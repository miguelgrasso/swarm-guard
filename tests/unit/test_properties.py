"""test_properties.py — property-based tests (Hypothesis) for P1–P8.

All tests run offline without network calls or AWS credentials.
Each property uses @settings(max_examples=100).

P1, P2, P3 and P7 drive a *real* ``Swarm`` / ``BudgetAwareSwarm`` with the
``ScriptedModel`` helpers from conftest — no mocks over ``Swarm``,
``SwarmResult`` or ``SwarmState``.  Their input ranges are kept small so each
example executes in milliseconds.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
from time import monotonic
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from strands.multiagent.base import Status
from strands.multiagent.swarm import Swarm, SwarmResult

from swarm_guard.budget_guard import BudgetAwareSwarm
from swarm_guard.configs.baseline import baseline_config
from swarm_guard.models import (
    RunResult,
    SwarmConfig,
)
from swarm_guard.observability.emf import EMFEmitter
from swarm_guard.observability.stop_reason import StopReasonInterceptor
from swarm_guard.runner import create_swarm
from swarm_guard.scenario_loader import load_file
from tests.unit.conftest import chain_agents, handoff_agent, ping_pong_agents, terminal_agent

# Real swarm runs take longer than Hypothesis' default 200 ms deadline.
_SWARM_SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


def _run_intercepted(swarm: Swarm, task: str) -> tuple[SwarmResult | None, StopReasonInterceptor]:
    """Run a real swarm with the StopReasonInterceptor attached.

    ``BudgetAwareSwarm`` halts its generator before the result event, which makes
    ``invoke_async`` raise ``ValueError``; that is expected and yields ``None``.
    """
    interceptor = StopReasonInterceptor()
    interceptor.attach()
    result: SwarmResult | None = None
    try:
        result = swarm(task)
    except ValueError:
        pass
    finally:
        interceptor.detach(monotonic())
    return result, interceptor


# ---------------------------------------------------------------------------
# P1 — Limit Enforcement Monotonicity
# ---------------------------------------------------------------------------


@_SWARM_SETTINGS
@given(st.integers(min_value=1, max_value=10))
def test_p1_limit_enforcement_monotonicity(n: int) -> None:
    """For any N in [1, 10], a real swarm with max_handoffs=N and agents that hand
    off forever terminates with FAILED and len(node_history) <= N + 1.

    **Validates: Requirements 1.3 — Correctness Property P1**
    """
    swarm = Swarm(nodes=ping_pong_agents(), max_handoffs=n, max_iterations=n + 10)

    result, interceptor = _run_intercepted(swarm, "hand off forever")

    assert result is not None
    assert result.status == Status.FAILED
    assert len(result.node_history) <= n + 1
    assert interceptor.stop_reason == "max_handoffs"


# ---------------------------------------------------------------------------
# P2 — Budget Guard Threshold Monotonicity
# ---------------------------------------------------------------------------


@_SWARM_SETTINGS
@given(
    st.integers(min_value=1, max_value=1000),
    st.integers(min_value=100, max_value=500),
)
def test_p2_budget_guard_threshold_monotonicity(threshold: int, tokens_per_step: int) -> None:
    """A real BudgetAwareSwarm whose nodes each add ``tokens_per_step`` tokens stops
    with ``budget_exceeded`` before total_tokens exceeds threshold + tokens_per_step.

    Uses a chain of distinct agents (each visited once) so every node adds exactly
    ``tokens_per_step``; the chain is long enough that the budget always trips
    before the chain ends (threshold / tokens_per_step <= 10 < 12 nodes).

    **Validates: Requirements 3.4 — Correctness Property P2**
    """
    chain_length = 12
    swarm = BudgetAwareSwarm(
        nodes=chain_agents(chain_length, tokens=tokens_per_step),
        max_handoffs=chain_length + 1,
        max_iterations=chain_length + 1,
        max_tokens=threshold,
    )

    result, interceptor = _run_intercepted(swarm, "burn tokens")

    total = swarm.state.accumulated_usage.get("totalTokens", 0)
    assert result is None  # the guard halted the stream before the result event
    assert interceptor.stop_reason == "budget_exceeded"
    assert total > threshold
    assert total <= threshold + tokens_per_step
    # The guard fired before the chain (and the SDK handoff limit) could end the run.
    assert len(swarm.state.node_history) < chain_length


# ---------------------------------------------------------------------------
# P3 — Stop Reason Always Populated on FAILED
# ---------------------------------------------------------------------------


@_SWARM_SETTINGS
@given(
    st.sampled_from(["max_handoffs", "max_iterations"]),
    st.integers(min_value=1, max_value=5),
)
def test_p3_stop_reason_always_populated_on_failed(binding_limit: str, limit: int) -> None:
    """For any low SDK limit that makes a real swarm FAIL, the interceptor captures a
    non-empty actual_stop_reason that names that limit.

    **Validates: Requirements 2.x — Correctness Property P3**
    """
    if binding_limit == "max_handoffs":
        swarm = Swarm(nodes=ping_pong_agents(), max_handoffs=limit, max_iterations=limit + 5)
    else:
        swarm = Swarm(nodes=ping_pong_agents(), max_handoffs=limit + 5, max_iterations=limit)

    result, interceptor = _run_intercepted(swarm, "hand off until a limit stops you")

    assert result is not None
    assert result.status == Status.FAILED
    assert interceptor.stop_reason is not None
    assert interceptor.stop_reason != ""
    assert interceptor.stop_reason == binding_limit


# ---------------------------------------------------------------------------
# P4 — Scenario YAML Schema Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    st.fixed_dictionaries({
        "name": st.from_regex(r"[a-z][a-z0-9_]{1,30}", fullmatch=True),
        "attack_vector": st.text(min_size=1, max_size=200),
        "input": st.text(min_size=1, max_size=200),
        "expected_baseline": st.fixed_dictionaries({
            "status": st.sampled_from(["COMPLETED", "FAILED"]),
            "stop_reason": st.one_of(st.none(), st.sampled_from([
                "max_handoffs", "max_iterations", "node_timeout",
                "repetitive_handoff", "budget_exceeded",
            ])),
        }),
        "expected_guarded": st.fixed_dictionaries({
            "status": st.sampled_from(["COMPLETED", "FAILED"]),
            "stop_reason": st.one_of(st.none(), st.sampled_from([
                "max_handoffs", "max_iterations", "node_timeout",
                "repetitive_handoff", "budget_exceeded",
            ])),
        }),
        "tags": st.lists(st.text(min_size=1, max_size=20), max_size=5),
    })
)
def test_p4_scenario_yaml_schema_completeness_valid(doc: dict[str, object]) -> None:
    """Valid YAML documents conforming to the schema are accepted by load_file."""
    import tempfile
    from pathlib import Path

    import yaml

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(doc, f, allow_unicode=True)
        tmp_path = Path(f.name)

    try:
        scenario = load_file(tmp_path)
        assert scenario.name == str(doc["name"])
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# P5 — EMF Dimension Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    st.text(min_size=1, max_size=30),
    st.text(min_size=1, max_size=50),
    st.one_of(st.none(), st.text(min_size=1, max_size=30)),
)
def test_p5_emf_dimension_completeness(
    config: str, scenario_name: str, stop_reason: str | None
) -> None:
    """EMF record always contains all three dimension keys with non-empty values,
    and declares exactly two dimension sets: the full per-run set and the
    aggregation-friendly ``["config"]`` set, both in the same record.

    **Validates: Requirements 5.3**
    """
    run_result = RunResult(
        scenario_name=scenario_name,
        config_name=config,
        actual_status="COMPLETED",
        actual_stop_reason=stop_reason,
        detection_time_ms=0.0,
        recovery_time_ms=0.0,
        total_handoffs=0,
        total_tokens=0,
        cost_usd=0.0,
        is_correct=True,
    )

    captured = io.StringIO()
    import builtins
    original_print = builtins.print

    def capture_print(*args: object, **kwargs: object) -> None:
        if args:
            captured.write(str(args[0]))

    builtins.print = capture_print
    try:
        EMFEmitter.emit(run_result)
    finally:
        builtins.print = original_print

    record = json.loads(captured.getvalue())

    # Top-level dimension keys must be present and non-empty
    assert "config" in record and record["config"]
    assert "scenario" in record and record["scenario"]
    assert "stop_reason" in record and record["stop_reason"]

    # Dimension keys must appear in the _aws metadata
    # Exactly two dimension sets, in the same record: full detail + ["config"]
    dims = record["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
    assert dims == [["config", "scenario", "stop_reason"], ["config"]]
    assert len(dims) == 2
    assert len(dims[0]) == 3
    assert len(dims[1]) == 1
    # Only one CloudWatchMetrics entry — both sets live in a single record
    assert len(record["_aws"]["CloudWatchMetrics"]) == 1


# ---------------------------------------------------------------------------
# P6 — CostPerRun Non-Negativity
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.floats(min_value=0.0001, allow_nan=False, allow_infinity=False),
)
def test_p6_cost_per_run_non_negativity(total_tokens: int, price: float) -> None:
    """CostPerRun is always >= 0.0 for any non-negative token count and positive price.

    **Validates: Requirements 5.4 — Correctness Property P6**
    """
    run_result = RunResult(
        scenario_name="test",
        config_name="guarded",
        actual_status="COMPLETED",
        actual_stop_reason=None,
        detection_time_ms=0.0,
        recovery_time_ms=0.0,
        total_handoffs=0,
        total_tokens=total_tokens,
        cost_usd=0.0,
        is_correct=True,
    )

    captured = io.StringIO()
    import builtins
    original_print = builtins.print

    def capture_print(*args: object, **kwargs: object) -> None:
        if args:
            captured.write(str(args[0]))

    builtins.print = capture_print
    try:
        with patch.dict(os.environ, {"TOKEN_PRICE_PER_UNIT": str(price)}):
            EMFEmitter.emit(run_result)
    finally:
        builtins.print = original_print

    record = json.loads(captured.getvalue())
    assert record["CostPerRun"] >= 0.0


# ---------------------------------------------------------------------------
# P7 — Baseline Never Activates Budget Guard
# ---------------------------------------------------------------------------


@_SWARM_SETTINGS
@given(st.integers(min_value=1_000, max_value=1_000_000))
def test_p7_baseline_never_activates_budget_guard(tokens_per_node: int) -> None:
    """A real swarm built from BaselineConfig never stops with ``budget_exceeded``,
    however many tokens its nodes report.

    Three-node chain (researcher → analyst → writer) where every node reports
    ``tokens_per_node`` tokens; the run must COMPLETE with the full total.

    **Validates: Requirements 3.5 — Correctness Property P7 / design Property 9**
    """
    cfg = baseline_config()
    assert cfg.budget_guard_enabled is False

    agents = [
        handoff_agent("researcher", "analyst", tokens=tokens_per_node),
        handoff_agent("analyst", "writer", tokens=tokens_per_node),
        terminal_agent("writer", text="Final report.", tokens=tokens_per_node),
    ]
    swarm = create_swarm(cfg, agents)
    assert not isinstance(swarm, BudgetAwareSwarm)

    result, interceptor = _run_intercepted(swarm, "write a report")

    assert result is not None
    assert result.status == Status.COMPLETED
    assert len(result.node_history) == 3
    assert result.accumulated_usage.get("totalTokens", 0) == 3 * tokens_per_node
    assert interceptor.stop_reason != "budget_exceeded"
    assert interceptor.stop_reason is None


# ---------------------------------------------------------------------------
# P8 — Config Round-Trip Stability
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    st.integers(min_value=1, max_value=100),
    st.integers(min_value=1, max_value=100),
    st.floats(min_value=1.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=600.0, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=50),
    st.integers(min_value=0, max_value=10),
    st.booleans(),
    st.integers(min_value=0, max_value=100_000),
    st.sampled_from(["baseline", "guarded"]),
)
def test_p8_config_round_trip_stability(
    max_handoffs: int,
    max_iterations: int,
    execution_timeout: float,
    node_timeout: float,
    rep_window: int,
    rep_min_unique: int,
    budget_enabled: bool,
    budget_max_tokens: int,
    config_name: str,
) -> None:
    """Serialise SwarmConfig to dict and back; result must equal original."""
    original = SwarmConfig(
        max_handoffs=max_handoffs,
        max_iterations=max_iterations,
        execution_timeout=execution_timeout,
        node_timeout=node_timeout,
        repetitive_handoff_detection_window=rep_window,
        repetitive_handoff_min_unique_agents=rep_min_unique,
        budget_guard_enabled=budget_enabled,
        budget_guard_max_tokens=budget_max_tokens,
        config_name=config_name,
    )
    as_dict = dataclasses.asdict(original)
    rebuilt = SwarmConfig(**as_dict)
    assert original == rebuilt


# ---------------------------------------------------------------------------
# Design P16 — Compare Script Produces Valid Markdown
# ---------------------------------------------------------------------------

_STOP_REASONS = [
    "max_handoffs",
    "max_iterations",
    "node_timeout",
    "repetitive_handoff",
    "budget_exceeded",
]


def _run_result_strategy(config_name: str) -> st.SearchStrategy[RunResult]:
    """``st.builds(RunResult, ...)`` with realistic field ranges for one config."""
    return st.builds(
        RunResult,
        scenario_name=st.from_regex(r"[a-z][a-z0-9_]{1,30}", fullmatch=True),
        config_name=st.just(config_name),
        actual_status=st.sampled_from(["COMPLETED", "FAILED"]),
        actual_stop_reason=st.one_of(st.none(), st.sampled_from(_STOP_REASONS)),
        detection_time_ms=st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
        recovery_time_ms=st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
        total_handoffs=st.integers(min_value=0, max_value=1_000),
        total_tokens=st.integers(min_value=0, max_value=10_000_000),
        cost_usd=st.floats(min_value=0.0, max_value=1e3, allow_nan=False),
        is_correct=st.booleans(),
        accumulated_metrics=st.just({}),
    )


@settings(max_examples=100)
@given(
    st.lists(_run_result_strategy("baseline"), min_size=1, max_size=25),
    st.lists(_run_result_strategy("guarded"), min_size=1, max_size=25),
)
def test_design_p16_compare_script_produces_valid_markdown(
    baseline_results: list[RunResult], guarded_results: list[RunResult]
) -> None:
    """For any two non-empty lists of RunResult, ``format_findings_table`` returns a
    Markdown table with a header row, a separator row and one data row per unique
    scenario_name present in either list.

    **Validates: Requirements 6.2 — Design Property 16**
    """
    from scripts.compare_runs import TABLE_HEADER, TABLE_SEPARATOR, format_findings_table

    output = format_findings_table(baseline_results, guarded_results)
    lines = output.splitlines()

    expected_scenarios = {r.scenario_name for r in baseline_results} | {
        r.scenario_name for r in guarded_results
    }

    # Header + separator + one data row per unique scenario, nothing else.
    assert len(lines) == 2 + len(expected_scenarios)
    assert lines[0] == TABLE_HEADER
    assert lines[1] == TABLE_SEPARATOR

    n_columns = TABLE_HEADER.count("|") - 1
    assert TABLE_SEPARATOR.count("|") - 1 == n_columns

    data_rows = lines[2:]
    row_scenarios = []
    for row in data_rows:
        assert row.startswith("| ") and row.endswith(" |")
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == n_columns
        assert all(cells), f"empty cell in row: {row!r}"
        row_scenarios.append(cells[0])

    # Exactly one row per unique scenario, sorted for a stable diff of docs/findings.md.
    assert row_scenarios == sorted(expected_scenarios)
