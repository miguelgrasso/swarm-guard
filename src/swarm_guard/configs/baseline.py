"""Baseline swarm configuration — SDK defaults, no controls enabled."""

from __future__ import annotations

from swarm_guard.models import SwarmConfig


def baseline_config() -> SwarmConfig:
    """Return a SwarmConfig with the exact SDK defaults (no controls activated).

    These values mirror the Swarm.__init__ defaults in strands-agents 1.64.0:
    - max_handoffs=20, max_iterations=20
    - execution_timeout=900.0, node_timeout=300.0
    - repetitive_handoff_detection_window=0 (disabled)
    - repetitive_handoff_min_unique_agents=0 (disabled)
    - budget_guard_enabled=False
    """
    return SwarmConfig(
        max_handoffs=20,
        max_iterations=20,
        execution_timeout=900.0,
        node_timeout=300.0,
        repetitive_handoff_detection_window=0,
        repetitive_handoff_min_unique_agents=0,
        budget_guard_enabled=False,
        budget_guard_max_tokens=0,
        config_name="baseline",
    )
