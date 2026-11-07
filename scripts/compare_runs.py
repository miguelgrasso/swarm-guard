"""compare_runs.py — compare two benchmark JSON files and generate docs/findings.md.

Usage::

    uv run python scripts/compare_runs.py baseline.json guarded.json
    uv run python scripts/compare_runs.py results/benchmark_20240101T000000Z.json \\
        results/benchmark_20240101T010000Z.json

The Markdown formatting logic lives in :func:`format_findings_table`, which is
importable from tests without side effects (Design Property 16). Only
:func:`main` touches the filesystem.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

try:
    from swarm_guard.models import RunResult
except ImportError:  # pragma: no cover - running as a script without the package installed
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from swarm_guard.models import RunResult

_FINDINGS_PATH = Path(__file__).parent.parent / "docs" / "findings.md"

TABLE_HEADER = (
    "| Scenario | Baseline Status | Baseline Stop Reason | "
    "Guarded Status | Guarded Stop Reason | "
    "Baseline ✓ | Guarded ✓ | ΔTokens | ΔCost |"
)
TABLE_SEPARATOR = "|---|---|---|---|---|---|---|---|---|"


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {p}", file=sys.stderr)
        sys.exit(1)
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _bool_icon(value: Any) -> str:
    return "✅" if value else "❌"


def _run_result_from_dict(raw: dict[str, Any]) -> RunResult:
    """Build a ``RunResult`` from a JSON dict, tolerating missing optional fields."""
    return RunResult(
        scenario_name=str(raw["scenario_name"]),
        config_name=str(raw.get("config_name", "")),
        actual_status=str(raw.get("actual_status", "")),
        actual_stop_reason=raw.get("actual_stop_reason"),
        detection_time_ms=float(raw.get("detection_time_ms") or 0.0),
        recovery_time_ms=float(raw.get("recovery_time_ms") or 0.0),
        total_handoffs=int(raw.get("total_handoffs") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
        cost_usd=float(raw.get("cost_usd") or 0.0),
        is_correct=bool(raw.get("is_correct", False)),
        accumulated_metrics=dict(raw.get("accumulated_metrics") or {}),
    )


def _index_by_scenario(results: Iterable[RunResult]) -> dict[str, RunResult]:
    return {r.scenario_name: r for r in results}


def format_findings_table(
    baseline_results: Sequence[RunResult],
    guarded_results: Sequence[RunResult],
) -> str:
    """Render the baseline-vs-guarded comparison as a Markdown table.

    Returns a string with a header row, a separator row and exactly one data row
    per unique ``scenario_name`` present in either list (sorted). Pure function:
    no filesystem or stdout access.
    """
    baseline = _index_by_scenario(baseline_results)
    guarded = _index_by_scenario(guarded_results)
    all_scenarios = sorted(set(baseline) | set(guarded))

    lines: list[str] = [TABLE_HEADER, TABLE_SEPARATOR]

    for name in all_scenarios:
        br = baseline.get(name)
        gr = guarded.get(name)

        b_tokens = br.total_tokens if br else 0
        g_tokens = gr.total_tokens if gr else 0
        delta_tokens = g_tokens - b_tokens

        b_cost = br.cost_usd if br else 0.0
        g_cost = gr.cost_usd if gr else 0.0
        delta_cost = g_cost - b_cost
        delta_cost_str = f"{delta_cost:+.6f}" if (b_cost or g_cost) else "—"

        lines.append(
            f"| {name} "
            f"| {_fmt(br.actual_status if br else None)} "
            f"| {_fmt(br.actual_stop_reason if br else None)} "
            f"| {_fmt(gr.actual_status if gr else None)} "
            f"| {_fmt(gr.actual_stop_reason if gr else None)} "
            f"| {_bool_icon(br.is_correct if br else None)} "
            f"| {_bool_icon(gr.is_correct if gr else None)} "
            f"| {delta_tokens:+d} "
            f"| {delta_cost_str} |"
        )

    return "\n".join(lines)


def _format_summary(baseline_data: Any, guarded_data: Any) -> str:
    lines: list[str] = ["## Summary\n"]
    for label, data in [("Baseline", baseline_data), ("Guarded", guarded_data)]:
        metrics_key = f"{label.lower()}_metrics"
        metrics: Any = data.get(metrics_key)
        if metrics:
            csr = float(metrics.get("correct_stop_rate", 0.0))
            fpr = float(metrics.get("false_positive_rate", 0.0))
            total = int(metrics.get("total_scenarios", 0))
            correct = int(metrics.get("total_correct", 0))
            lines.append(
                f"**{label}**: "
                f"scenarios={total}, correct={correct}, "
                f"CorrectStopRate={csr:.3f}, FalsePositiveRate={fpr:.3f}"
            )
        else:
            lines.append(f"**{label}**: no aggregate metrics found.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="compare_runs",
        description="Compare two benchmark result JSON files and produce docs/findings.md.",
    )
    parser.add_argument("baseline_json", help="Path to the baseline benchmark JSON file.")
    parser.add_argument("guarded_json", help="Path to the guarded benchmark JSON file.")
    args = parser.parse_args(argv)

    baseline_data: Any = _load_json(args.baseline_json)
    guarded_data: Any = _load_json(args.guarded_json)

    baseline_results = [
        _run_result_from_dict(r)
        for r in baseline_data.get("results", [])
        if r.get("config_name") == "baseline"
    ]
    guarded_results = [
        _run_result_from_dict(r)
        for r in guarded_data.get("results", [])
        if r.get("config_name") == "guarded"
    ]

    document = "\n".join(
        [
            "# swarm-guard — Findings\n",
            "> Auto-generated by `scripts/compare_runs.py`. Do not edit manually.\n",
            f"Baseline run: `{args.baseline_json}`  \nGuarded run: `{args.guarded_json}`\n",
            "",
            format_findings_table(baseline_results, guarded_results),
            "",
            _format_summary(baseline_data, guarded_data),
        ]
    )

    _FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FINDINGS_PATH.write_text(document + "\n", encoding="utf-8")
    print(f"Generated {_FINDINGS_PATH}")


if __name__ == "__main__":
    main()
