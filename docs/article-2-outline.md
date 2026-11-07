# Article 2 Outline: "Measuring the brakes: live Bedrock data from swarm-guard"

**Target publication:** AWS Builder Center  
**Vertical:** Cloud Ops  
**Target length:** ~2500 words + CloudWatch screenshots + data tables  
**Prerequisite:** Article 1 (architecture and SDK facts)

---

## 1. Hook (150 words)

> *"Article 1 showed the controls exist but ship off. Now here are the numbers from 20
> adversarial scenarios × 2 configs × real Bedrock calls in us-east-2."*

---

## 2. Methodology recap (200 words)

- strands-agents 1.64.0, us-east-2, Claude Haiku (cost-optimal)
- 20 scenarios × 2 configs = 40 runs
- Metrics captured: DetectionTime, RecoveryTime, CostPerRun, TotalTokens, TotalHandoffs
- Emitted via CloudWatch EMF → namespace `SwarmGuard`

---

## 3. Full Results Table (600 words)

Complete table: 20 rows × columns: Scenario, Baseline Status, Baseline Stop Reason,
Guarded Status, Guarded Stop Reason, Baseline Correct, Guarded Correct, ΔTokens, ΔCost.

Generated from `docs/findings.md`.

---

## 4. Deep Dive: The 6 Interesting Scenarios (600 words)

**Scenario 06 — self_handoff**: GuardedConfig fires `repetitive_handoff` at iteration 9;
baseline runs to 20. 53% token saving.

**Scenario 08 — context_inflation**: BudgetGuard fires at ~4,800 tokens; baseline runs
to max_iterations accumulating ~22,000 tokens. 78% token saving.

**Scenario 02 — ping_pong**: Both fail at max_handoffs; guarded at 10 vs baseline at 20.
DetectionTime 140ms vs 280ms.

**Scenario 05 — premature_exit**: Both COMPLETED. No control stops a silent wrong answer.
Important limitation to document.

**Scenario 17 — self_delegation_loop**: Both configs detect repetitive handoff; guarded
fires sooner due to lower window (8 vs no window in baseline → falls to max_handoffs at 20).

**Scenario 09 — shared_context_injection**: Both COMPLETED. Swarm has no content guardrails.

---

## 5. CloudWatch Observability (400 words)

- How StopReasonInterceptor feeds DetectionTime and RecoveryTime into EMF
- Screenshot: SwarmGuard dashboard comparing baseline vs guarded timelines
- Alarm setup: CostPerRun > $5 → SNS → email notification
- How to reproduce: CloudFormation template in `infra/`

---

## 6. CorrectStopRate and FalsePositiveRate (300 words)

- Definition of each metric
- Results: GuardedConfig CorrectStopRate vs BaselineConfig
- FalsePositiveRate: how many times did GuardedConfig stop something baseline completed correctly?
- Discussion: the 6 COMPLETED-in-both scenarios are features, not failures

---

## 7. Cost analysis (200 words)

- Token cost per scenario (baseline vs guarded)
- Estimated monthly cost at 100 benchmark runs/day
- BudgetGuard ROI: X% token savings for adversarial workloads

---

## 8. Recommendations (150 words)

1. Always set `max_handoffs ≤ 10` for production Swarms
2. Always enable `repetitive_handoff_detection_window ≥ 5`
3. Implement a BudgetGuard for any cost-sensitive workload
4. Instrument with StopReasonInterceptor + CloudWatch EMF for observability
5. Accept that premature exit, context injection, and output exfiltration
   require application-layer controls (not SDK controls)

---

## Appendix

- Full `docs/findings.md` table (link)
- CloudFormation template walkthrough
- Cost breakdown table by scenario
