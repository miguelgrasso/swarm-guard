"""test_offline_benchmark.py — A31: the whole benchmark offline, 20 scenarios × 2 configs.

Every case builds the real three-agent Swarm (``create_swarm``) with scenario-scripted
models, runs the scenario's own ``input``, captures the stop reason the way the Runner
does, and checks ``evaluate_correctness`` against the YAML's expected outcome.

Timeout scenarios (``slow_node``, ``zombie_agent``, ``timeout_chain``) are the one place
the configs are not used verbatim: ``baseline`` waits ``node_timeout=300 s`` for real, so
the test shortens ``node_timeout`` to 0.4 s (and keeps everything else). The mechanism
under test is unchanged — the SDK's ``asyncio.timeout`` fires, the node fails, the swarm
reports FAILED and the interceptor reads ``node_timeout`` from ``exc_info``.
"""

from __future__ import annotations

import dataclasses
import os
from time import monotonic

import pytest

from swarm_guard.configs.baseline import baseline_config
from swarm_guard.configs.guarded import guarded_config
from swarm_guard.models import RunResult, ScenarioDefinition, SwarmConfig
from swarm_guard.observability.stop_reason import StopReasonInterceptor
from swarm_guard.runner import create_swarm, evaluate_correctness
from swarm_guard.scenario_loader import load_all

from .conftest import scenario_agents

TIMEOUT_SCENARIOS = {"slow_node", "zombie_agent", "timeout_chain"}
TEST_NODE_TIMEOUT_S = 0.4
SLOW_DELAY_S = 1.0
CONFIGS = ("baseline", "guarded")

_SCENARIOS = load_all()


def _config(config_name: str, scenario: ScenarioDefinition) -> SwarmConfig:
    os.environ.setdefault("BUDGET_GUARD_MAX_TOKENS", "5000")
    config = baseline_config() if config_name == "baseline" else guarded_config()
    if scenario.name in TIMEOUT_SCENARIOS:
        config = dataclasses.replace(
            config, node_timeout=TEST_NODE_TIMEOUT_S, execution_timeout=30.0
        )
    return config


def run_offline(scenario: ScenarioDefinition, config_name: str) -> RunResult:
    """One scenario × one config through a real Swarm, mirroring Runner.run_benchmark."""
    config = _config(config_name, scenario)
    swarm = create_swarm(config, scenario_agents(scenario.name, slow_delay_s=SLOW_DELAY_S))

    interceptor = StopReasonInterceptor()
    interceptor.attach()
    actual_status = "ERROR"
    actual_tokens = 0
    actual_handoffs = 0
    stop_reason_override: str | None = None
    try:
        result = swarm(scenario.input)
        actual_status = result.status.name
        actual_tokens = int(result.accumulated_usage.get("totalTokens", 0))
        actual_handoffs = len(result.node_history)
    except Exception:  # noqa: BLE001 — same contract as the Runner
        actual_status = "FAILED"
        stop_reason_override = "exception"
    finally:
        interceptor.detach(monotonic())

    run = RunResult(
        scenario_name=scenario.name,
        config_name=config_name,
        actual_status=actual_status,
        actual_stop_reason=interceptor.stop_reason or stop_reason_override,
        detection_time_ms=interceptor.detection_time_ms,
        recovery_time_ms=interceptor.recovery_time_ms,
        total_handoffs=actual_handoffs,
        total_tokens=actual_tokens,
        cost_usd=0.0,
        is_correct=False,
    )
    run.is_correct = evaluate_correctness(run, scenario, config_name)
    return run


def _expected(scenario: ScenarioDefinition, config_name: str) -> str:
    exp = scenario.expected_baseline if config_name == "baseline" else scenario.expected_guarded
    return f"{exp.status}/{exp.stop_reason}"


@pytest.mark.parametrize("config_name", CONFIGS)
@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s.name for s in _SCENARIOS])
def test_offline_run_matches_expected(scenario: ScenarioDefinition, config_name: str) -> None:
    run = run_offline(scenario, config_name)
    assert run.is_correct, (
        f"{scenario.name} [{config_name}]: expected {_expected(scenario, config_name)}, "
        f"got {run.actual_status}/{run.actual_stop_reason} "
        f"(handoffs={run.total_handoffs}, tokens={run.total_tokens})"
    )


def test_offline_benchmark_is_40_for_40() -> None:
    """The A-Checkpoint figure: all 20 scenarios × both configs correct, offline."""
    runs = [run_offline(s, c) for s in _SCENARIOS for c in CONFIGS]
    wrong = [
        f"{r.scenario_name}[{r.config_name}] -> {r.actual_status}/{r.actual_stop_reason}"
        for r in runs
        if not r.is_correct
    ]
    assert len(runs) == 40
    assert not wrong, "incorrect runs:\n  " + "\n  ".join(wrong)
