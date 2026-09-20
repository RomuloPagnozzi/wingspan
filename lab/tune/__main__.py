"""CLI: `python -m lab.tune -c <config.yaml>`.

Reads a tuning YAML, runs the study, persists results under
`experiments/tuning/<study_name>/`.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

import yaml

from lab.tune.merge import merge_study
from lab.tune.runner import run_study

_TUNING_ROOT = Path(__file__).parent.parent.parent / "experiments" / "tuning"


def _on_sigint(signum, frame):
    # Let optuna unwind cleanly: the in-flight trial finishes, then optimize
    # raises and we exit. Second Ctrl-C hard-exits.
    print("\nShutdown requested. Finishing in-flight trial...")
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def main():
    parser = argparse.ArgumentParser(description="Run an Optuna study over MCTSConfig")
    parser.add_argument("-c", "--config", type=Path, help="Tuning YAML path")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output root (default: {_TUNING_ROOT})",
    )
    parser.add_argument(
        "--merge-only",
        type=Path,
        default=None,
        metavar="STUDY_DIR",
        help="Collapse per-trial parquets in STUDY_DIR into one file per kind and exit.",
    )
    args = parser.parse_args()

    if args.merge_only is not None:
        counts = merge_study(args.merge_only)
        for kind, n in counts.items():
            print(f"{kind}: merged {n} files")
        return

    if args.config is None:
        parser.error("either -c/--config or --merge-only is required")

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    with args.config.open() as f:
        config = yaml.safe_load(f)

    root = args.output_dir or _TUNING_ROOT
    study_dir = root / config["study_name"]

    print(f"Study: {config['study_name']}")
    print(f"Output: {study_dir}")
    print(f"Trials: {config['n_trials']}  seeds/trial: {config['seeds']['count']}")
    print("-" * 60)

    signal.signal(signal.SIGINT, _on_sigint)
    run_study(config, study_dir, source_yaml_path=args.config)


if __name__ == "__main__":
    main()
