"""ScenarioLoader — reads and validates the 20 adversarial YAML scenario files.

Scenarios live under ``scenarios/adversarial/scenario_NN_*.yaml`` relative to
the repository root.  Each file must contain the fields:
  name, attack_vector, input, expected_baseline, expected_guarded, tags

Missing fields raise :class:`~swarm_guard.models.SchemaError` with the field
name in the message so callers can report it clearly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from swarm_guard.models import ExpectedOutcome, ScenarioDefinition, SchemaError

# Path to scenarios/adversarial/ relative to this source file
# src/swarm_guard/scenario_loader.py → ../../.. → repo root
_REPO_ROOT = Path(__file__).parent.parent.parent
SCENARIOS_DIR: Path = _REPO_ROOT / "scenarios" / "adversarial"

_REQUIRED_FIELDS = frozenset(
    {"name", "attack_vector", "input", "expected_baseline", "expected_guarded", "tags"}
)
_EXPECTED_OUTCOME_KEYS = frozenset({"status", "stop_reason"})


def load_file(path: Path) -> ScenarioDefinition:
    """Parse and validate a single scenario YAML file.

    Args:
        path: Absolute or relative path to the YAML file.

    Returns:
        A fully populated :class:`~swarm_guard.models.ScenarioDefinition`.

    Raises:
        SchemaError: If any required field is missing or has the wrong type.
        yaml.YAMLError: If the file is not valid YAML.
    """
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        got = type(raw).__name__
        raise SchemaError(f"Scenario {path.name}: expected a YAML mapping, got {got}")

    missing = _REQUIRED_FIELDS - set(raw.keys())
    if missing:
        raise SchemaError(
            f"Scenario {path.name} is missing required fields: {sorted(missing)}"
        )

    # Validate expected_baseline and expected_guarded sub-dicts
    for key in ("expected_baseline", "expected_guarded"):
        sub = raw[key]
        if not isinstance(sub, dict):
            raise SchemaError(
                f"Scenario {path.name}.{key}: expected a mapping, got {type(sub).__name__}"
            )
        sub_missing = _EXPECTED_OUTCOME_KEYS - set(sub.keys())
        if sub_missing:
            raise SchemaError(
                f"Scenario {path.name}.{key} is missing fields: {sorted(sub_missing)}"
            )

    return ScenarioDefinition(
        name=str(raw["name"]),
        attack_vector=str(raw["attack_vector"]),
        input=str(raw["input"]),
        expected_baseline=ExpectedOutcome(
            status=str(raw["expected_baseline"]["status"]),
            stop_reason=raw["expected_baseline"].get("stop_reason"),
        ),
        expected_guarded=ExpectedOutcome(
            status=str(raw["expected_guarded"]["status"]),
            stop_reason=raw["expected_guarded"].get("stop_reason"),
        ),
        tags=list(raw.get("tags") or []),
    )


def load_all(scenarios_dir: Path = SCENARIOS_DIR) -> list[ScenarioDefinition]:
    """Load all scenario YAML files in *scenarios_dir* sorted by filename.

    Args:
        scenarios_dir: Directory to scan for ``scenario_*.yaml`` files.
            Defaults to :data:`SCENARIOS_DIR`.

    Returns:
        List of :class:`~swarm_guard.models.ScenarioDefinition` in filename order.

    Raises:
        SchemaError: Propagated from :func:`load_file` with the filename prepended.
        FileNotFoundError: If *scenarios_dir* does not exist.
    """
    paths = sorted(scenarios_dir.glob("scenario_*.yaml"))
    scenarios: list[ScenarioDefinition] = []
    for p in paths:
        try:
            scenarios.append(load_file(p))
        except SchemaError as exc:
            raise SchemaError(f"[{p.name}] {exc}") from exc
    return scenarios
