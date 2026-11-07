# ADR-002: Stop reason capture — logger interceptor vs should_continue wrapper

## Contexto

Cuando el Swarm de Strands supera un límite (`max_handoffs`, `max_iterations`, etc.), el SDK
**no expone** la razón de parada en el objeto de resultado (`SwarmResult`). La única fuente de
esta información es el mensaje que el SDK emite a `logger.debug(...)` en el logger
`strands.multiagent.swarm` (hijo de `"strands"`).

Hay dos enfoques para capturarla:
- **(a)** Interceptar el logger `"strands"` en nivel DEBUG.
- **(b)** Envolver el método `should_continue` de `SwarmState` para observar las condiciones
  antes de que el SDK las evalúe.

## Decisión

**Interceptar el logger** `logging.getLogger("strands")` en nivel DEBUG, añadiendo y removiendo
un handler custom alrededor de cada ejecución (`attach()` / `detach()`).

## Alternativa considerada

**Wrapper de `should_continue`**: envolver `swarm.state.should_continue` para inspeccionar
`len(node_history)` y compararlo con los límites configurados, infiriendo la razón de parada.
Tiene acceso directo al estado pero requiere replicar la lógica interna del SDK, creando
acoplamiento frágil con la implementación.

## Trade-offs

| Aspecto | Logger interceptor | should_continue wrapper |
|---|---|---|
| Acoplamiento | ✅ Solo al string del mensaje de log | ❌ A lógica interna del SDK |
| Fragilidad ante cambios de SDK | ✅ Solo si cambia el string | ❌ Si cambia la lógica de limit-check |
| Completitud | ✅ Captura todos los límites con el mismo código | ❌ Hay que replicar cada condición |
| Captura de node_timeout | ✅ Sí (el timeout lanza excepción antes de `should_continue`) | ❌ No accesible vía should_continue |
| Limpieza de recursos | ⚠️ Hay que hacer `removeHandler` en `finally` | ✅ Solo restaurar función original |
