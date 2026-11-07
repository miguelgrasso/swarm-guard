"""EMFEmitter — emits CloudWatch Embedded Metrics Format (EMF) records to stdout.

The CloudWatch Agent picks up these JSON lines from stdout and publishes them
as native CloudWatch metrics in the ``SwarmGuard`` namespace.

EMF spec reference:
  https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from swarm_guard.models import AggregatedMetrics, RunResult

logger = logging.getLogger(__name__)

_NAMESPACE = "SwarmGuard"
_DIMENSIONS = [["config", "scenario", "stop_reason"]]


def _get_token_price() -> Optional[float]:
    """Read TOKEN_PRICE_PER_UNIT from the environment.

    Returns:
        Price as float, or None if the variable is absent or invalid.
    """
    raw = os.environ.get("TOKEN_PRICE_PER_UNIT")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("TOKEN_PRICE_PER_UNIT=%r is not a valid float; defaulting to 0.0", raw)
        return None


def _timestamp_ms() -> int:
    """Return current time as Unix milliseconds."""
    return int(time.time() * 1000)


class EMFEmitter:
    """Emit CloudWatch EMF JSON records to stdout.

    All methods are class methods — no instance state is needed.
    """

    @classmethod
    def emit(cls, run_result: RunResult) -> None:
        """Emit per-scenario metrics for one RunResult.

        Metrics emitted: DetectionTime, RecoveryTime, CostPerRun,
        TotalHandoffs, TotalTokens.

        Args:
            run_result: The result of one scenario × configuration execution.
        """
        price = _get_token_price()
        if price is None:
            logger.warning(
                "TOKEN_PRICE_PER_UNIT not set in environment; emitting CostPerRun=0.0"
            )
            cost = 0.0
        else:
            cost = run_result.total_tokens * price

        stop_reason_dim = run_result.actual_stop_reason or "none"

        record: dict[str, object] = {
            "_aws": {
                "Timestamp": _timestamp_ms(),
                "CloudWatchMetrics": [
                    {
                        "Namespace": _NAMESPACE,
                        "Dimensions": _DIMENSIONS,
                        "Metrics": [
                            {"Name": "DetectionTime", "Unit": "Milliseconds"},
                            {"Name": "RecoveryTime", "Unit": "Milliseconds"},
                            {"Name": "CostPerRun", "Unit": "None"},
                            {"Name": "TotalHandoffs", "Unit": "Count"},
                            {"Name": "TotalTokens", "Unit": "Count"},
                        ],
                    }
                ],
            },
            # Dimensions
            "config": run_result.config_name,
            "scenario": run_result.scenario_name,
            "stop_reason": stop_reason_dim,
            # Metrics
            "DetectionTime": run_result.detection_time_ms,
            "RecoveryTime": run_result.recovery_time_ms,
            "CostPerRun": cost,
            "TotalHandoffs": run_result.total_handoffs,
            "TotalTokens": run_result.total_tokens,
        }
        print(json.dumps(record))

    @classmethod
    def emit_aggregate(
        cls,
        metrics: AggregatedMetrics,
        scenario: str = "__aggregate__",
    ) -> None:
        """Emit aggregate metrics (CorrectStopRate, FalsePositiveRate) for a full run.

        Args:
            metrics: Aggregated metrics for one configuration.
            scenario: Synthetic scenario name; defaults to "__aggregate__".
        """
        record: dict[str, object] = {
            "_aws": {
                "Timestamp": _timestamp_ms(),
                "CloudWatchMetrics": [
                    {
                        "Namespace": _NAMESPACE,
                        "Dimensions": _DIMENSIONS,
                        "Metrics": [
                            {"Name": "CorrectStopRate", "Unit": "None"},
                            {"Name": "FalsePositiveRate", "Unit": "None"},
                        ],
                    }
                ],
            },
            # Dimensions
            "config": metrics.config_name,
            "scenario": scenario,
            "stop_reason": "none",
            # Metrics
            "CorrectStopRate": metrics.correct_stop_rate,
            "FalsePositiveRate": metrics.false_positive_rate,
        }
        print(json.dumps(record))
