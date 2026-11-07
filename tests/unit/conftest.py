"""Test fixtures for swarm-guard unit tests — all offline, no network calls.

Provides a ``ScriptedModel`` that fully implements ``strands.models.Model`` so
that a real ``Swarm`` instance can execute without any network calls.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from strands import Agent
from strands.models.model import Model
from strands.multiagent.base import Status
from strands.multiagent.swarm import SwarmNode, SwarmResult
from strands.types.content import Messages, SystemContentBlock
from strands.types.event_loop import Metrics, Usage
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------


@dataclass
class Response:
    """Describes one scripted model turn.

    Either ``text`` (terminal text reply) or ``tool_name`` / ``tool_input``
    (tool-use reply) must be provided.  Both may not be None simultaneously.
    """

    text: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    tokens: int = 100


# ---------------------------------------------------------------------------
# ScriptedModel — full implementation of strands.models.Model
# ---------------------------------------------------------------------------


class ScriptedModel(Model):
    """Offline model that replays ``Response`` objects without any network calls.

    Implements the ``strands.models.Model`` ABC completely so a real ``Swarm``
    instance can execute without mocking the ``Agent`` object itself.

    The model cycles through its response list; once exhausted it repeats the
    last entry.
    """

    def __init__(self, responses: list[Response]) -> None:
        self._responses: list[Response] = list(responses)
        self._index: int = 0

    # ------------------------------------------------------------------
    # Model ABC — configuration methods
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Return minimal model configuration required by the SDK."""
        return {"model_id": "scripted-model"}

    def update_config(self, **kwargs: Any) -> None:
        """No-op: scripted model has no configurable runtime parameters."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_response(self) -> Response:
        """Return the next ``Response``, cycling when the list is exhausted."""
        if not self._responses:
            return Response(text="Done.")
        resp = self._responses[self._index % len(self._responses)]
        # Advance index but clamp to last entry once exhausted
        if self._index < len(self._responses) - 1:
            self._index += 1
        return resp

    # ------------------------------------------------------------------
    # stream — the key method
    # ------------------------------------------------------------------

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: Any = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, Any] | None = None,
        cancel_signal: threading.Event | None = None,
        agent_metadata: Any = None,
        structured_output_model: Any = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:  # pragma: no cover – type annotation only
        resp = self._next_response()
        half = max(1, resp.tokens // 2)

        yield {"messageStart": {"role": "assistant"}}

        if resp.tool_name is not None:
            # --- tool-use response ---
            tool_use_id = str(uuid.uuid4())[:8]
            tool_input_json = json.dumps(resp.tool_input)

            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {
                        "toolUse": {
                            "toolUseId": tool_use_id,
                            "name": resp.tool_name,
                        }
                    },
                }
            }
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": tool_input_json}},
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "tool_use"}}

        else:
            # --- text response ---
            text = resp.text or "Done."

            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": text},
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}

        yield {
            "metadata": {
                "usage": Usage(
                    inputTokens=half,
                    outputTokens=half,
                    totalTokens=resp.tokens,
                ),
                "metrics": Metrics(latencyMs=10),
            }
        }

    # ------------------------------------------------------------------
    # structured_output — minimal async-generator stub
    # ------------------------------------------------------------------

    async def structured_output(
        self,
        output_model: Any,
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:  # pragma: no cover
        """Minimal stub: not exercised by unit tests."""
        yield {"output": None}


class CyclingScriptedModel(ScriptedModel):
    """ScriptedModel that wraps around to the first response once exhausted.

    A Swarm node only ends when the agent closes its turn with a text reply, so a
    node that hands off needs two model calls: ``handoff_to_agent`` and then a
    terminal text.  Cycling lets the same agent repeat that pair on every visit,
    which is how the "infinite handoff" scenarios are scripted offline.
    """

    def _next_response(self) -> Response:
        if not self._responses:
            return Response(text="Done.")
        resp = self._responses[self._index % len(self._responses)]
        self._index += 1
        return resp


# ---------------------------------------------------------------------------
# Response helper functions (not fixtures — plain callables)
# ---------------------------------------------------------------------------


def handoff_response(target_agent: str, tokens: int = 100) -> Response:
    """Create a tool-use ``Response`` that calls ``handoff_to_agent``."""
    return Response(
        tool_name="handoff_to_agent",
        tool_input={
            "agent_name": target_agent,
            "message": f"Handing off to {target_agent}.",
        },
        tokens=tokens,
    )


def terminal_response(text: str = "Task complete.", tokens: int = 100) -> Response:
    """Create a text ``Response`` with no tool call (terminal node)."""
    return Response(text=text, tokens=tokens)


def token_heavy_response(n: int) -> Response:
    """Create a text ``Response`` carrying ``n`` tokens (for BudgetGuard tests)."""
    return Response(text=f"Large response with {n} synthetic tokens.", tokens=n)


# ---------------------------------------------------------------------------
# Agent builders for real-Swarm tests (plain callables, no network)
# ---------------------------------------------------------------------------


def handoff_agent(name: str, target: str, tokens: int = 100) -> Agent:
    """Agent that hands off to ``target`` every time it is invoked.

    Each visit costs exactly ``tokens`` total tokens: the handoff call carries
    them and the closing text reply reports zero, so per-node accounting is exact.
    """
    model = CyclingScriptedModel(
        [
            handoff_response(target, tokens=tokens),
            terminal_response(f"Handed off to {target}.", tokens=0),
        ]
    )
    return Agent(model=model, name=name, system_prompt=f"Agent {name}", callback_handler=None)


def terminal_agent(name: str, text: str = "Task complete.", tokens: int = 100) -> Agent:
    """Agent that answers with text and never hands off (premature exit)."""
    return Agent(
        model=ScriptedModel([terminal_response(text, tokens=tokens)]),
        name=name,
        system_prompt=f"Agent {name}",
        callback_handler=None,
    )


def ping_pong_agents(tokens: int = 100) -> list[Agent]:
    """Two agents that hand off to each other forever (a → b → a → ...).

    Note: the SDK's ``Agent`` metrics accumulate across invocations, and the Swarm
    adds each node result's cumulative usage to its own total.  A revisited agent
    therefore contributes more than ``tokens`` on later visits.  Use
    :func:`chain_agents` when exact per-node token accounting matters.
    """
    return [handoff_agent("a", "b", tokens=tokens), handoff_agent("b", "a", tokens=tokens)]


def chain_agents(count: int, tokens: int = 100) -> list[Agent]:
    """``count`` distinct agents n0 → n1 → ... → n(count-1); the last one is terminal.

    Every agent is visited at most once, so each node adds exactly ``tokens`` to
    the swarm's ``accumulated_usage["totalTokens"]``.
    """
    agents = [handoff_agent(f"n{i}", f"n{i + 1}", tokens=tokens) for i in range(count - 1)]
    agents.append(terminal_agent(f"n{count - 1}", text="End of chain.", tokens=tokens))
    return agents


# ---------------------------------------------------------------------------
# A31 — scenario-aware scripts for the offline 40-run benchmark
# ---------------------------------------------------------------------------


class SlowScriptedModel(CyclingScriptedModel):
    """ScriptedModel that sleeps ``delay_s`` before answering.

    With a ``node_timeout`` shorter than ``delay_s`` the SDK cancels the node through
    its real path (``asyncio.timeout`` → ``Exception("Node '<name>' execution timed out
    after <N>s")`` → ``logger.exception("node=<%s> | node execution failed")``), which is
    exactly what ``StopReasonInterceptor`` must capture as ``node_timeout``.
    """

    def __init__(self, responses: list[Response], delay_s: float = 1.0) -> None:
        super().__init__(responses)
        self.delay_s = delay_s

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterable[StreamEvent]:
        import asyncio

        await asyncio.sleep(self.delay_s)
        async for event in super().stream(*args, **kwargs):
            yield event


def _script(*responses: Response, slow: bool = False, delay_s: float = 1.0) -> ScriptedModel:
    if slow:
        return SlowScriptedModel(list(responses), delay_s=delay_s)
    return CyclingScriptedModel(list(responses))


def scenario_agents(
    scenario_name: str, *, tokens: int = 100, slow_delay_s: float = 1.0
) -> list[Agent]:
    """Build the three real agents (researcher, analyst, writer) scripted for one scenario.

    The script encodes how an LLM would *behave* under each adversarial prompt, so a
    real ``Swarm`` reproduces the expected stop reason offline:

    - pipeline ``researcher → analyst → writer`` (COMPLETED): happy_path, premature_exit and
      the vectors the Swarm cannot detect (design §7.4)
    - ping-pong ``researcher ↔ analyst``: ping_pong, cascade_backtrack, malformed_json,
      self_delegation_loop
    - three-agent cycle ``researcher → analyst → writer → researcher``: infinite_chain,
      tool_loop (with a tool call first), role_conflict, context_inflation (heavy tokens)
    - self_handoff: researcher → researcher; unknown_agent: researcher → "supervisor"
    - slow_node / zombie_agent / timeout_chain: one or all agents answer after ``slow_delay_s``
    """
    from swarm_guard.agents.analyst import build_analyst
    from swarm_guard.agents.researcher import build_researcher
    from swarm_guard.agents.writer import build_writer

    h, t = handoff_response, terminal_response
    done = t("Done.", tokens=0)

    def pipeline(tok: int = tokens) -> tuple[ScriptedModel, ScriptedModel, ScriptedModel]:
        return (
            _script(h("analyst", tok), done),
            _script(h("writer", tok), done),
            _script(t("Final report.", tok)),
        )

    def ping_pong() -> tuple[ScriptedModel, ScriptedModel, ScriptedModel]:
        return (
            _script(h("analyst", tokens), done),
            _script(h("researcher", tokens), done),
            _script(t("Writer idle.", tokens)),
        )

    def cycle(
        tok: int = tokens, *, tool_first: bool = False
    ) -> tuple[ScriptedModel, ScriptedModel, ScriptedModel]:
        first: list[Response] = []
        if tool_first:
            first.append(
                Response(
                    tool_name="search_knowledge_base", tool_input={"query": "data"}, tokens=tok
                )
            )
        return (
            _script(*first, h("analyst", tok), done),
            _script(h("writer", tok), done),
            _script(h("researcher", tok), done),
        )

    scripts: dict[str, tuple[ScriptedModel, ScriptedModel, ScriptedModel]] = {
        "happy_path": pipeline(),
        "premature_exit": (
            _script(t("Brief research only; stopping.", tokens)),
            _script(done),
            _script(done),
        ),
        "shared_context_injection": pipeline(),
        "impossible_task": pipeline(),
        "privilege_escalation": pipeline(),
        "memory_poisoning": pipeline(),
        "data_exfiltration": pipeline(),
        "ping_pong": ping_pong(),
        "cascade_backtrack": ping_pong(),
        "malformed_json": ping_pong(),
        "self_delegation_loop": ping_pong(),
        "infinite_chain": cycle(),
        "tool_loop": cycle(tool_first=True),
        "role_conflict": cycle(),
        "context_inflation": cycle(tok=1000),
        "self_handoff": (_script(h("researcher", tokens), done), _script(done), _script(done)),
        "unknown_agent": (
            _script(
                h("supervisor", tokens),
                t("No supervisor available; answering directly.", tokens),
            ),
            _script(done),
            _script(done),
        ),
        "slow_node": (
            _script(h("analyst", tokens), done, slow=True, delay_s=slow_delay_s),
            _script(h("writer", tokens), done),
            _script(t("Final report.", tokens)),
        ),
        "zombie_agent": (
            _script(h("analyst", tokens), done),
            _script(h("writer", tokens), done, slow=True, delay_s=slow_delay_s),
            _script(t("Final report.", tokens)),
        ),
        "timeout_chain": (
            _script(h("analyst", tokens), done, slow=True, delay_s=slow_delay_s),
            _script(h("writer", tokens), done, slow=True, delay_s=slow_delay_s),
            _script(t("Final report.", tokens), slow=True, delay_s=slow_delay_s),
        ),
    }
    if scenario_name not in scripts:
        raise KeyError(f"No offline script for scenario {scenario_name!r}")
    r, a, w = scripts[scenario_name]
    return [build_researcher(r), build_analyst(a), build_writer(w)]


# ---------------------------------------------------------------------------
# Fixture: scripted_model factory
# ---------------------------------------------------------------------------


@pytest.fixture
def scripted_model() -> Any:
    """Factory fixture: call with a list of Response objects to get a ScriptedModel."""

    def _create(responses: list[Response], tokens_per_response: int = 100) -> ScriptedModel:  # noqa: ARG001
        return ScriptedModel(responses)

    return _create


# ---------------------------------------------------------------------------
# Pre-built ScriptedModel fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider() -> ScriptedModel:
    """ScriptedModel pre-configured for a happy-path three-agent run.

    Sequence: researcher → analyst → writer (terminal).
    """
    return ScriptedModel(
        responses=[
            handoff_response("analyst", tokens=100),
            handoff_response("writer", tokens=100),
            terminal_response("Final report: analysis shows positive trends.", tokens=100),
        ]
    )


@pytest.fixture
def ping_pong_provider() -> ScriptedModel:
    """ScriptedModel with 30 handoff responses cycling between two agents."""
    return ScriptedModel(
        responses=[handoff_response("analyst" if i % 2 == 0 else "researcher") for i in range(30)]
    )


@pytest.fixture
def budget_exceeding_provider() -> ScriptedModel:
    """ScriptedModel with 50 token-heavy responses (1000 tokens each)."""
    return ScriptedModel(responses=[token_heavy_response(1000) for _ in range(50)])


# ---------------------------------------------------------------------------
# Mock SwarmResult fixtures
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
# Scenario directory fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def scenario_dir() -> Path:
    """Path to the adversarial scenarios directory."""
    return Path(__file__).parent.parent.parent / "scenarios" / "adversarial"
