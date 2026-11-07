"""test_budget_guard.py — unit tests for BudgetAwareSwarm with real Swarm (no mocks).

All tests use ScriptedModel from conftest.py and real Swarm/BudgetAwareSwarm
instances. No mocks are used for the Swarm itself — the tests exercise the
actual stream_async override and token accumulation logic.

Requirements: 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import logging
from time import monotonic

import pytest
from strands import Agent
from strands.multiagent.swarm import Swarm

from swarm_guard.budget_guard import BudgetAwareSwarm
from swarm_guard.configs.baseline import baseline_config
from swarm_guard.configs.guarded import guarded_config
from swarm_guard.observability.stop_reason import StopReasonInterceptor
from swarm_guard.runner import create_swarm

# Import test helpers from conftest — same package
from tests.unit.conftest import (  # type: ignore[import-not-found]
    ScriptedModel,
    terminal_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_simple_agents() -> list[Agent]:
    """Create minimal agents for SwarmFactory type-check tests.

    Each agent has its own ScriptedModel instance so they don't share state.
    """
    return [
        Agent(
            model=ScriptedModel([terminal_response("Done.")]),
            system_prompt="Test agent A",
            name="a",
        ),
        Agent(
            model=ScriptedModel([terminal_response("Done.")]),
            system_prompt="Test agent B",
            name="b",
        ),
    ]


def _run_with_interceptor(swarm: BudgetAwareSwarm, prompt: str) -> str | None:
    """Run a BudgetAwareSwarm and return the captured stop_reason.

    BudgetAwareSwarm may raise ValueError when it halts early (no result event
    is produced); this is expected and caught.
    """
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    try:
        swarm(prompt)
    except Exception:
        # Budget exceeded halts the generator before the result event,
        # causing invoke_async to raise ValueError — expected behavior.
        pass
    finally:
        swarm_end = monotonic()
        interceptor.detach(swarm_end)
    return interceptor.stop_reason


# ---------------------------------------------------------------------------
# Test 1 — BudgetAwareSwarm stops above threshold
# ---------------------------------------------------------------------------


def test_budget_aware_swarm_stops_above_threshold() -> None:
    """BudgetAwareSwarm halts with stop_reason='budget_exceeded' when tokens exceed threshold.

    **Validates: Requirements 3.4, 3.6**
    """
    # Single agent produces a terminal text response with 2000 tokens.
    # With max_tokens=1500, the budget is exceeded after the first response
    # (2000 > 1500). The BudgetAwareSwarm checks accumulated_usage after each
    # event from stream_async — the MultiAgentNodeStopEvent triggers the check.
    agent_a = Agent(
        model=ScriptedModel([terminal_response("Large response.", tokens=2000)]),
        system_prompt="Agent A",
        name="a",
    )

    swarm = BudgetAwareSwarm(
        nodes=[agent_a],
        max_handoffs=20,
        max_iterations=20,
        max_tokens=1500,
    )

    stop_reason = _run_with_interceptor(swarm, "test prompt that triggers budget")
    assert stop_reason == "budget_exceeded"


# ---------------------------------------------------------------------------
# Test 2 — BudgetAwareSwarm allows below threshold
# ---------------------------------------------------------------------------


def test_budget_aware_swarm_allows_below_threshold() -> None:
    """BudgetAwareSwarm does NOT emit budget_exceeded when tokens stay below threshold.

    **Validates: Requirements 3.4**
    """
    # Single agent with a low-token terminal response (50 tokens).
    # With max_tokens=10000, the budget is never exceeded.
    agent_a = Agent(
        model=ScriptedModel([terminal_response("Task complete.", tokens=50)]),
        system_prompt="Agent A",
        name="a",
    )

    swarm = BudgetAwareSwarm(
        nodes=[agent_a],
        max_handoffs=10,
        max_iterations=10,
        max_tokens=10000,
    )

    stop_reason = _run_with_interceptor(swarm, "simple task")
    assert stop_reason != "budget_exceeded"


# ---------------------------------------------------------------------------
# Test 3 — BudgetAwareSwarm emits debug log
# ---------------------------------------------------------------------------


def test_budget_guard_emits_debug_log(caplog: pytest.LogCaptureFixture) -> None:
    """BudgetAwareSwarm emits 'budget_exceeded' debug log when threshold exceeded.

    **Validates: Requirements 3.4, 3.6**
    """
    agent_a = Agent(
        model=ScriptedModel([terminal_response("Large response.", tokens=2000)]),
        system_prompt="Agent A",
        name="a",
    )

    swarm = BudgetAwareSwarm(
        nodes=[agent_a],
        max_handoffs=20,
        max_iterations=20,
        max_tokens=1500,
    )

    with caplog.at_level(logging.DEBUG, logger="strands"):
        try:
            swarm("trigger budget")
        except Exception:
            # Expected ValueError when budget is exceeded
            pass

    assert any("budget_exceeded" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Test 4 — Baseline config does NOT produce BudgetAwareSwarm
# ---------------------------------------------------------------------------


def test_baseline_does_not_inject_budget_guard() -> None:
    """create_swarm with BaselineConfig returns Swarm, not BudgetAwareSwarm.

    **Validates: Requirements 3.5**
    """
    cfg = baseline_config()
    assert cfg.budget_guard_enabled is False

    agents = _make_simple_agents()
    swarm = create_swarm(cfg, agents)

    assert isinstance(swarm, Swarm)
    assert not isinstance(swarm, BudgetAwareSwarm)


# ---------------------------------------------------------------------------
# Test 5 — Guarded config produces BudgetAwareSwarm
# ---------------------------------------------------------------------------


def test_create_swarm_guarded_returns_budget_aware_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_swarm with GuardedConfig returns BudgetAwareSwarm.

    **Validates: Requirements 3.3, 3.4**
    """
    monkeypatch.setenv("BUDGET_GUARD_MAX_TOKENS", "5000")

    cfg = guarded_config()
    assert cfg.budget_guard_enabled is True

    agents = _make_simple_agents()
    swarm = create_swarm(cfg, agents)

    assert isinstance(swarm, BudgetAwareSwarm)
