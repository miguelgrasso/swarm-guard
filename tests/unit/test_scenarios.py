"""test_scenarios.py — validates the 20 adversarial YAML scenario files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from swarm_guard.models import SchemaError
from swarm_guard.scenario_loader import load_all, load_file

# Expected scenario names from the design table (in order)
_EXPECTED_NAMES = [
    "happy_path",
    "ping_pong",
    "infinite_chain",
    "slow_node",
    "premature_exit",
    "self_handoff",
    "unknown_agent",
    "context_inflation",
    "shared_context_injection",
    "impossible_task",
    "tool_loop",
    "zombie_agent",
    "privilege_escalation",
    "memory_poisoning",
    "cascade_backtrack",
    "data_exfiltration",
    "self_delegation_loop",
    "role_conflict",
    "malformed_json",
    "timeout_chain",
]


# ---------------------------------------------------------------------------
# All 20 scenarios load
# ---------------------------------------------------------------------------


def test_all_20_scenarios_load() -> None:
    scenarios = load_all()
    assert len(scenarios) == 20, f"Expected 20 scenarios, got {len(scenarios)}"


# ---------------------------------------------------------------------------
# Missing required field raises SchemaError with field name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    ["name", "attack_vector", "input", "expected_baseline", "expected_guarded", "tags"],
)
def test_missing_field_raises_schema_error(missing_field: str, tmp_path: Path) -> None:
    valid: dict[str, object] = {
        "name": "test_scenario",
        "attack_vector": "test attack",
        "input": "test input",
        "expected_baseline": {"status": "COMPLETED", "stop_reason": None},
        "expected_guarded": {"status": "COMPLETED", "stop_reason": None},
        "tags": ["test"],
    }
    del valid[missing_field]

    yaml_file = tmp_path / "scenario_99_test.yaml"
    yaml_file.write_text(yaml.dump(valid), encoding="utf-8")

    with pytest.raises(SchemaError) as exc_info:
        load_file(yaml_file)

    assert missing_field in str(exc_info.value)


# ---------------------------------------------------------------------------
# Scenario names match design table exactly
# ---------------------------------------------------------------------------


def test_scenario_names_match_design() -> None:
    scenarios = load_all()
    actual_names = [s.name for s in scenarios]
    assert actual_names == _EXPECTED_NAMES, (
        f"Scenario names mismatch.\n"
        f"Expected: {_EXPECTED_NAMES}\n"
        f"Actual:   {actual_names}"
    )


# ---------------------------------------------------------------------------
# No real credentials in any YAML file
# ---------------------------------------------------------------------------


def test_no_real_credentials_in_scenarios() -> None:
    """Scenario files must not contain real ARNs or AWS access key IDs."""
    scenario_dir = Path(__file__).parent.parent.parent / "scenarios" / "adversarial"
    arn_pattern = re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:")
    key_pattern = re.compile(r"AKIA[0-9A-Z]{16}")

    for yaml_file in scenario_dir.glob("scenario_*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        assert not arn_pattern.search(content), (
            f"{yaml_file.name} contains a real ARN"
        )
        assert not key_pattern.search(content), (
            f"{yaml_file.name} contains a real AWS access key"
        )


# ---------------------------------------------------------------------------
# Expected status values are valid
# ---------------------------------------------------------------------------


def test_expected_status_values_are_valid() -> None:
    valid_statuses = {"COMPLETED", "FAILED"}
    scenarios = load_all()
    for s in scenarios:
        assert s.expected_baseline.status in valid_statuses, (
            f"{s.name}: invalid baseline status {s.expected_baseline.status!r}"
        )
        assert s.expected_guarded.status in valid_statuses, (
            f"{s.name}: invalid guarded status {s.expected_guarded.status!r}"
        )


# ---------------------------------------------------------------------------
# Scenario 08 has different stop_reason per config (key design property)
# ---------------------------------------------------------------------------


def test_scenario_08_differs_between_configs() -> None:
    """context_inflation must differ: baseline=max_handoffs, guarded=budget_exceeded.

    Baseline is max_handoffs (not max_iterations) because the SDK evaluates handoffs
    before iterations; with 20/20 the handoff limit always wins (design.md table, A24).
    """
    scenarios = load_all()
    s08 = next(s for s in scenarios if s.name == "context_inflation")
    assert s08.expected_baseline.stop_reason == "max_handoffs"
    assert s08.expected_guarded.stop_reason == "budget_exceeded"


# ---------------------------------------------------------------------------
# Valid YAML with all fields loads without error
# ---------------------------------------------------------------------------


def test_valid_yaml_loads_correctly(tmp_path: Path) -> None:
    data = {
        "name": "my_test",
        "attack_vector": "synthetic attack",
        "input": "do something adversarial",
        "expected_baseline": {"status": "FAILED", "stop_reason": "max_handoffs"},
        "expected_guarded": {"status": "FAILED", "stop_reason": "max_handoffs"},
        "tags": ["test", "synthetic"],
    }
    yaml_file = tmp_path / "scenario_99_my_test.yaml"
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    scenario = load_file(yaml_file)
    assert scenario.name == "my_test"
    assert scenario.expected_baseline.stop_reason == "max_handoffs"
    assert scenario.tags == ["test", "synthetic"]
