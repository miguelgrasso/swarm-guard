---
inclusion: always
---

# Tech Steering — swarm-guard

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Gestor de paquetes | `uv` + `pyproject.toml` |
| SDK multiagente | `strands-agents` (multiagent/swarm.py) |
| Proveedor de modelo (default) | Amazon Bedrock — región `us-east-2` |
| Proveedor de modelo (alt) | Ollama local — solo para validar mecánica, nunca para mediciones |
| Linter / formatter | `ruff` |
| Type checker | `mypy` |
| Test runner | `pytest` |
| Observabilidad | CloudWatch EMF (Embedded Metrics Format) |
| IaC | CloudFormation — región `us-east-2` |
| Licencia | Apache-2.0 |

## Configuración del proveedor de modelo

El proveedor se selecciona con la variable de entorno `MODEL_PROVIDER`:

```
MODEL_PROVIDER=bedrock   # default — usa Bedrock en us-east-2
MODEL_PROVIDER=ollama    # local — solo para pruebas de mecánica
```

Nunca hardcodear el proveedor ni el modelo en el código de la aplicación. Leer desde entorno o archivo de configuración.

## Precios de tokens (configurables)

El costo por corrida se calcula como `tokens × precio_configurable`. Los precios se leen de variables de entorno o de un archivo de configuración. **Nunca hardcodear precios en el código de la aplicación.**

## Tests

### Tests unitarios (sin red ni credenciales)

- Modelo con guion (`scripted model`): responde con fixtures predefinidos.
- Proveedor simulado (`mock provider`): no llama a ningún endpoint real.
- Deben correr con `pytest` sin ninguna variable de entorno de AWS configurada.
- Son la base de CI.

### Tests de integración (opt-in)

- Requieren credenciales AWS reales y acceso a Bedrock en `us-east-2`.
- Marcados con `@pytest.mark.integration`.
- Se ejecutan manualmente o en CI con flag `--run-integration`.

## Observabilidad

- Capturar `stop_reason` interceptando el logger de debug de Strands (`logging.getLogger("strands")`).
- Emitir métricas CloudWatch EMF con dimensiones: `[config, scenario, stop_reason]`.
- Métricas requeridas (nombres Cloud Ops):
  - `DetectionTime` — tiempo desde inicio hasta detección del problema
  - `RecoveryTime` — tiempo desde detección hasta corte del swarm
  - `CostPerRun` — tokens × precio configurable
  - `CorrectStopRate` — tasa de parada correcta
  - `FalsePositiveRate` — tasa de falsos positivos

## IaC

- CloudFormation únicamente (us-east-2).
- Roles IAM por agente con `Deny` explícito a acciones mutantes.
- Log group, dashboard CloudWatch, alarma de presupuesto.
- **No desplegar durante el diseño** — la cuenta AWS está en verificación.
- Script `scripts/cleanup.sh` destruye todos los recursos y verifica que no quedan huérfanos.

## Seguridad y secretos

- Nunca incluir IDs de cuenta, ARNs reales ni claves en el repo.
- Archivo `.env.example` con todas las variables requeridas (sin valores reales).
- `.env` en `.gitignore`.

## Convenciones de código

- Identificadores, comentarios inline y commits en inglés.
- Documentación de módulos y archivos en el idioma del archivo (inglés para todo excepto donde se indique).
- `ruff` y `mypy` deben pasar sin errores en CI.
- Imports ordenados con `ruff --select I`.

## ADRs requeridos

Ubicación: `docs/adr/`. Formato corto: contexto, decisión, alternativa, trade-off.

1. `adr-001-swarm-vs-graph.md` — elección de Swarm vs Graph
2. `adr-002-stop-reason-capture.md` — captura de stop_reason
3. `adr-003-budget-guard.md` — guardia de presupuesto de tokens
4. `adr-004-cloudformation-vs-cdk.md` — CloudFormation vs otra IaC
