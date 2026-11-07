"""StopReasonInterceptor — captures the stop reason from the Strands SDK debug logger.

The Strands Swarm SDK exposes stop reasons exclusively via ``logger.debug(...)``
messages on the ``strands.multiagent.swarm`` logger (a child of ``"strands"``).
No public API exists for this value.  This interceptor adds a custom handler to
``logging.getLogger("strands")`` *before* each swarm execution and removes it
*after*, capturing the reason and measuring detection / recovery timings.

Design reference: ADR-002.

Verified log message patterns against strands-agents 1.64.0 source
(``strands/multiagent/swarm.py``):
  - "Max handoffs reached: <N>"                       (should_continue, line ~212)
  - "Max iterations reached: <N>"                     (should_continue, line ~216)
  - "Execution timed out: <N>s"                       (should_continue, line ~221)
  - "Repetitive handoff: <N> unique nodes out of <M> recent iterations"  (line ~231)
  - "budget_exceeded"                                 (emitted by BudgetGuard)
  - node timeout: the SDK raises ``Exception("Node '<name>' execution timed out after
    <N>s")`` and logs it with ``logger.exception("node=<%s> | node execution failed")``.
    The timeout text therefore lives in ``record.exc_info``, not in
    ``record.getMessage()``; the interceptor inspects both.

The limit messages are wrapped as ``"reason=<...> | stopping execution"`` by the
swarm loop; the patterns match on substrings so the wrapper is irrelevant.
"""

from __future__ import annotations

import logging
import re
from time import monotonic
from typing import Optional


class StopReasonInterceptor:
    """Attach to the Strands logger, capture the first stop-reason message.

    Lifecycle::

        interceptor = StopReasonInterceptor()
        interceptor.attach()       # before swarm.run(...)
        try:
            result = swarm(task)
        finally:
            swarm_end = monotonic()
            interceptor.detach(swarm_end)

        print(interceptor.stop_reason)         # "max_handoffs" | "max_iterations" | ...
        print(interceptor.detection_time_ms)   # ms from swarm start to first match
        print(interceptor.recovery_time_ms)    # ms from first match to swarm end
    """

    # Ordered list of (pattern_name, compiled_regex). Each regex is searched in
    # ``record.getMessage()`` and, when present, in ``str(record.exc_info[1])``.
    PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("max_handoffs", re.compile(r"Max handoffs reached:")),
        ("max_iterations", re.compile(r"Max iterations reached:")),
        ("execution_timeout", re.compile(r"Execution timed out:")),
        (
            "repetitive_handoff",
            re.compile(r"Repetitive handoff: \d+ unique nodes out of \d+"),
        ),
        ("budget_exceeded", re.compile(r"budget_exceeded")),
        (
            "node_timeout",
            re.compile(r"execution timed out after|node execution failed"),
        ),
    ]

    def __init__(self) -> None:
        self.stop_reason: Optional[str] = None
        self.detection_time_ms: float = 0.0
        self.recovery_time_ms: float = 0.0

        self._start_time: float = 0.0
        self._detection_time: Optional[float] = None
        self._handler: Optional[logging.Handler] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(self) -> None:
        """Add a handler to ``logging.getLogger("strands")`` and record start time."""
        self.stop_reason = None
        self.detection_time_ms = 0.0
        self.recovery_time_ms = 0.0
        self._detection_time = None

        self._start_time = monotonic()

        handler = logging.Handler()
        handler.emit = self._on_record  # type: ignore[method-assign]

        strands_logger = logging.getLogger("strands")
        strands_logger.addHandler(handler)
        # Ensure DEBUG messages reach us even if the root logger is set higher
        if strands_logger.level == logging.NOTSET or strands_logger.level > logging.DEBUG:
            strands_logger.setLevel(logging.DEBUG)

        self._handler = handler

    def detach(self, swarm_end_time: Optional[float] = None) -> None:
        """Remove the handler and compute recovery_time_ms.

        Args:
            swarm_end_time: monotonic() timestamp when swarm execution ended.
                If None, monotonic() is called internally.
        """
        if self._handler is None:
            return

        logging.getLogger("strands").removeHandler(self._handler)
        self._handler = None

        end_time = swarm_end_time if swarm_end_time is not None else monotonic()

        if self._detection_time is not None:
            self.recovery_time_ms = (end_time - self._detection_time) * 1000.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_record(self, record: logging.LogRecord) -> None:
        """Called for every log record; matches against known stop-reason patterns."""
        if self._detection_time is not None:
            # Already captured a reason — ignore subsequent messages
            return

        text = record.getMessage()
        # logger.exception(...) puts the raised exception in exc_info; the SDK's
        # node-timeout text travels there, so search it as well.
        exc_info = record.exc_info
        if exc_info is not None and exc_info[1] is not None:
            text = f"{text}\n{exc_info[1]}"
        for pattern_name, pattern in self.PATTERNS:
            if pattern.search(text):
                self._detection_time = monotonic()
                self.stop_reason = pattern_name
                self.detection_time_ms = (self._detection_time - self._start_time) * 1000.0
                return
