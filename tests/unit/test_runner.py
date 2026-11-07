"""test_runner.py — offline tests for run_benchmark (A26, Requirements 1.7, 3.7).

Runs the real Runner end-to-end against a ScriptedModel so no network is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from swarm_guard import runner
from swarm_guard.models import SchemaError
from swarm_guard.scenario_loader import load_file
from tests.unit.conftest import ScriptedModel, handoff_response, terminal_response

_TOKENS_PER_CALL = 100


class CountingModel(ScriptedModel):
    """ScriptedModel that counts model invocations so token totals can be predicted."""

    def __init__(self, responses: list[Any]) -> None:
        super().__init__(responses)
        self.calls = 0

    def _next_response(self) -> Any:
        self.calls += 1
        return super()._next_response()


@pytest.fixture
def offline_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> CountingModel:
    """Patch the model provider with a happy-path ScriptedModel and isolate output."""
    model = CountingModel(
        responses=[
            handoff_response("analyst", tokens=_TOKENS_PER_CALL),
            handoff_response("writer", tokens=_TOKENS_PER_CALL),
            terminal_response("Final report.", tokens=_TOKENS_PER_CALL),
        ]
    )
    monkeypatch.setattr(runner, "build_model_provider", lambda: model)
    monkeypatch.setenv("BENCHMARK_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("TOKEN_PRICE_PER_UNIT", "0.000001")
    monkeypatch.delenv("SWARM_CONFIG", raising=False)
    return model


def test_run_benchmark_propagates_tokens_and_metrics(offline_runner: CountingModel) -> None:
    """Requirement 1.7 / Property 11: total_tokens and accumulated_metrics come from the SDK."""
    report = runner.run_benchmark(["baseline"], scenario_names=["happy_path"])

    assert len(report.results) == 1
    rr = report.results[0]
    assert rr.actual_status == "COMPLETED"
    # Every scripted model call reports exactly _TOKENS_PER_CALL tokens, so the
    # swarm-level total must equal calls × tokens — no attribute access involved.
    assert offline_runner.calls > 0
    assert rr.total_tokens == offline_runner.calls * _TOKENS_PER_CALL
    assert rr.accumulated_metrics, "accumulated_metrics must be populated"
    assert "latencyMs" in rr.accumulated_metrics
    assert rr.cost_usd == pytest.approx(rr.total_tokens * 0.000001)


def test_run_benchmark_reads_swarm_config_env(
    offline_runner: ScriptedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement 3.7: SWARM_CONFIG selects the config when config_names is omitted."""
    monkeypatch.setenv("SWARM_CONFIG", "baseline")
    report = runner.run_benchmark(scenario_names=["happy_path"])
    assert [r.config_name for r in report.results] == ["baseline"]
    assert report.baseline_metrics is not None
    assert report.guarded_metrics is None


@pytest.mark.parametrize("value", ["", "production"])
def test_run_benchmark_rejects_bad_swarm_config(
    offline_runner: ScriptedModel, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SWARM_CONFIG", value)
    with pytest.raises(SystemExit) as excinfo:
        runner.run_benchmark(scenario_names=["happy_path"])
    assert excinfo.value.code == 1


def test_run_benchmark_aborts_when_fewer_than_20_scenarios(
    offline_runner: ScriptedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "load_all", lambda: [])
    with pytest.raises(SystemExit) as excinfo:
        runner.run_benchmark(["baseline"])
    assert excinfo.value.code == 1


def test_run_benchmark_exception_records_stop_reason(
    offline_runner: ScriptedModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashing swarm yields actual_stop_reason='exception', never None."""

    class _Boom:
        def __call__(self, *_: Any, **__: Any) -> Any:
            raise RuntimeError("synthetic failure")

    monkeypatch.setattr(runner, "create_swarm", lambda config, agents: _Boom())
    report = runner.run_benchmark(["baseline"], scenario_names=["happy_path"])
    rr = report.results[0]
    assert rr.actual_status == "FAILED"
    assert rr.actual_stop_reason == "exception"
    assert rr.total_tokens == 0
    assert rr.accumulated_metrics == {}


def test_load_file_wraps_yaml_errors(tmp_path: Path) -> None:
    bad = tmp_path / "scenario_99_bad.yaml"
    bad.write_text("name: [unclosed\nattack_vector: x\n", encoding="utf-8")
    with pytest.raises(SchemaError) as excinfo:
        load_file(bad)
    assert "scenario_99_bad.yaml" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
