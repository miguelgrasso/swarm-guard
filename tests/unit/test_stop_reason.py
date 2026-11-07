"""test_stop_reason.py — unit tests for StopReasonInterceptor."""

from __future__ import annotations

import logging
from time import monotonic

from swarm_guard.observability.stop_reason import StopReasonInterceptor

_STRANDS_LOGGER = logging.getLogger("strands")


def _emit(message: str) -> None:
    """Emit a DEBUG log record to the strands logger."""
    _STRANDS_LOGGER.debug(message)


# ---------------------------------------------------------------------------
# One test per pattern
# ---------------------------------------------------------------------------


def test_pattern_max_handoffs() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("reason=<Max handoffs reached: 20> | stopping execution")
    interceptor.detach()
    assert interceptor.stop_reason == "max_handoffs"
    assert interceptor.detection_time_ms >= 0.0


def test_pattern_max_iterations() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("reason=<Max iterations reached: 10> | stopping execution")
    interceptor.detach()
    assert interceptor.stop_reason == "max_iterations"
    assert interceptor.detection_time_ms >= 0.0


def test_pattern_repetitive_handoff() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("Repetitive handoff: 1 unique nodes out of 8 recent iterations")
    interceptor.detach()
    assert interceptor.stop_reason == "repetitive_handoff"
    assert interceptor.detection_time_ms >= 0.0


def test_pattern_budget_exceeded() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("budget_exceeded")
    interceptor.detach()
    assert interceptor.stop_reason == "budget_exceeded"
    assert interceptor.detection_time_ms >= 0.0


def test_pattern_node_timeout() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("Node 'researcher' execution timed out after 60s")
    interceptor.detach()
    assert interceptor.stop_reason == "node_timeout"
    assert interceptor.detection_time_ms >= 0.0


def test_pattern_execution_timeout() -> None:
    """The swarm-wide execution_timeout limit (should_continue) is captured too."""
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("reason=<Execution timed out: 300.0s> | stopping execution")
    interceptor.detach()
    assert interceptor.stop_reason == "execution_timeout"


def test_node_timeout_via_exc_info() -> None:
    """Real SDK path: logger.exception('node=<x> | node execution failed') with the
    timeout text only inside exc_info — exactly what strands 1.64.0 swarm.py does."""
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    try:
        raise Exception("Node 'analyst' execution timed out after 60.0s")
    except Exception:
        _STRANDS_LOGGER.exception("node=<%s> | node execution failed", "analyst")
    interceptor.detach()
    assert interceptor.stop_reason == "node_timeout"
    assert interceptor.detection_time_ms >= 0.0


def test_node_failure_without_timeout_is_still_node_timeout_pattern() -> None:
    """The SDK logs every node failure with the same message; a non-timeout exception
    in exc_info still matches the 'node execution failed' half of the pattern."""
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    record = logging.LogRecord(
        name="strands.multiagent.swarm",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg="node=<%s> | node execution failed",
        args=("writer",),
        exc_info=(RuntimeError, RuntimeError("model refused"), None),
    )
    _STRANDS_LOGGER.handle(record)
    interceptor.detach()
    assert interceptor.stop_reason == "node_timeout"


# ---------------------------------------------------------------------------
# No match → stop_reason is None
# ---------------------------------------------------------------------------


def test_no_match_returns_none() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("current_node=<researcher>, iteration=<1> | executing node")
    interceptor.detach()
    assert interceptor.stop_reason is None
    assert interceptor.detection_time_ms == 0.0
    assert interceptor.recovery_time_ms == 0.0


# ---------------------------------------------------------------------------
# Handler removed after detach
# ---------------------------------------------------------------------------


def test_handler_removed_after_detach() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    handler_before = interceptor._handler
    assert handler_before in _STRANDS_LOGGER.handlers

    interceptor.detach()

    assert handler_before not in _STRANDS_LOGGER.handlers
    assert interceptor._handler is None


# ---------------------------------------------------------------------------
# Only first match stored (subsequent messages ignored)
# ---------------------------------------------------------------------------


def test_only_first_match_stored() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("Max handoffs reached: 20")
    _emit("Max iterations reached: 20")  # should be ignored
    interceptor.detach()
    assert interceptor.stop_reason == "max_handoffs"


# ---------------------------------------------------------------------------
# recovery_time_ms is non-negative
# ---------------------------------------------------------------------------


def test_recovery_time_non_negative() -> None:
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    _emit("budget_exceeded")
    end = monotonic() + 0.01  # simulate small delay
    interceptor.detach(end)
    assert interceptor.recovery_time_ms >= 0.0
