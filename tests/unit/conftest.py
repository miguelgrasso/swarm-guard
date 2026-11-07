"""Test fixtures for swarm-guard unit tests — all offline, no network calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from strands.multiagent.base import Status
from strands.multiagent.swarm import SwarmNode, SwarmResult
from strands.types.event_loop import Metrics, Usage

# ---------------------------------------------------------------------------
# ScriptedModel
# ---------------------------------------------------------------------------


class ScriptedModel:
    """Minimal model stub that returns pre-defined text responses without network calls.

    Does NOT implement the full strands.models.Model ABC; it is only suitable for
    unit tests where the Agent is also mocked via MagicMock.  When you need a real
    agent that executes with this model, see the integration fixtures instead.
    """

    def __init__(self, responses: list[str], tokens_per_response: int = 100) -> None:
        self._responses = list(responses)
        self._index = 0
        self.tokens_per_response = tokens_per_response
        self.call_count = 0

    def next_response(self) -> str:
        """Return the next scripted response string (cycling when exhausted)."""
        if not self._responses:
            return "Done."
        text = self._responses[self._index % len(self._responses)]
        self._index += 1
        self.call_count += 1
        return text

    def reset(self) -> None:
        """Reset index back to the beginning."""
        self._index = 0
        self.call_count = 0


@pytest.fixture
def scripted_model() -> Any:
    """Factory fixture: call with responses list to get a ScriptedModel."""

    def _create(responses: list[str], tokens_per_response: int = 100) -> ScriptedModel:
        return ScriptedModel(responses, tokens_per_response)

    return _create


@pytest.fixture
def mock_provider() -> ScriptedModel:
    """ScriptedModel pre-configured for a happy-path three-agent run."""
    return ScriptedModel(
        responses=[
            "Research complete: found 3 key points about the topic.",
            "Analysis complete: identified 2 main patterns and 1 risk.",
            "Final report: The analysis shows positive trends with minor risks.",
        ],
        tokens_per_response=100,
    )


@pytest.fixture
def ping_pong_provider() -> ScriptedModel:
    """ScriptedModel that triggers the max_handoffs limit."""
    return ScriptedModel(
        responses=["Handing off to the other agent."] * 30,
        tokens_per_response=50,
    )


@pytest.fixture
def budget_exceeding_provider() -> ScriptedModel:
    """ScriptedModel that produces very high token counts to trigger BudgetGuard."""
    return ScriptedModel(
        responses=["Processing large context block..."] * 50,
        tokens_per_response=1000,
    )


# ---------------------------------------------------------------------------
# Mock SwarmResult builders
# ---------------------------------------------------------------------------


def _make_swarm_result(
    status: Status = Status.COMPLETED,
    total_tokens: int = 300,
    handoff_count: int = 0,
    latency_ms: int = 500,
) -> MagicMock:
    """Return a MagicMock shaped like SwarmResult with the given field values."""
    result: MagicMock = MagicMock(spec=SwarmResult)
    result.status = status
    result.accumulated_usage = Usage(
        inputTokens=total_tokens // 3,
        outputTokens=total_tokens - total_tokens // 3,
        totalTokens=total_tokens,
    )
    result.accumulated_metrics = Metrics(latencyMs=latency_ms)
    # node_history: list of mock SwarmNode stubs
    result.node_history = [MagicMock(spec=SwarmNode) for _ in range(handoff_count)]
    result.execution_count = handoff_count
    result.execution_time = latency_ms
    return result


@pytest.fixture
def mock_swarm_result() -> MagicMock:
    """Mock SwarmResult with COMPLETED status."""
    return _make_swarm_result(status=Status.COMPLETED, total_tokens=300, handoff_count=3)


@pytest.fixture
def mock_failed_swarm_result() -> MagicMock:
    """Mock SwarmResult with FAILED status."""
    return _make_swarm_result(status=Status.FAILED, total_tokens=1500, handoff_count=20)


# ---------------------------------------------------------------------------
# Scenario directory
# ---------------------------------------------------------------------------


@pytest.fixture
def scenario_dir() -> Path:
    """Path to the adversarial scenarios directory."""
    return Path(__file__).parent.parent.parent / "scenarios" / "adversarial"
