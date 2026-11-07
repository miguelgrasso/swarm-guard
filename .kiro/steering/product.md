---
inclusion: always
---

# Product Steering — swarm-guard

## Propósito del proyecto

`swarm-guard` es un proyecto de referencia para la postulación a AWS Community Builders (verticales: **AI Engineering** y **Cloud Ops**). Demuestra, con evidencia reproducible, que los controles de seguridad del patrón Swarm en Strands Agents están **desactivados por defecto** y mide el impacto de activarlos frente a 20 escenarios adversariales.

## Tesis central

> "Los frenos de un Swarm de Strands Agents vienen apagados de fábrica."

El proyecto cuantifica qué ocurre **con** y **sin** controles comparando dos configuraciones:

| Configuración | Descripción |
|---|---|
| `baseline` | Defaults del SDK (max_handoffs=20, max_iterations=20, ping-pong desactivado) |
| `guarded` | 4 controles del SDK encendidos + guardia propia de presupuesto de tokens |

## Salidas del proyecto

Un único repositorio público alimenta tres salidas:

1. **Repo público** — benchmark reproducible con IaC, datos sintéticos y script de limpieza.
2. **2 artículos** en AWS Builder Center (`docs/article-1-outline.md` y `docs/article-2-outline.md`).
3. **2 charlas de meetup** — slides derivadas del benchmark.

## Restricciones de negocio

- **Región AWS:** `us-east-2` únicamente (SCP de organización bloquea `us-east-1`).
- **Sin despliegues durante el diseño:** la cuenta AWS está en verificación.
- **Sin credenciales en el repo:** usar `.env.example`; nunca incluir IDs de cuenta, ARNs reales ni claves.
- **Licencia:** Apache-2.0.
- **Documentación:** un solo idioma por archivo. README en inglés con sección "Resumen en español".

## Hechos verificados del SDK (strands-agents, multiagent/swarm.py)

Estos hechos deben demostrarse con pruebas reproducibles, no asumirse:

1. Defaults: `max_handoffs=20`, `max_iterations=20`, `execution_timeout=900.0`, `node_timeout=300.0`, `repetitive_handoff_detection_window=0`, `repetitive_handoff_min_unique_agents=0`.
2. `max_handoffs` y `max_iterations` comparan el mismo contador (`len(node_history)`); gana el menor.
3. Al superar cualquier límite, el swarm termina con `Status.FAILED` sin excepción; la razón solo aparece en `logger.debug`, no en el resultado.
4. Si un agente responde sin llamar `handoff_to_agent`, el swarm termina `COMPLETED` aunque la tarea esté a medias (terminación prematura silenciosa).
5. `node_timeout` lanza excepción y el swarm completo cae a `FAILED`.
6. No existe presupuesto nativo de tokens ni de costo; el resultado expone `accumulated_usage` y `accumulated_metrics`.

## Audiencia

- Comunidad AWS Builders (revisores de la postulación).
- Ingenieros que construyen sistemas multiagente con Strands y Bedrock.
- Equipos de Cloud Ops interesados en observabilidad y controles de costo.
