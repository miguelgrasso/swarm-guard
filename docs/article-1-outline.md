# Article 1 Outline: "The Strands Swarm brakes come off from the factory"

**Target publication:** AWS Builder Center  
**Vertical:** AI Engineering  
**Target length:** ~2000 words + 4–6 code snippets  

---

## 1. Hook (150 words)

> *"You deploy a multi-agent Swarm with Strands Agents. It looks fine in happy-path tests.
> Then production hits it with a ping-pong loop and your Lambda runs for 15 minutes."*

Open with the core observation: Swarm security controls exist but ship disabled.

---

## 2. What is a Strands Agents Swarm? (300 words)

- Handoff model: agents call `handoff_to_agent` to transfer control
- No DAG, no explicit edges — flexible but unpredictable
- Key controls in `multiagent/swarm.py` (verified against 1.64.0):
  - `max_handoffs`, `max_iterations`, `execution_timeout`, `node_timeout`
  - `repetitive_handoff_detection_window`, `repetitive_handoff_min_unique_agents`

Code snippet: Swarm constructor with default values highlighted.

---

## 3. The Six Verified Facts (500 words)

Step through each of the 6 SDK facts with minimal code evidence:

1. Default values table (all permissive)
2. `max_handoffs` and `max_iterations` share `len(node_history)` — same counter, smaller wins
3. Termination is `Status.FAILED` with no exception raised
4. `stop_reason` hidden in `logger.debug` — not in `SwarmResult`
5. Premature exit → `Status.COMPLETED` (silent wrong answer)
6. No native token budget — `accumulated_usage` grows unbounded

---

## 4. The Benchmark Setup (300 words)

- Three agents: researcher → analyst → writer
- Two configurations: baseline (defaults) vs guarded (controls on + BudgetGuard)
- 20 adversarial scenarios; 5 highlighted: ping_pong, self_handoff, context_inflation,
  premature_exit, shared_context_injection

Code snippet: baseline_config() vs guarded_config() side by side.

---

## 5. Results Preview (400 words)

Table: 5 selected scenarios × 2 configs (Status / StopReason / Tokens / DetectionTime).

Key findings:
- 6 scenarios complete in both configs (SDK limitations documented)
- GuardedConfig stops ping-pong 2× faster
- BudgetGuard catches context_inflation before max_iterations
- Premature exit undetectable by either config — by design

---

## 6. How to reproduce (200 words)

```bash
git clone https://github.com/YOUR_USERNAME/swarm-guard
cd swarm-guard
uv sync
uv run pytest tests/unit/ -v   # no AWS needed
```

Link to full benchmark instructions in README.

---

## 7. Call to action (100 words)

- Turn the controls on before going to production
- Instrument with StopReasonInterceptor or a similar logger hook
- Add a BudgetGuard if cost predictability matters
- Watch Article 2 for live Bedrock measurements and CloudWatch dashboards

---

## Appendix: Key code snippets

1. `swarm.py` defaults (annotated screenshot / code block)
2. `baseline_config()` function
3. `guarded_config()` function  
4. `StopReasonInterceptor.attach()` / `detach()`
5. `BudgetGuard.inject()` wrapper
