# swarm-guard

The brakes on a Strands Agents Swarm come turned off from the factory. This repo measures them on and off against 20 adversarial scenarios.

## Status

Design phase. No benchmark results yet. Article 1 (design) in `docs/article-1.md`; article 2 (results) pending.

## Findings (verified against strands-agents 1.64.0 source)

1. Ping-pong detection is off by default (`repetitive_handoff_detection_window=0`, `repetitive_handoff_min_unique_agents=0`).
2. `max_handoffs` and `max_iterations` compare the same counter (`len(node_history)`); the smaller wins.
3. On limit exceeded the swarm ends `Status.FAILED` with no exception; the reason only goes to `logger.debug`.
4. If an agent responds without calling `handoff_to_agent`, the swarm ends `COMPLETED` even if the task is unfinished.
5. `node_timeout` raises an internal exception the SDK captures; the result is `FAILED` and the node is not in `node_history`.
6. No native token or cost budget; the result exposes `accumulated_usage` and `accumulated_metrics` but does not enforce them.

## Cost guards

The `guarded` configuration turns on four SDK controls with lower thresholds (`max_handoffs=10`, `max_iterations=10`, `execution_timeout=300`, `node_timeout=60`, ping-pong `window=8`, `min_unique_agents=3`) plus a custom `BudgetGuard` that reads `accumulated_usage.total_tokens` between handoffs and stops the swarm when it exceeds `BUDGET_GUARD_MAX_TOKENS`.

## Validity limits

- Tests are synthetic (scripted model with predefined fixtures).
- Results apply to strands-agents 1.64.0 only.
- Token prices are read from the `TOKEN_PRICE_PER_UNIT` environment variable; nothing is hardcoded.
- AWS region is `us-east-2`.

## Quick start

```bash
uv sync
uv run pytest tests/unit/ -v
```

Available after phase A (application code, scenarios and tests are not yet committed).

## Cleanup

```bash
bash scripts/cleanup.sh
```

Available after phase A.

## Resumen en español

`swarm-guard` demuestra que los frenos de un Swarm de Strands Agents vienen apagados de fábrica.
El proyecto mide el comportamiento del swarm con y sin controles frente a 20 escenarios adversariales.
Compara dos configuraciones: `baseline` (defaults del SDK) y `guarded` (controles encendidos).
Los hallazgos están verificados contra el código fuente de strands-agents 1.64.0.
Artículo 1 (diseño) en `docs/article-1.md`; artículo 2 (resultados) pendiente.

## License

Apache-2.0. See [LICENSE](LICENSE).
