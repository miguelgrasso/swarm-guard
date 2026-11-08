# Diagrams

- **01-arquitectura-aws.drawio** — AWS architecture in us-east-2: Bedrock, CloudWatch (metrics, dashboard, alarm), IAM roles per agent.
- **02-swarm-sin-frenos.drawio** — Sequence of a Swarm with SDK defaults: ping-pong runs until handoff 20, ends FAILED with no stop_reason in the result.
- **03-swarm-con-frenos.drawio** — Same sequence with guarded controls: repetitive_handoff fires at node 6, stop_reason is captured.

Export each to PNG in `docs/img/` with the same base name (e.g. `01-arquitectura-aws.png`) using draw.io's File → Export As → PNG.
