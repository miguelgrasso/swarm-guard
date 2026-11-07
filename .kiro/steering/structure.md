---
inclusion: always
---

# Structure Steering — swarm-guard

## Estructura de directorios

```
swarm-guard/
├── src/
│   └── swarm_guard/
│       ├── __init__.py
│       ├── agents/              # Definición de los 3 agentes especializados
│       │   ├── researcher.py
│       │   ├── analyst.py
│       │   └── writer.py
│       ├── configs/             # Configuraciones baseline y guarded
│       │   ├── baseline.py
│       │   └── guarded.py
│       ├── observability/       # Captura de stop_reason y emisión EMF
│       │   ├── stop_reason.py   # Interceptor del logger de debug de Strands
│       │   └── emf.py           # Emisor de métricas CloudWatch EMF
│       ├── budget_guard.py      # Quinto control: guardia de presupuesto de tokens
│       └── runner.py            # Orquestador del benchmark (carga escenarios, ejecuta, reporta)
├── scenarios/
│   ├── __init__.py
│   └── adversarial/
│       ├── scenario_01_happy_path.yaml
│       ├── scenario_02_ping_pong.yaml
│       ├── scenario_03_infinite_chain.yaml
│       ├── scenario_04_slow_node.yaml
│       ├── scenario_05_premature_exit.yaml
│       ├── scenario_06_self_handoff.yaml
│       ├── scenario_07_unknown_agent.yaml
│       ├── scenario_08_context_inflation.yaml
│       ├── scenario_09_shared_context_injection.yaml
│       ├── scenario_10_impossible_task.yaml
│       ├── scenario_11_tool_loop.yaml
│       ├── scenario_12_zombie_agent.yaml
│       ├── scenario_13_privilege_escalation.yaml
│       ├── scenario_14_memory_poisoning.yaml
│       ├── scenario_15_cascade_backtrack.yaml
│       ├── scenario_16_data_exfiltration.yaml
│       ├── scenario_17_self_delegation_loop.yaml
│       ├── scenario_18_role_conflict.yaml
│       ├── scenario_19_malformed_json.yaml
│       └── scenario_20_timeout_chain.yaml
├── scripts/
│   ├── run_benchmark.py         # Ejecuta los 20 escenarios × 2 configs
│   ├── compare_runs.py          # Compara dos runs y genera tabla Markdown
│   └── cleanup.sh               # Destruye recursos IaC y verifica que no quedan huérfanos
├── infra/
│   ├── template.yaml            # CloudFormation stack (us-east-2)
│   └── parameters.json          # Parámetros sin valores reales
├── tests/
│   ├── unit/
│   │   ├── test_defaults.py     # Verifica los 6 hechos del SDK con modelo scripted
│   │   ├── test_budget_guard.py
│   │   ├── test_stop_reason.py
│   │   ├── test_scenarios.py    # Carga y valida estructura de cada escenario YAML
│   │   └── conftest.py          # Fixtures: scripted model, mock provider
│   └── integration/             # Tests opt-in con Bedrock real
│       ├── test_baseline_bedrock.py
│       └── test_guarded_bedrock.py
├── docs/
│   ├── adr/
│   │   ├── adr-001-swarm-vs-graph.md
│   │   ├── adr-002-stop-reason-capture.md
│   │   ├── adr-003-budget-guard.md
│   │   └── adr-004-cloudformation-vs-cdk.md
│   ├── findings.md              # Generado por scripts/compare_runs.py — no editar a mano
│   ├── article-1-outline.md
│   └── article-2-outline.md
├── .env.example                 # Variables requeridas sin valores reales
├── .gitignore
├── pyproject.toml               # uv, ruff, mypy, pytest config
├── LICENSE                      # Apache-2.0
└── README.md                    # Inglés + sección "Resumen en español"
```

## Convenciones de archivos

### Escenarios YAML

Cada archivo `scenarios/adversarial/scenario_NN_*.yaml` sigue este esquema:

```yaml
name: string                    # Identificador corto en snake_case
attack_vector: string           # Descripción del vector de ataque
input: string                   # Prompt de entrada — idéntico para baseline y guarded
expected_baseline:
  status: FAILED | COMPLETED    # Estado esperado del swarm en baseline
  stop_reason: string | null    # Razón de parada esperada (null si no aplica)
expected_guarded:
  status: FAILED | COMPLETED
  stop_reason: string | null
tags: [list of strings]         # p. ej. [ping-pong, handoff, timeout]
```

### Métricas EMF

Las métricas se emiten en el namespace `SwarmGuard` con las dimensiones `[config, scenario, stop_reason]`.

Nombres de métricas (Cloud Ops):
- `DetectionTime` (ms)
- `RecoveryTime` (ms)
- `CostPerRun` (USD)
- `CorrectStopRate` (ratio 0-1)
- `FalsePositiveRate` (ratio 0-1)
- `TotalHandoffs` (count)
- `TotalTokens` (count)

### ADRs

Formato corto obligatorio:

```markdown
# ADR-NNN: Título

## Contexto
## Decisión
## Alternativa considerada
## Trade-offs
```

## Reglas de naming

- Módulos Python: `snake_case`
- Clases: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Variables de entorno: `UPPER_SNAKE_CASE`
- Archivos de escenario: `scenario_NN_descripcion_corta.yaml` (NN = 01-20)
- Stacks CloudFormation: `swarm-guard-{env}` (env = dev | prod)
- Log groups: `/swarm-guard/{env}/{agent_name}`

## Archivos que NUNCA deben commitearse

- `.env` (credenciales reales)
- `*.pyc`, `__pycache__/`
- `.venv/`, `dist/`, `*.egg-info/`
- `docs/findings.md` generado localmente con datos reales de Bedrock (solo se commitea la versión de referencia con datos sintéticos)

## Generación de findings.md

`docs/findings.md` es generado por `scripts/compare_runs.py`. Nunca editarlo manualmente. El script toma como input dos archivos JSON de resultados y produce una tabla Markdown reproducible.
