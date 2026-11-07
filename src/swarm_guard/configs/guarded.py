"""Guarded swarm configuration — all four SDK controls enabled plus BudgetGuard."""

from __future__ import annotations

import os

from swarm_guard.models import SwarmConfig


class ConfigurationError(ValueError):
    """Raised when a required environment variable for GuardedConfig is missing or invalid."""


def guarded_config() -> SwarmConfig:
    """Return a SwarmConfig with all four SDK controls enabled and BudgetGuard active.

    Reads BUDGET_GUARD_MAX_TOKENS from the environment. Raises ConfigurationError
    if the variable is absent or set to zero (which would disable the budget guard).

    Environment variables:
        BUDGET_GUARD_MAX_TOKENS: positive integer token threshold (required)
    """
    raw = os.environ.get("BUDGET_GUARD_MAX_TOKENS", "0")
    try:
        max_tokens = int(raw)
    except ValueError:
        raise ConfigurationError(
            f"BUDGET_GUARD_MAX_TOKENS must be a positive integer, got: {raw!r}"
        )

    if max_tokens == 0:
        raise ConfigurationError(
            "BUDGET_GUARD_MAX_TOKENS must be set and > 0 for GuardedConfig. "
            "Set it in your environment (e.g. export BUDGET_GUARD_MAX_TOKENS=5000) "
            "or in .env."
        )

    return SwarmConfig(
        max_handoffs=10,
        max_iterations=10,
        execution_timeout=300.0,
        node_timeout=60.0,
        repetitive_handoff_detection_window=8,
        repetitive_handoff_min_unique_agents=3,
        budget_guard_enabled=True,
        budget_guard_max_tokens=max_tokens,
        config_name="guarded",
    )
