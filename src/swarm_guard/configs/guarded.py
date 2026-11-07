"""Guarded swarm configuration — all SDK controls active plus Budget Guard.

Requirements: 3.2, 3.3, 3.6
"""

from __future__ import annotations

import os

from swarm_guard.models import SwarmConfig


class ConfigurationError(ValueError):
    """Raised when a required configuration value is missing or invalid."""


def guarded_config() -> SwarmConfig:
    """Return a SwarmConfig with all controls activated.

    Reads BUDGET_GUARD_MAX_TOKENS from the environment.
    Raises ConfigurationError if the variable is absent or set to 0.

    SDK controls:
    - max_handoffs=10, max_iterations=8
    - execution_timeout=300.0, node_timeout=60.0
    - repetitive_handoff_detection_window=6
    - repetitive_handoff_min_unique_agents=3

    Budget Guard:
    - budget_guard_enabled=True
    - budget_guard_max_tokens read from BUDGET_GUARD_MAX_TOKENS env var
    """
    budget_guard_max_tokens = int(os.environ.get("BUDGET_GUARD_MAX_TOKENS", "0"))

    if budget_guard_max_tokens == 0:
        raise ConfigurationError(
            "BUDGET_GUARD_MAX_TOKENS environment variable must be set to a positive integer. "
            "A value of 0 means the variable was not configured."
        )

    return SwarmConfig(
        max_handoffs=10,
        max_iterations=8,
        execution_timeout=300.0,
        node_timeout=60.0,
        repetitive_handoff_detection_window=6,
        repetitive_handoff_min_unique_agents=3,
        budget_guard_enabled=True,
        budget_guard_max_tokens=budget_guard_max_tokens,
        config_name="guarded",
    )
