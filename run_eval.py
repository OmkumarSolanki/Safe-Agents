"""CLI entry point: run the full Safe-Agents eval and (optionally) generate a report.

Examples:
    python run_eval.py                              # all models, all scenarios, 1 trial
    python run_eval.py --models qwen --trials 3
    python run_eval.py --report                     # generate report.md when done
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_runner import run_full_eval
from config import MODELS
from report import generate_report
from scenarios import SCENARIOS


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run the Safe-Agents eval.")
    parser.add_argument(
        "--models",
        default=",".join(MODELS.keys()),
        help=f"Comma-separated model keys (default: all: {','.join(MODELS.keys())}).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Trials per scenario per model (default: 1).",
    )
    parser.add_argument(
        "--results-root",
        default="results",
        help="Root directory for results (default: results).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate a markdown report at the end of the run.",
    )
    args = parser.parse_args()

    model_keys = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in model_keys if m not in MODELS]
    if unknown:
        raise SystemExit(f"Unknown model keys: {unknown}. Known: {list(MODELS.keys())}")

    print(f"Running {len(SCENARIOS)} scenarios × {len(model_keys)} models × {args.trials} trials...")

    def _on_trial(record: dict) -> None:
        verdict = "PASS" if record["pass"] else "FAIL"
        print(f"  [{verdict}] {record['model_id']} :: {record['scenario_id']}")

    run_id, run_dir = run_full_eval(
        SCENARIOS,
        model_keys,
        trials_per_scenario=args.trials,
        results_root=Path(args.results_root),
        on_trial=_on_trial,
    )
    print(f"Done. Run ID: {run_id}")
    print(f"Trials written to: {run_dir / 'trials.jsonl'}")

    if args.report:
        out, _ = generate_report(run_dir)
        print(f"Report: {out}")


if __name__ == "__main__":
    _cli()
