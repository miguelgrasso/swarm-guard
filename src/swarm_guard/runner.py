"""Runner — main benchmark orchestrator and SwarmFactory.

Loads adversarial scenarios, executes each against both configurations,
captures stop reasons, emits EMF metrics, and serialises results to JSON.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from strands import Agent
from strands.models.model import Model
from strands.multiagent.swarm import Swarm

from swarm_guard.budget_guard import BudgetAwareSwarm
from swarm_guard.configs.baseline import baseline_config
from swarm_guard.configs.guarded import ConfigurationError, guarded_config
from swarm_guard.models import (
    AggregatedMetrics,
    BenchmarkReport,
    RunResult,
    ScenarioDefinition,
    SwarmConfig,
)
from swarm_guard.observability.emf import EMFEmitter
from swarm_guard.observability.stop_reason import StopReasonInterceptor
from swarm_guard.scenario_loader import load_all

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SwarmFactory
# ---------------------------------------------------------------------------


def create_swarm(config: SwarmConfig, agents: list[Agent]) -> Swarm:
    """Build a Swarm from *config* and *agents*, using BudgetAwareSwarm if enabled.

    Args:
        config: Full parameter set for this configuration.
        agents: List of Agent instances to include in the swarm.

    Returns:
        Configured Swarm, or BudgetAwareSwarm (a Swarm subclass) when
        ``config.budget_guard_enabled`` is True.
    """
    if config.budget_guard_enabled:
        return BudgetAwareSwarm(
            nodes=agents,
            max_handoffs=config.max_handoffs,
            max_iterations=config.max_iterations,
            execution_timeout=config.execution_timeout,
            node_timeout=config.node_timeout,
            repetitive_handoff_detection_window=config.repetitive_handoff_detection_window,
            repetitive_handoff_min_unique_agents=config.repetitive_handoff_min_unique_agents,
            max_tokens=config.budget_guard_max_tokens,
        )

    return Swarm(
        nodes=agents,
        max_handoffs=config.max_handoffs,
        max_iterations=config.max_iterations,
        execution_timeout=config.execution_timeout,
        node_timeout=config.node_timeout,
        repetitive_handoff_detection_window=config.repetitive_handoff_detection_window,
        repetitive_handoff_min_unique_agents=config.repetitive_handoff_min_unique_agents,
    )


# ---------------------------------------------------------------------------
# Model provider
# ---------------------------------------------------------------------------


def build_model_provider() -> Model:
    """Instantiate the model backend from MODEL_PROVIDER env var.

    Supported values:
      - ``bedrock`` (default): Amazon Bedrock in us-east-2
      - ``ollama``: local Ollama instance (mechanical validation only)

    Returns:
        Configured Model instance.
    """
    provider = os.environ.get("MODEL_PROVIDER", "bedrock").lower()

    if provider == "ollama":
        try:
            import importlib

            ollama_mod = importlib.import_module("strands.models.ollama")
            OllamaModel = ollama_mod.OllamaModel
            return OllamaModel(host="http://localhost:11434")  # type: ignore[no-any-return]
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                "OllamaModel not available. Install strands-agents with Ollama extras "
                "or set MODEL_PROVIDER=bedrock."
            ) from exc

    # Default: Bedrock
    from strands.models import BedrockModel

    model_id = os.environ.get("BEDROCK_MODEL_ID") or None
    kwargs: dict[str, Any] = {"region_name": "us-east-2"}
    if model_id:
        kwargs["model_id"] = model_id
    return BedrockModel(**kwargs)


def build_agents(model: Model) -> list[Agent]:
    """Instantiate the three benchmark agents with *model*.

    Args:
        model: Shared model backend for all agents.

    Returns:
        List [researcher, analyst, writer].
    """
    from swarm_guard.agents.analyst import build_analyst
    from swarm_guard.agents.researcher import build_researcher
    from swarm_guard.agents.writer import build_writer

    return [build_researcher(model), build_analyst(model), build_writer(model)]


# ---------------------------------------------------------------------------
# Correctness evaluation
# ---------------------------------------------------------------------------


def evaluate_correctness(
    run_result: RunResult,
    scenario: ScenarioDefinition,
    config_name: str,
) -> bool:
    """Return True when *run_result* matches the expected outcome in *scenario*.

    Args:
        run_result: Actual execution result.
        scenario: Scenario definition with expected outcomes.
        config_name: ``"baseline"`` or ``"guarded"``.

    Returns:
        True if status and stop_reason both match the expected values.
    """
    expected = (
        scenario.expected_baseline if config_name == "baseline" else scenario.expected_guarded
    )

    status_match = run_result.actual_status == expected.status
    reason_match = run_result.actual_stop_reason == expected.stop_reason
    return status_match and reason_match


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def compute_aggregates(
    results: list[RunResult],
    config_name: str,
    baseline_results: list[RunResult] | None = None,
) -> AggregatedMetrics:
    """Compute per-configuration aggregate metrics.

    Args:
        results: All RunResult objects for *config_name*.
        config_name: ``"baseline"`` or ``"guarded"``.
        baseline_results: Baseline results used to compute FalsePositiveRate.
            Required when *config_name* is ``"guarded"``.

    Returns:
        AggregatedMetrics for this configuration.
    """
    config_results = [r for r in results if r.config_name == config_name]
    total = len(config_results)
    correct = sum(1 for r in config_results if r.is_correct)
    correct_rate = correct / total if total > 0 else 0.0

    # FalsePositiveRate: guarded stopped (FAILED) where baseline correctly completed (COMPLETED)
    false_positives = 0
    if config_name == "guarded" and baseline_results:
        baseline_completed = {
            r.scenario_name
            for r in baseline_results
            if r.config_name == "baseline" and r.actual_status == "COMPLETED" and r.is_correct
        }
        for r in config_results:
            if r.scenario_name in baseline_completed and r.actual_status == "FAILED":
                false_positives += 1
    fpr = false_positives / total if total > 0 else 0.0

    return AggregatedMetrics(
        config_name=config_name,
        correct_stop_rate=correct_rate,
        false_positive_rate=fpr,
        total_scenarios=total,
        total_correct=correct,
    )


# ---------------------------------------------------------------------------
# Cost helper
# ---------------------------------------------------------------------------


def compute_cost(total_tokens: int) -> float:
    """Return cost in USD for *total_tokens* using TOKEN_PRICE_PER_UNIT env var.

    Returns 0.0 if the env var is absent (EMFEmitter will log the warning).
    """
    raw = os.environ.get("TOKEN_PRICE_PER_UNIT")
    if raw is None:
        return 0.0
    try:
        return max(0.0, total_tokens * float(raw))
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_config(config_name: str) -> SwarmConfig:
    """Return a SwarmConfig for *config_name*.

    Args:
        config_name: ``"baseline"`` or ``"guarded"``.

    Returns:
        Corresponding SwarmConfig.

    Raises:
        ValueError: For unknown config names.
        ConfigurationError: If guarded config is missing env vars.
    """
    if config_name == "baseline":
        return baseline_config()
    if config_name == "guarded":
        return guarded_config()
    raise ValueError(f"Unknown config name: {config_name!r}. Choose 'baseline' or 'guarded'.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


MIN_SCENARIOS = 20
_VALID_CONFIG_NAMES = ("baseline", "guarded")


def resolve_config_names(config_names: list[str] | None) -> list[str]:
    """Return the configs to run, falling back to the ``SWARM_CONFIG`` env var.

    Requirement 3.7: when *config_names* is not passed explicitly, the active
    configuration is read from ``SWARM_CONFIG`` (``baseline`` or ``guarded``).

    Raises:
        ValueError: If neither source provides a valid config name.
    """
    if config_names:
        return list(config_names)

    raw = os.environ.get("SWARM_CONFIG", "").strip().lower()
    if not raw:
        raise ValueError(
            "No configuration selected: pass config_names or set SWARM_CONFIG "
            "to 'baseline' or 'guarded'."
        )
    if raw not in _VALID_CONFIG_NAMES:
        raise ValueError(
            f"Invalid SWARM_CONFIG={raw!r}. Accepted values: {list(_VALID_CONFIG_NAMES)}."
        )
    return [raw]


def run_benchmark(
    config_names: list[str] | None = None,
    scenario_names: list[str] | None = None,
) -> BenchmarkReport:
    """Execute the benchmark for each config × scenario combination.

    Args:
        config_names: List of config names to run (``["baseline"]``,
            ``["guarded"]``, or ``["baseline", "guarded"]``). When omitted,
            the single config named by the ``SWARM_CONFIG`` env var is used.
        scenario_names: If provided, only run scenarios whose ``name`` field
            matches one of these strings.

    Returns:
        Complete BenchmarkReport with all RunResults and aggregated metrics.
    """
    try:
        config_names = resolve_config_names(config_names)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Load and optionally filter scenarios
    all_scenarios = load_all()
    if len(all_scenarios) < MIN_SCENARIOS:
        print(
            f"Expected at least {MIN_SCENARIOS} adversarial scenarios, "
            f"found {len(all_scenarios)} in scenarios/adversarial/. Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)

    if scenario_names is not None:
        filtered = [s for s in all_scenarios if s.name in scenario_names]
        if not filtered:
            valid = [s.name for s in all_scenarios]
            msg = f"No matching scenarios for {scenario_names}. Valid names: {valid}"
            print(msg, file=sys.stderr)
            sys.exit(1)
        scenarios = filtered
    else:
        scenarios = all_scenarios

    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = BenchmarkReport(run_id=run_id)

    for config_name in config_names:
        try:
            config = load_config(config_name)
        except ConfigurationError as exc:
            print(f"Configuration error for '{config_name}': {exc}", file=sys.stderr)
            sys.exit(1)

        try:
            model = build_model_provider()
            agents = build_agents(model)
            swarm = create_swarm(config, agents)
        except Exception as exc:
            logger.error("Failed to build swarm for config '%s': %s", config_name, exc)
            raise

        for scenario in scenarios:
            interceptor = StopReasonInterceptor()
            interceptor.attach()

            actual_status = "ERROR"
            actual_tokens = 0
            actual_handoffs = 0
            actual_metrics: dict[str, Any] = {}
            stop_reason_override: str | None = None

            try:
                result = swarm(scenario.input)
                actual_status = result.status.name
                # Requirement 1.7: accumulated_usage / accumulated_metrics are dicts
                actual_tokens = int(result.accumulated_usage.get("totalTokens", 0))
                actual_metrics = dict(result.accumulated_metrics or {})
                actual_handoffs = len(result.node_history)
            except Exception as exc:
                logger.exception(
                    "Swarm execution failed for scenario '%s' config '%s': %s",
                    scenario.name,
                    config_name,
                    exc,
                )
                actual_status = "FAILED"
                stop_reason_override = "exception"
            finally:
                swarm_end = monotonic()
                interceptor.detach(swarm_end)

            run_result = RunResult(
                scenario_name=scenario.name,
                config_name=config_name,
                actual_status=actual_status,
                # The interceptor's capture wins: BudgetAwareSwarm and node timeouts
                # surface as exceptions too, but their real cause is already recorded.
                actual_stop_reason=interceptor.stop_reason or stop_reason_override,
                detection_time_ms=interceptor.detection_time_ms,
                recovery_time_ms=interceptor.recovery_time_ms,
                total_handoffs=actual_handoffs,
                total_tokens=actual_tokens,
                cost_usd=compute_cost(actual_tokens),
                is_correct=False,  # set below after construction
                accumulated_metrics=actual_metrics,
            )
            run_result.is_correct = evaluate_correctness(run_result, scenario, config_name)

            EMFEmitter.emit(run_result)
            report.results.append(run_result)

    # Aggregate metrics
    baseline_results = [r for r in report.results if r.config_name == "baseline"]
    if "baseline" in config_names:
        report.baseline_metrics = compute_aggregates(report.results, "baseline")
    if "guarded" in config_names:
        report.guarded_metrics = compute_aggregates(
            report.results, "guarded", baseline_results=baseline_results
        )

    # Emit aggregate EMF records
    if report.baseline_metrics:
        EMFEmitter.emit_aggregate(report.baseline_metrics)
    if report.guarded_metrics:
        EMFEmitter.emit_aggregate(report.guarded_metrics)

    # Write JSON output
    output_dir = Path(os.environ.get("BENCHMARK_OUTPUT_DIR", "./results"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"benchmark_{run_id}.json"
    output_path.write_text(
        json.dumps(dataclasses.asdict(report), indent=2, default=str), encoding="utf-8"
    )
    logger.info("Results written to %s", output_path)

    # Print summary
    _print_summary(report)

    return report


def _print_summary(report: BenchmarkReport) -> None:
    """Print a human-readable summary of the benchmark run."""
    print(f"\n{'='*60}")
    print(f"swarm-guard benchmark  run_id={report.run_id}")
    print(f"{'='*60}")
    for metrics in (report.baseline_metrics, report.guarded_metrics):
        if metrics is None:
            continue
        print(
            f"  [{metrics.config_name:8s}]  "
            f"scenarios={metrics.total_scenarios}  "
            f"correct={metrics.total_correct}  "
            f"CorrectStopRate={metrics.correct_stop_rate:.3f}  "
            f"FalsePositiveRate={metrics.false_positive_rate:.3f}"
        )
    print(f"{'='*60}\n")
