"""test_defaults.py — verifies the 6 verified SDK facts for strands-agents 1.64.0.

All tests run offline against a *real* ``Swarm`` driven by the ``ScriptedModel``
fixtures in conftest — no AWS credentials, no network, and no mocks over
``Swarm`` / ``SwarmResult`` / ``SwarmState``.

Requirements: 1.3, 1.5, 1.8, 8.3
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from time import monotonic

from strands.multiagent.base import Status
from strands.multiagent.swarm import Swarm, SwarmResult

from swarm_guard.configs.baseline import baseline_config
from swarm_guard.configs.guarded import guarded_config
from swarm_guard.observability.stop_reason import StopReasonInterceptor
from swarm_guard.runner import create_swarm
from tests.unit.conftest import ping_pong_agents, terminal_agent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(swarm: Swarm, task: str) -> tuple[SwarmResult, StopReasonInterceptor]:
    """Run a real swarm with the StopReasonInterceptor attached."""
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    try:
        result = swarm(task)
    finally:
        interceptor.detach(monotonic())
    return result, interceptor


# ---------------------------------------------------------------------------
# Fact 1 — Baseline config has exact SDK defaults
# ---------------------------------------------------------------------------


def test_baseline_config_values() -> None:
    """Baseline config mirrors the exact SDK defaults from strands-agents 1.64.0."""
    cfg = baseline_config()
    assert cfg.max_handoffs == 20
    assert cfg.max_iterations == 20
    assert cfg.execution_timeout == 900.0
    assert cfg.node_timeout == 300.0
    assert cfg.repetitive_handoff_detection_window == 0
    assert cfg.repetitive_handoff_min_unique_agents == 0
    assert cfg.budget_guard_enabled is False
    assert cfg.config_name == "baseline"


# ---------------------------------------------------------------------------
# Fact 2 — max_handoffs: swarm fails without raising when limit reached
# ---------------------------------------------------------------------------


def test_swarm_fails_on_max_handoffs() -> None:
    """A real swarm that exhausts max_handoffs terminates with FAILED, no exception.

    **Validates: Requirements 1.3**
    """
    max_handoffs = 5
    swarm = Swarm(nodes=ping_pong_agents(), max_handoffs=max_handoffs, max_iterations=20)

    result, interceptor = _run(swarm, "keep handing off forever")

    assert result.status == Status.FAILED
    assert len(result.node_history) <= max_handoffs + 1
    assert interceptor.stop_reason == "max_handoffs"


# ---------------------------------------------------------------------------
# Fact 3 — max_iterations: same node_history counter governs both limits
# ---------------------------------------------------------------------------


def test_swarm_fails_on_max_iterations() -> None:
    """max_handoffs and max_iterations compare the same len(node_history) counter.

    With max_iterations smaller than max_handoffs, the iteration limit wins.

    **Validates: Requirements 1.3**
    """
    max_iterations = 4
    swarm = Swarm(nodes=ping_pong_agents(), max_handoffs=20, max_iterations=max_iterations)

    result, interceptor = _run(swarm, "cycle all agents forever")

    assert result.status == Status.FAILED
    assert len(result.node_history) <= max_iterations + 1
    assert interceptor.stop_reason == "max_iterations"


# ---------------------------------------------------------------------------
# Fact 4 — premature exit: COMPLETED even when task is unfinished
# ---------------------------------------------------------------------------


def test_swarm_completes_on_premature_exit() -> None:
    """When an agent responds without calling handoff_to_agent, swarm → COMPLETED.

    **Validates: Requirements 1.5**
    """
    agents = [terminal_agent("a", text="Brief summary, stopping here."), *ping_pong_agents()[1:]]
    swarm = Swarm(nodes=agents, max_handoffs=20, max_iterations=20)

    result, interceptor = _run(swarm, "summarise briefly then stop")

    # SDK Fact #4: premature exit produces COMPLETED, not FAILED
    assert result.status == Status.COMPLETED
    assert len(result.node_history) == 1
    assert interceptor.stop_reason is None


# ---------------------------------------------------------------------------
# Fact 5 — StopReasonInterceptor captures non-empty reason on FAILED
# ---------------------------------------------------------------------------


def test_stop_reason_captured_on_failure() -> None:
    """Interceptor captures stop_reason from the strands logger on FAILED runs."""
    interceptor = StopReasonInterceptor()
    interceptor.attach()

    strands_logger = logging.getLogger("strands")
    strands_logger.debug("reason=<Max handoffs reached: 20> | stopping execution")

    interceptor.detach()

    assert interceptor.stop_reason == "max_handoffs"
    assert interceptor.detection_time_ms >= 0.0


# ---------------------------------------------------------------------------
# Fact 6 — No native budget enforcement: accumulated_usage grows unbounded
# ---------------------------------------------------------------------------


def test_no_native_budget_enforcement() -> None:
    """BaselineConfig has no token budget; accumulated_usage grows without termination.

    Streams a real baseline Swarm whose agents report 5 000 tokens per node and
    records ``accumulated_usage["totalTokens"]`` after every event.  The total
    must keep growing past an arbitrary threshold, and the run must end only
    because of the handoff limit, never because of tokens.

    **Validates: Requirements 1.8**
    """
    tokens_per_node = 5_000
    threshold = 20_000  # any "reasonable" budget — crossed after 5 nodes
    cfg = baseline_config()
    swarm = create_swarm(cfg, ping_pong_agents(tokens=tokens_per_node))
    assert type(swarm) is Swarm  # baseline never builds BudgetAwareSwarm

    async def _stream() -> tuple[SwarmResult, list[int]]:
        totals: list[int] = []
        final_result: SwarmResult | None = None
        async for event in swarm.stream_async("produce many tokens"):
            total = swarm.state.accumulated_usage.get("totalTokens", 0)
            if not totals or total != totals[-1]:
                totals.append(total)
            if "result" in event:
                final_result = event["result"]
        assert final_result is not None
        return final_result, totals

    interceptor = StopReasonInterceptor()
    interceptor.attach()
    try:
        result, totals = asyncio.run(_stream())
    finally:
        interceptor.detach(monotonic())

    # Usage grows monotonically, one node at a time.  (Agent metrics persist across
    # invocations and the Swarm adds each node's cumulative usage, so revisited
    # agents push the total *above* nodes × tokens — all the more unbounded.)
    assert totals == sorted(totals)
    assert len(totals) == cfg.max_handoffs + 1  # initial 0 plus one step per node
    assert totals[-1] >= cfg.max_handoffs * tokens_per_node
    # ... crosses the threshold ...
    crossed_at = next(i for i, t in enumerate(totals) if t > threshold)
    # ... and the swarm keeps executing nodes afterwards instead of stopping.
    assert len(totals) - 1 - crossed_at >= 10
    assert result.accumulated_usage.get("totalTokens", 0) > threshold

    # Termination came from the SDK handoff limit, not from any token budget.
    assert result.status == Status.FAILED
    assert len(result.node_history) == cfg.max_handoffs
    assert interceptor.stop_reason == "max_handoffs"


# ---------------------------------------------------------------------------
# Fact 5b — Intra-agent tool loop: node_history does not grow; only node_timeout stops it
# ---------------------------------------------------------------------------


def test_intra_agent_tool_loop_stops_on_node_timeout() -> None:
    """An intra-agent tool loop (repeated tool calls without handoff) does not grow
    node_history; only node_timeout stops it, in both configs.

    The Researcher calls search_knowledge_base repeatedly without ever calling
    handoff_to_agent.  Since no handoff occurs, len(node_history) stays at 0 and
    none of the handoff/iteration limits apply.  Only node_timeout fires.

    **Validates: Requirements 1.6**
    """
    from tests.unit.conftest import scenario_agents

    os.environ.setdefault("BUDGET_GUARD_MAX_TOKENS", "5000")

    for config_name in ("baseline", "guarded"):
        cfg = baseline_config() if config_name == "baseline" else guarded_config()
        config = dataclasses.replace(cfg, node_timeout=0.4, execution_timeout=30.0)
        agents = scenario_agents("tool_loop", slow_delay_s=1.0)
        swarm = create_swarm(config, agents)

        result, interceptor = _run(swarm, "call search_knowledge_base repeatedly")

        assert result.status == Status.FAILED, f"{config_name}: expected FAILED"
        assert len(result.node_history) == 0, f"{config_name}: node_history grew"
        assert interceptor.stop_reason == "node_timeout", (
            f"{config_name}: expected node_timeout, got {interceptor.stop_reason}"
        )
