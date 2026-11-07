"""BudgetAwareSwarm — fifth safety control: stop the swarm when tokens exceed a threshold.

The SDK does not natively enforce any token budget.  ``BudgetAwareSwarm`` subclasses
``Swarm`` and overrides ``stream_async`` to check the token accumulator after each
event.  The override survives the per-invocation ``SwarmState`` reset because it
lives on the class, not on the state instance.

Design reference: ADR-003.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from strands.agent.invocation_context import InvocationContext
from strands.multiagent.swarm import Swarm
from strands.types.multiagent import MultiAgentInput

logger = logging.getLogger("strands")


class BudgetAwareSwarm(Swarm):
    """Swarm subclass that enforces a token budget on every iteration.

    Overrides ``stream_async`` to check accumulated token usage after each event.
    The override survives the per-invocation ``SwarmState`` reset because it lives
    on the class, not on the state instance.

    When total tokens exceed ``max_tokens``, emits ``logger.debug("budget_exceeded")``
    (captured by ``StopReasonInterceptor``) and stops the async generator.

    Usage::

        swarm = BudgetAwareSwarm(
            nodes=[researcher, analyst, writer],
            max_handoffs=10,
            max_iterations=8,
            max_tokens=5000,
        )
        result = swarm("my task")
    """

    def __init__(self, *args: Any, max_tokens: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._max_tokens = max_tokens

    async def stream_async(
        self,
        task: MultiAgentInput,
        invocation_state: dict[str, Any] | None = None,
        *,
        invocation_context: InvocationContext | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield events from the parent stream, halting when the token budget is exceeded.

        After each event, checks ``self.state.accumulated_usage.get("totalTokens", 0)``.
        When the total exceeds ``self._max_tokens``, emits
        ``logger.debug("budget_exceeded")`` and returns, stopping the generator.
        """
        async for event in super().stream_async(
            task,
            invocation_state,
            invocation_context=invocation_context,
            **kwargs,
        ):
            tokens = self.state.accumulated_usage.get("totalTokens", 0)
            if tokens > self._max_tokens:
                logger.debug("budget_exceeded")
                return
            yield event
