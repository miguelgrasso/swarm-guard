"""Consistency check: every scenario's expected stop_reason must be reachable.

The Strands SDK evaluates its termination limits in a fixed order inside
``Swarm._should_continue``::

    handoffs → iterations → repetitive_handoff

A ``stop_reason`` declared in a scenario YAML is only *reachable* for a given
config if no higher-priority limit would fire first.  For example, a
``BaselineConfig`` (``repetitive_handoff_detection_window=0``) can never
produce ``repetitive_handoff`` because the detector is disabled.

This test guards the 20 YAML files against such contradictions so a wrong
``expected_*`` value is caught offline, before any paid benchmark run.

Requirements: 4.1, 4.4, 4.5, 4.6
Design: Property 4, Property 6, § 3.6 ScenarioLoader, ADR-002, ADR-003, § 7.2
"""

from __future__ import annotations

import pytest

from swarm_guard.configs.baseline import baseline_config
from swarm_guard.configs.guarded import guarded_config
from swarm_guard.models import ScenarioDefinition, SwarmConfig
from swarm_guard.scenario_loader import load_all

EXPECTED_SCENARIO_COUNT = 20


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def reachable_stop_reasons(config: SwarmConfig) -> set[str | None]:
    """Return the set of ``stop_reason`` values a swarm with *config* can emit.

    Mirrors the SDK evaluation order ``handoffs → iterations → repetitive``:

    - ``"max_handoffs"``: always reachable (highest-priority limit).
    - ``"max_iterations"``: reachable only if ``max_iterations < max_handoffs``;
      otherwise the handoff limit always fires first.
    - ``"repetitive_handoff"``: reachable only if the detector is enabled
      (``detection_window > 0``) **and** the window can fill before the
      iteration limit (``detection_window < max_iterations``).
    - ``"budget_exceeded"``: reachable only if ``budget_guard_enabled``.
    - ``"node_timeout"``: always reachable (independent of the evaluation order).
    - ``None``: always reachable (any config may finish ``COMPLETED`` without a limit).
    """
    reachable: set[str | None] = {"max_handoffs", "node_timeout", None}

    if config.max_iterations < config.max_handoffs:
        reachable.add("max_iterations")

    window = config.repetitive_handoff_detection_window
    if window > 0 and window < config.max_iterations:
        reachable.add("repetitive_handoff")

    if config.budget_guard_enabled is True:
        reachable.add("budget_exceeded")

    return reachable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def guarded(monkeypatch: pytest.MonkeyPatch) -> SwarmConfig:
    """GuardedConfig built with ``BUDGET_GUARD_MAX_TOKENS=5000`` in the environment."""
    monkeypatch.setenv("BUDGET_GUARD_MAX_TOKENS", "5000")
    return guarded_config()


@pytest.fixture
def scenarios() -> list[ScenarioDefinition]:
    """All 20 scenarios loaded from ``scenarios/adversarial/``."""
    loaded = load_all()
    assert len(loaded) == EXPECTED_SCENARIO_COUNT, (
        f"Expected {EXPECTED_SCENARIO_COUNT} scenario files, found {len(loaded)}"
    )
    return loaded


# ---------------------------------------------------------------------------
# Tests for the helper itself
# ---------------------------------------------------------------------------


def test_reachable_stop_reasons_baseline() -> None:
    """BaselineConfig (SDK defaults) cannot reach repetitive_handoff, max_iterations or budget."""
    reachable = reachable_stop_reasons(baseline_config())
    assert reachable == {"max_handoffs", "node_timeout", None}


def test_reachable_stop_reasons_guarded(guarded: SwarmConfig) -> None:
    """GuardedConfig reaches every stop_reason."""
    reachable = reachable_stop_reasons(guarded)
    assert reachable == {
        "max_handoffs",
        "max_iterations",
        "repetitive_handoff",
        "budget_exceeded",
        "node_timeout",
        None,
    }


def test_repetitive_handoff_unreachable_when_window_exceeds_iterations() -> None:
    """A window >= max_iterations can never fill before the iteration limit fires."""
    cfg = SwarmConfig(
        max_handoffs=10,
        max_iterations=8,
        repetitive_handoff_detection_window=8,
        repetitive_handoff_min_unique_agents=3,
    )
    assert "repetitive_handoff" not in reachable_stop_reasons(cfg)


def test_max_iterations_unreachable_when_not_below_max_handoffs() -> None:
    """If max_iterations >= max_handoffs the handoff limit always fires first."""
    cfg = SwarmConfig(max_handoffs=10, max_iterations=10)
    assert "max_iterations" not in reachable_stop_reasons(cfg)


# ---------------------------------------------------------------------------
# Main consistency test over the 20 YAML files
# ---------------------------------------------------------------------------


def _collect_unreachable(
    scenarios: list[ScenarioDefinition],
    config: SwarmConfig,
    field_name: str,
) -> list[str]:
    reachable = reachable_stop_reasons(config)
    problems: list[str] = []
    for scenario in scenarios:
        expected = getattr(scenario, field_name)
        if expected.stop_reason not in reachable:
            problems.append(
                f"scenario '{scenario.name}': {field_name}.stop_reason="
                f"{expected.stop_reason!r} is unreachable for config "
                f"'{config.config_name}' (reachable: {sorted(r or 'null' for r in reachable)})"
            )
    return problems


def test_all_scenarios_stop_reasons_are_reachable(
    scenarios: list[ScenarioDefinition],
    guarded: SwarmConfig,
) -> None:
    """Every expected stop_reason must be reachable for its target config."""
    problems = _collect_unreachable(scenarios, baseline_config(), "expected_baseline")
    problems += _collect_unreachable(scenarios, guarded, "expected_guarded")

    assert not problems, "Unreachable stop_reasons found:\n  - " + "\n  - ".join(problems)


@pytest.mark.parametrize("field_name", ["expected_baseline", "expected_guarded"])
def test_each_scenario_stop_reason_reachable_per_config(
    scenarios: list[ScenarioDefinition],
    guarded: SwarmConfig,
    field_name: str,
) -> None:
    """Per-config variant that reports every offending scenario by name."""
    config = baseline_config() if field_name == "expected_baseline" else guarded
    problems = _collect_unreachable(scenarios, config, field_name)
    assert not problems, "\n".join(problems)


def test_injected_unreachable_stop_reason_is_detected(
    scenarios: list[ScenarioDefinition],
) -> None:
    """Verification criterion: a baseline `repetitive_handoff` must be flagged by name."""
    bad = ScenarioDefinition(
        name="injected_bad_scenario",
        attack_vector="synthetic",
        input="x",
        expected_baseline=scenarios[0].expected_baseline.__class__(
            status="FAILED", stop_reason="repetitive_handoff"
        ),
        expected_guarded=scenarios[0].expected_guarded,
    )
    problems = _collect_unreachable([*scenarios, bad], baseline_config(), "expected_baseline")
    assert len(problems) == 1
    assert "injected_bad_scenario" in problems[0]
    assert "repetitive_handoff" in problems[0]
