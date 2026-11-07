# ADR-001: Swarm vs Graph pattern for multi-agent orchestration

## Contexto

Strands Agents ofrece dos patrones de orquestación multiagente:
**Swarm** (agentes se pasan control mediante `handoff_to_agent`, sin DAG explícito)
y **Graph** (grafo de nodos con aristas tipadas y control de flujo declarativo).

El benchmark necesita demostrar comportamientos de fallo **emergentes** cuando los controles
están desactivados; la elección del patrón determina qué controles existen y cómo fallan.

## Decisión

Usar el patrón **Swarm**. Los controles de seguridad
(`max_handoffs`, `max_iterations`, `repetitive_handoff_detection_window`,
`repetitive_handoff_min_unique_agents`) están implementados en `multiagent/swarm.py` y vienen
**desactivados por defecto**. Esta es exactamente la tesis que el benchmark quiere demostrar.

## Alternativa considerada

Patrón **Graph**: ofrece flujo más predecible y tipado, con aristas explícitas que previenen
ciclos arbitrarios. Hubiera requerido demostrar que el grafo también puede configurarse
inseguramente, lo cual es menos directo y menos relevante para la tesis central.

## Trade-offs

| Aspecto | Swarm | Graph |
|---|---|---|
| Demuestra tesis central | ✅ Directo | ❌ Indirecto |
| Ciclos adversariales naturales | ✅ Fácil (ping-pong, infinite-chain) | ❌ Requiere aristas explícitas |
| Predictibilidad del flujo | ❌ Dinámica | ✅ Declarativa |
| Overhead de diseño | ✅ Bajo | ❌ Mayor (definir aristas) |
| Controles demostrables off-by-default | ✅ Sí | ❌ No equivalente |
