"""BudgetGuard — fifth safety control: stop the swarm when accumulated tokens exceed a threshold.

The SDK does not natively enforce any token budget.  BudgetGuard wraps the
``should_continue`` method on ``swarm.state`` (a ``SwarmState`` instance) so
that every iteration check also guards against token over-spend.

Design reference: ADR-003.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands.multiagent.swarm import Swarm

logger = logging.getLogger(__name__)


class BudgetGuard:
    """Token-budget enforcement wrapper injected into a Swarm after construction.

    When the swarm's ``accumulated_usage["totalTokens"]`` exceeds *max_tokens*,
    the guard emits ``logger.debug("budget_exceeded")`` (which the
    ``StopReasonInterceptor`` picks up) and returns ``(False, "budget_exceeded")``,
    stopping the swarm cleanly.

    Usage::

        swarm = Swarm(nodes=[...], ...)
        guard = BudgetGuard(max_tokens=5000)
        guard.inject(swarm)
        result = swarm("my task")
    """

    def __init__(self, max_tokens: int) -> None:
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be > 0, got {max_tokens}")
        self.max_tokens = max_tokens

    def inject(self, swarm: "Swarm") -> None:
        """Wrap ``swarm.state.should_continue`` with budget-aware logic.

        The original ``should_continue`` is preserved and called as a fallback
        when the budget has not been exceeded.

        Args:
            swarm: The Swarm instance to protect.  Its ``state.should_continue``
                   method is replaced on the *instance* (not the class), so other
                   Swarm instances are unaffected.
        """
        guard = self  # capture in closure
        original_should_continue = swarm.state.should_continue

        def guarded_should_continue(**kwargs: Any) -> tuple[bool, str]:
            """Budget-aware replacement for SwarmState.should_continue."""
            tokens: int = swarm.state.accumulated_usage.get("totalTokens", 0)
            if tokens > guard.max_tokens:
                logger.debug("budget_exceeded")
                return False, "budget_exceeded"
            return original_should_continue(**kwargs)

        # Bind the new callable to the state instance
        import types

        swarm.state.should_continue = types.MethodType(  # type: ignore[method-assign]  # noqa: PGH003
            lambda self, **kw: guarded_should_continue(**kw),
            swarm.state,
        )
