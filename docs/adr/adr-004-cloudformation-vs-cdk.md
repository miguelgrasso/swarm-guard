# ADR-004: CloudFormation vs CDK para infraestructura

## Contexto

El proyecto necesita IaC para IAM roles, Log Groups, un Dashboard de CloudWatch y una alarma
de presupuesto en `us-east-2`. Las opciones principales son:
- **CloudFormation**: plantilla YAML declarativa, sin dependencias de compilación.
- **CDK**: código Python/TypeScript que genera CloudFormation, con framework de testing incluido.

El objetivo es un repositorio público reproducible orientado a revisores de AWS Community Builders.

## Decisión

Usar **CloudFormation** directamente (`infra/template.yaml`). El objetivo es la reproducibilidad
máxima: cualquier revisor puede inspeccionar la plantilla YAML directamente sin instalar
dependencias adicionales más allá de la AWS CLI.

## Alternativa considerada

**AWS CDK (Python)**: permite usar el mismo lenguaje (Python 3.12) que el resto del proyecto,
con `cdk synth` para snapshot testing y `cdk diff` para revisión de cambios. Descartado porque
añade una dependencia de Node.js (para el CLI de CDK) que complica el setup, y porque la
auditoría de seguridad por revisores externos es más directa con YAML plano.

## Trade-offs

| Aspecto | CloudFormation | CDK |
|---|---|---|
| Dependencias | ✅ Solo AWS CLI | ❌ Node.js + npm + CDK CLI |
| Auditoría directa | ✅ YAML legible sin herramientas | ⚠️ Requiere `cdk synth` para ver el template |
| Testing de IaC | ⚠️ Validación con cfn-lint | ✅ `cdk assertions` nativo |
| Abstracción L2/L3 | ❌ Manual | ✅ Constructs preempaquetados |
| Idoneidad para el proyecto | ✅ Alta (simplicidad reproducible, 4 recursos) | ⚠️ Overkill |
