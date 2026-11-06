# Los frenos de tu swarm vienen apagados de fábrica: controles de operación para Strands Agents Swarm

## Qué límites trae el SDK, cuáles no vienen encendidos y cómo medir si funcionan

Peter Steinberger escribió que no deberías estar formulando prompts a los agentes; deberías estar diseñando bucles que formulen prompts a tus agentes. Concedida como cierta. La pregunta que sigue es directa: ¿y quién apaga el bucle cuando el agente no sabe qué hacer?

En una demo comunitaria, un agente con Strands tardó 5 a 6 segundos por decisión, superó un límite de 8 segundos, hizo timeout y se quedó en el bucle. La explicación del orador fue que el contexto crece y el agente no sabe qué decidir. En producción, quien lo detiene eres tú, o nadie.

## 1. El problema en una frase

En un swarm nadie manda. Cada agente decide a quién pasar el trabajo, y dos agentes pueden pasárselo entre sí hasta agotar tiempo y tokens. Imagina un grupo de estudiantes con un solo cuaderno: si nadie dice "ya terminé", se lo pasan indefinidamente y nadie escribe la conclusión. El SDK trae límites para cortar el bucle, pero vienen apagados o con topes que no están pensados para tu caso.

## 2. Antecedentes en la comunidad

Diego Flores, en "Designing Enterprise-Grade LLM Agent Architectures on AWS", propone un supervisor jerárquico que orquesta agentes especializados, IAM por agente con mínimo privilegio y un circuit breaker para caídas de backend. Menciona "strict iteration ceilings" como ventaja de su patrón supervisor, pero no muestra ninguno configurado ni explica qué pasa cuando se alcanza. Este artículo cubre lo que ese trabajo deja abierto: los límites del propio bucle entre agentes, no los de un agente individual contra un backend.

Sergio Mondragón, en el repositorio strands-decider-patterns, implementa un tope de 60 llamadas LLM por ejecución y un presupuesto de 5 USD para su benchmark, ambos por fuera del SDK, en código que envuelve la ejecución. Es un agente único, no un swarm, pero la idea es la misma: el SDK no trae los frenos, hay que ponerlos.

El principio compartido con ambos es el mismo: los controles van en infraestructura y código, no en el prompt. El prompt describe la tarea; el bucle es infraestructura. Si confías en el prompt para que el agente se detenga, estás confiando en que el LLM siempre haga lo que le pides. En un escenario adversarial, no lo hará.

## 3. Ficha del swarm de ejemplo

| Agente | Herramienta | Permiso IAM | Handoff a |
|---|---|---|---|
| Researcher | `search_knowledge_base(query)` | S3 lectura + Bedrock InvokeModel; Deny mutantes | Analyst |
| Analyst | `analyze_data(data)` | S3 lectura + Bedrock InvokeModel; Deny mutantes | Writer |
| Writer | `format_output(content)` | S3 lectura + escritura bucket output; Deny `iam:*`, `sts:*` | --- (nodo terminal) |

Los tres agentes usan el mismo modelo en Amazon Bedrock, región us-east-2. El proveedor se selecciona con la variable de entorno `MODEL_PROVIDER` (`bedrock` o `ollama`).

Swarm entrega a cada agente la herramienta `handoff_to_agent` con todos los demás agentes como destino posible. La columna "Handoff a" es la intención de diseño, no algo que el SDK haga cumplir; justo por eso el ping-pong es posible.

## 4. Qué trae el SDK

strands-agents 1.64.0, archivo `src/strands/multiagent/swarm.py`. Los seis parámetros de control del swarm y sus valores por defecto:

| Parámetro | Valor por defecto | Qué detiene | Qué pasa al dispararse |
|---|---|---|---|
| `max_handoffs` | 20 | Handoffs entre agentes | `Status.FAILED`; razón en `logger.debug` |
| `max_iterations` | 20 | Iteraciones del bucle | `Status.FAILED`; razón en `logger.debug` |
| `execution_timeout` | 900.0 s | Tiempo total del swarm | `Status.FAILED` |
| `node_timeout` | 300.0 s | Tiempo de un solo agente | `Status.FAILED`; el nodo no entra en `node_history` |
| `repetitive_handoff_detection_window` | 0 | Ventana de detección de ping-pong | Desactivado |
| `repetitive_handoff_min_unique_agents` | 0 | Agentes únicos mínimos en ventana | Desactivado |

### Hallazgo 1: el ping-pong viene desactivado

En la versión 1.64.0, según el código fuente, `repetitive_handoff_detection_window=0` y `repetitive_handoff_min_unique_agents=0`. Con esos valores, dos agentes pueden pasarse el control indefinidamente hasta que otro límite actúe. La detección de ping-pong existe en el SDK, pero no viene encendida.

### Hallazgo 2: max_handoffs y max_iterations comparan el mismo contador

En la versión 1.64.0, según el código fuente, ambos límites comparan `len(node_history)`. Gana el menor. Si `max_handoffs=10` y `max_iterations=20`, el swarm para a los 10 handoffs. Solo cambia el texto de la razón, no el comportamiento. Fragmento del SDK (licencia Apache-2.0):

```python
# strands-agents 1.64.0 — src/strands/multiagent/swarm.py (Apache-2.0)
if len(self.node_history) >= max_handoffs:
    return False, f"Max handoffs reached: {max_handoffs}"
if len(self.node_history) >= max_iterations:
    return False, f"Max iterations reached: {max_iterations}"
```

La función devuelve una tupla `(bool, razón)`. Es el bucle que la llama quien escribe la razón con `logger.debug` y pone `Status.FAILED`.

### Hallazgo 3: la razón de parada no llega al resultado

En la versión 1.64.0, según el código fuente, al superar un límite el swarm termina `Status.FAILED` sin excepción. La razón ("Max handoffs reached", "Repetitive handoff: N unique nodes out of M") solo va a `logger.debug`. No queda en el objeto de resultado. En producción, sin interceptar el logger, no sabes por qué paró.

### Hallazgo 4: terminación prematura silenciosa

En la versión 1.64.0, según el código fuente, si un agente responde sin llamar `handoff_to_agent`, el swarm termina `COMPLETED` aunque la tarea esté a medias. No hay error ni warning. El resultado dice "completado" y la tarea quedó incompleta.

### Hallazgo 5: node_timeout tira el swarm completo

En la versión 1.64.0, según el código fuente, `node_timeout` lanza una excepción interna que el SDK captura; para quien llama, el resultado es `FAILED`, igual que con los otros límites. La diferencia es que ese nodo no se registra en `node_history`, porque solo se registran los nodos que terminan `COMPLETED`.

### Hallazgo 6: no hay presupuesto de tokens

En la versión 1.64.0, según el código fuente, no existe un presupuesto nativo de tokens ni de costo. El resultado expone `accumulated_usage` y `accumulated_metrics`, pero el SDK no los usa para detener la ejecución. Un swarm puede consumir tokens sin límite hasta que otro control actúe o se acabe el tiempo.

## 5. Los controles que proponemos

| Control | Parámetro o componente | Qué previene | Cómo se verifica |
|---|---|---|---|
| Tope de handoffs | `max_handoffs=10` | Bucle infinito entre 2 agentes | `len(node_history) <= 10` |
| Timeout de ejecución | `execution_timeout=300.0` | Swarm que consume tiempo indefinido | Tiempo total < 300 s |
| Timeout por nodo | `node_timeout=60.0` | Agente lento bloquea el swarm | `FAILED` a los 60 s; el nodo no aparece en `node_history` |
| Ping-pong | `window=8`, `min_unique=3` | Dos agentes se pasan el control | Razón = `repetitive_handoff` |
| Presupuesto de tokens | `BudgetGuard` (propio) | Costo descontrolado | `budget_exceeded` en log |

Los primeros tres son nativos del SDK, encendidos a propósito con valores más bajos que los defaults. El cuarto es nativo pero viene apagado; lo encendemos con `repetitive_handoff_detection_window=8` y `repetitive_handoff_min_unique_agents=3`. El quinto no existe en el SDK.

El BudgetGuard lee `accumulated_usage.total_tokens` después de cada respuesta; si supera el umbral, devuelve `(False, 'budget_exceeded')`. El umbral se lee de la variable de entorno `BUDGET_GUARD_MAX_TOKENS` y el precio por token de `TOKEN_PRICE_PER_UNIT`; ninguno de los dos se hardcodea en el código de aplicación. La implementación propuesta envuelve `should_continue` del estado del swarm; como el estado se crea en cada ejecución, falta confirmar que el wrapper sobreviva entre invocaciones. Pendiente de verificar en la implementación.

### Observabilidad: la razón de parada es la métrica clave

Sin capturar la razón de parada no distingues "paró por ping-pong" de "falló un agente por timeout". El `StopReasonInterceptor` adjunta un handler al logger `"strands"` en nivel DEBUG, extrae la razón con patrones regex y la expone. La razón viaja como dimensión en las métricas CloudWatch EMF:

```python
# Namespace: SwarmGuard
# Dimensiones: [config, scenario, stop_reason]
{
  "config": "guarded",
  "scenario": "ping_pong",
  "stop_reason": "repetitive_handoff"
}
```

Sin esa dimensión, un dashboard de CloudWatch muestra que el swarm falló, pero no por qué. Con ella, puedes segmentar y comparar: los fallos de baseline, ¿son todos `max_handoffs`? Los de guarded, ¿son `repetitive_handoff` o `budget_exceeded`? Esa es la pregunta que el artículo 2 responde con números.

## 6. Cómo lo vamos a medir

20 escenarios adversariales con el mismo input para baseline y guarded. Sin resultados todavía; este artículo es de diseño.

Categorías de escenarios: ping-pong entre 2 agentes, cadena de delegación infinita, agente lento, terminación prematura por inyección, handoff a sí mismo, handoff a agente inexistente, inflado de contexto, inyección entre agentes vía shared context, tarea imposible y caso feliz como control. Cada escenario se define en un archivo YAML con el prompt de entrada, el vector de ataque y los resultados esperados para cada configuración. El mismo input se ejecuta contra baseline y guarded; la diferencia está en los controles, no en el prompt.

Para "handoff a agente inexistente", el SDK no falla: `handoff_to_agent` devuelve un error como resultado de la herramienta y el agente continúa. Es un escenario donde baseline y guarded deberían comportarse igual; sirve para comprobar que los controles no introducen falsos positivos.

Métricas: tiempo de detección (desde que inicia el ataque hasta que se dispara el control, en segundos y en handoffs), tiempo de recuperación (desde el disparo hasta que el proceso devuelve el resultado y libera recursos), costo por corrida (tokens multiplicado por precio configurable), tasa de parada correcta (aciertos sobre total) y falsos positivos (guarded corta lo que baseline completó bien). El artículo 2 trae la tabla con los números.

## 7. Lo que este diseño no resuelve

Los límites por iteración no equivalen a calidad de la respuesta. Un swarm puede parar en 3 handoffs y entregar un resultado incorrecto. El control mide cuántas veces pasó el control, no si el resultado es correcto.

El presupuesto de tokens depende de precios configurables. El costo se calcula como `total_tokens * TOKEN_PRICE_PER_UNIT`, leído de entorno. Si el proveedor cambia precios, el umbral de costo no se ajusta solo. Hay que actualizar la variable.

Un agente malicioso puede terminar "bien" sin hacer la tarea. El Hallazgo 4 lo demuestra: responder sin `handoff_to_agent` produce `COMPLETED`. Ninguno de los 5 controles lo detecta. Se necesitan controles de validación de output, que están fuera del alcance de este diseño.

Las pruebas son sintéticas. Los escenarios usan un modelo scripted en tests unitarios que responde con fixtures predefinidos. Los resultados reales dependen del modelo, del prompt y del dominio. El benchmark con Bedrock real va en el artículo 2.

## 8. Repo y reproducción

El repo incluye IaC en CloudFormation para us-east-2 (roles IAM por agente con `Deny` explícito a acciones mutantes, log groups, dashboard y alarma de presupuesto), datos sintéticos para los 20 escenarios y un script de limpieza (`scripts/cleanup.sh`) que destruye todos los recursos y verifica que no quedan huérfanos.

Los tests unitarios corren sin credenciales AWS ni acceso a red, usando un modelo scripted que responde con fixtures predefinidos:

```bash
# Sin credenciales, sin red
uv sync
uv run pytest tests/unit/ -v
uv run ruff check .
uv run mypy src/
```

Los tests de integración requieren Bedrock en us-east-2 y se activan con el marker de pytest `integration` (`uv run pytest -m integration`). El template de CloudFormation se puede validar con `cfn-lint` sin credenciales. No se despliega durante el diseño; la cuenta AWS está en verificación.

## 9. Siguiente artículo

El artículo 2 ejecuta el benchmark con Bedrock real contra los 20 escenarios. Presenta la tabla completa con tiempos, tokens, costo y razón de parada por escenario. Si los controles funcionan, la tasa de parada correcta sube y el costo baja. Si no, sabremos exactamente dónde fallan.

## 10. Referencias

- Documentación del patrón Swarm, Strands Agents. https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/
- Código fuente strands-agents 1.64.0, src/strands/multiagent/swarm.py. https://github.com/strands-agents/sdk-python/blob/main/src/strands/multiagent/swarm.py
- Diego Flores, "Designing Enterprise-Grade LLM Agent Architectures on AWS". https://builder.aws.com/content/3IpW0GXjKlNBuJdIuhgkhONg2B6/designing-enterprise-grade-llm-agent-architectures-on-aws-security-resilience-and-architectural-trade-offs
- Sergio Mondragón, charla "AI Capture The Flag" (AWS Community Day Paraguay 2026). https://www.youtube.com/watch?v=-qpBeOeHTDI
- Sergio Mondragón, repositorio strands-decider-patterns. https://github.com/Akemid/strands-decider-patterns
- Peter Steinberger, publicación en X. URL_TWEET

## Pendiente antes de publicar

1. URL del repo público swarm-guard y confirmar que el tag `baseline` existe.
2. Verificar que el wrapper de BudgetGuard sobrevive entre invocaciones de `should_continue`.
3. Confirmar nombres finales de los agentes (Researcher, Analyst, Writer) en `design.md`.
4. Confirmar en el README de strands-decider-patterns las cifras de 60 llamadas LLM y 5 USD; si no aparecen, eliminar esa frase de la sección 2.
5. Rellenar URL_TWEET con el enlace a la publicación de Peter Steinberger.
