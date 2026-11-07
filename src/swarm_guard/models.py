"""Data models for the swarm-guard benchmark.

All models use Python dataclasses with full type annotations.
Dataclasses are preferred over Pydantic to keep the unit-test stack minimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SchemaError(ValueError):
    """Raised when a scenario YAML file is missing required fields or has invalid types."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SwarmConfig:
    """Full parameter set for one swarm configuration."""

    # SDK controls
    max_handoffs: int = 20
    max_iterations: int = 20
    execution_timeout: float = 900.0
    node_timeout: float = 300.0
    repetitive_handoff_detection_window: int = 0
    repetitive_handoff_min_unique_agents: int = 0

    # Budget Guard (fifth control — custom)
    budget_guard_enabled: bool = False
    # 0 = disabled; reads from BUDGET_GUARD_MAX_TOKENS when constructing GuardedConfig
    budget_guard_max_tokens: int = 0

    # Identity
    config_name: str = "baseline"  # "baseline" | "guarded"


# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------


@dataclass
class ExpectedOutcome:
    """Expected result for one configuration in a scenario."""

    status: str  # "FAILED" | "COMPLETED"
    stop_reason: Optional[str] = None  # None when status is COMPLETED without a limit hit


@dataclass
class ScenarioDefinition:
    """Parsed representation of one adversarial YAML file."""

    name: str  # snake_case identifier, e.g. "ping_pong"
    attack_vector: str  # human-readable description of the attack
    input: str  # prompt sent to the swarm (identical for both configs)
    expected_baseline: ExpectedOutcome
    expected_guarded: ExpectedOutcome
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Run results
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Captured result of one scenario × one configuration execution."""

    scenario_name: str
    config_name: str  # "baseline" | "guarded"

    # Actual outcomes
    actual_status: str  # "FAILED" | "COMPLETED"
    actual_stop_reason: Optional[str]  # captured from strands logger; None if not detected

    # Timing (milliseconds)
    detection_time_ms: float  # swarm start → stop_reason captured; 0.0 if no match
    recovery_time_ms: float  # stop_reason captured → swarm terminated; 0.0 if no match

    # Usage
    total_handoffs: int  # len(node_history) at termination
    total_tokens: int  # accumulated_usage["totalTokens"]
    cost_usd: float  # total_tokens × TOKEN_PRICE_PER_UNIT

    # Correctness flag
    is_correct: bool  # actual matches expected for this config

    # Raw SDK metrics (Requirement 1.7): copy of SwarmResult.accumulated_metrics
    accumulated_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMetrics:
    """Per-configuration aggregate metrics computed over all scenarios in a run."""

    config_name: str
    correct_stop_rate: float  # correct results / total scenarios ∈ [0.0, 1.0]
    false_positive_rate: float  # guarded stops that baseline completed correctly ∈ [0.0, 1.0]
    total_scenarios: int
    total_correct: int


@dataclass
class BenchmarkReport:
    """Complete output of one benchmark run."""

    run_id: str  # ISO-8601 timestamp used as run identifier
    results: list[RunResult] = field(default_factory=list)
    baseline_metrics: Optional[AggregatedMetrics] = None
    guarded_metrics: Optional[AggregatedMetrics] = None
