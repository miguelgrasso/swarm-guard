"""run_benchmark.py — CLI entry point for the swarm-guard benchmark.

Executes all 20 adversarial scenarios against one or both configurations
and writes results to BENCHMARK_OUTPUT_DIR.

Usage::

    uv run python scripts/run_benchmark.py --config all
    uv run python scripts/run_benchmark.py --config guarded --scenario ping_pong
    uv run python scripts/run_benchmark.py --config baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure src/ is on the path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from swarm_guard.configs.guarded import ConfigurationError
from swarm_guard.runner import run_benchmark


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_benchmark",
        description="Execute the swarm-guard adversarial benchmark.",
    )
    parser.add_argument(
        "--config",
        choices=["baseline", "guarded", "all"],
        default="all",
        help="Which configuration(s) to run. Default: all (both baseline and guarded).",
    )
    parser.add_argument(
        "--scenario",
        metavar="NAME",
        default=None,
        help=(
            "Run a single scenario by name (snake_case, e.g. ping_pong). "
            "Omit to run all 20 scenarios."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    config_names: list[str]
    if args.config == "all":
        config_names = ["baseline", "guarded"]
    else:
        config_names = [args.config]

    scenario_names: list[str] | None = None
    if args.scenario is not None:
        scenario_names = [args.scenario]

    try:
        run_benchmark(config_names, scenario_names)
    except ConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "Hint: set BUDGET_GUARD_MAX_TOKENS in your environment "
            "(e.g. export BUDGET_GUARD_MAX_TOKENS=5000)",
            file=sys.stderr,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
