"""Run games between strategies and save results to parquet."""

import argparse
import json
import random
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator

import yaml
from tqdm import tqdm

from wingspan.ai import Strategy
from lab.data import GamesWriter, DecisionsWriter, generate_run_id
from lab.simulation import play_games
from lab import ledger
from lab.summary import as_dict, format_summary, load_games, summarize
from lab.generators import (
    ConfigError,
    build_strategy,
    count_games,
    get_generator,
    validate_config,
)

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        sys.exit(1)
    print("\nShutdown requested. Finishing in-flight games...")
    _shutdown_requested = True


def _arm_desc(arm: dict, param_name: str | None) -> str:
    """Short human-readable description of one paired/vs_reference arm."""
    if "overrides" in arm:
        return ", ".join(f"{k}={v}" for k, v in arm["overrides"].items())
    return f"{param_name}={arm['value']}"


def _spec_desc(spec: dict) -> str:
    return f"{spec['strategy']}(" + ", ".join(f"{k}={v}" for k, v in spec.items() if k != "strategy") + ")"


def describe_config(config: dict) -> list[str]:
    """The lines that describe what a config plays (for `--list` and the run header)."""
    mode = config.get("mode", "continuous")
    total = count_games(config)
    seeds = config.get("seeds")
    lines = [f"Experiment Mode: {mode}"]
    if mode in ("paired", "vs_reference"):
        compare = config["compare"]
        param_name = compare.get("parameter")
        if mode == "vs_reference":
            lines.append(f"Reference ({compare['reference_label']}): {_spec_desc(compare['reference'])}")
        if param_name:
            lines.append(f"Parameter: {param_name}")
        lines.append("Arms:")
        lines += [f"  - {arm['label']} ({_arm_desc(arm, param_name)})" for arm in compare["values"]]
    else:
        defaults = config.get("defaults", {})
        lines.append(f"Matchups: {len(config['matchups'])}")
        for i, spec_list in enumerate(config["matchups"], 1):
            named = " vs ".join(f"{spec['label']} ({build_strategy(spec, defaults)})" for spec in spec_list)
            lines.append(f"  {i}. {named}")
    if seeds:
        lines.append(f"Seeds: {seeds.get('count') or 'endless'} (starting at {seeds.get('start', 1)})")
    lines.append(f"Total games: {total if total is not None else 'until Ctrl+C'}")
    return lines


def scoring_for(game_seed: int, blue_share: float) -> str:
    """The round-goal scoring side of a game, fixed by its seed: blue for about `blue_share` of
    seeds, green otherwise, so a game can be replayed exactly."""
    return "blue" if random.Random(game_seed).random() < blue_share else "green"


def _work_iter(
    generator: Iterator[tuple[list[Strategy], int, list[str]]],
    total_games: int | None,
    record_decisions: bool,
    blue_share: float = 0.0,
) -> Iterator[tuple[list[Strategy], int, list[str], int, bool, str]]:
    """Yield work items `(strategies, game_seed, arm_labels, game_idx, record_decisions, scoring)`
    for `lab.simulation.run_one_game`, halting on shutdown or when total_games is reached."""
    for game_idx, (strategies, game_seed, arm_labels) in enumerate(generator):
        if _shutdown_requested:
            return
        if total_games is not None and game_idx >= total_games:
            return
        yield (strategies, game_seed, arm_labels, game_idx, record_decisions, scoring_for(game_seed, blue_share))


def run_experiments(
    config: dict,
    data_dir: Path,
    run_id: str,
    record_decisions: bool = False,
    rotate: int | None = None,
):
    total_games = count_games(config)
    num_workers = int(config.get("num_workers", 1))
    wins: dict[frozenset, Counter] = {}  # per matchup: wins by label, ties under None
    progress = tqdm(total=total_games, desc="games", unit="game", dynamic_ncols=True, smoothing=0.1)

    with GamesWriter(data_dir, run_id, rotate) as games_writer:
        decisions_writer = DecisionsWriter(data_dir, run_id, rotate) if record_decisions else None
        try:
            # `blue_share` (config): share of games with blue round-goal scoring; default all green
            work = _work_iter(get_generator(config), total_games, record_decisions, config.get("blue_share", 0.0))
            for result, game_decisions, _game_idx in play_games(work, num_workers):
                games_writer.add_game(result)
                if decisions_writer and game_decisions:
                    decisions_writer.add_game_decisions(game_decisions)
                progress.update(1)
                # An unrotated parquet can't be read until it closes: this is how the lab UI follows the run
                (data_dir / run_id / "progress.json").write_text(json.dumps({"games": progress.n, "total": total_games}))
                labels = sorted(p.arm_label for p in result.players)
                tally = wins.setdefault(frozenset(labels), Counter())
                tally[result.winner_label()] += 1
                progress.set_postfix_str(" ".join(f"{label}:{tally[label]}" for label in labels) + f" ties:{tally[None]}")
        finally:
            progress.close()
            if decisions_writer:
                decisions_writer.close()

    games = load_games([data_dir / run_id])
    print(f"\n{'=' * 60}\nRESULTS ({games.game_id.nunique()} games)\n{'=' * 60}")
    print(format_summary(summarize(games)))
    description = (data_dir / run_id / "config.yaml").read_text().split("\n")[0].lstrip("# ")
    ledger.record("run", experiment=data_dir.name, run_id=run_id, description=description, config=config, nets=ledger.nets_in(config), **as_dict(games))


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def code_version() -> str:
    """The git commit of this checkout, noting uncommitted changes; "unknown" outside git."""
    git = lambda *args: subprocess.run(["git", *args], capture_output=True, text=True, cwd=Path(__file__).parent)
    commit = git("rev-parse", "HEAD")
    if commit.returncode:
        return "unknown"
    return commit.stdout.strip() + (" + uncommitted changes" if git("status", "--porcelain").stdout.strip() else "")


def _run_one_config(
    config_path: Path,
    data_dir: Path,
    record_decisions: bool,
    list_only: bool,
    rotate: int | None = None,
) -> None:
    config = load_config(config_path)

    try:
        validate_config(config)
    except ConfigError as e:
        print(f"Config error in {config_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if list_only:
        print("\n".join(describe_config(config)))
        return

    run_id = generate_run_id()

    # Each run gets its own folder containing games, decisions, and config.
    # Copy the source YAML into it so the run is fully self-contained.
    # Ad-hoc/non-CLI runs have no YAML and skip this — the `run_id` column
    # still groups rows.
    run_dir = data_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_bytes(config_path.read_bytes())
    # Replays are only valid with the engine rules the games were played under
    (run_dir / "code_version.txt").write_text(config.get("code_version") or code_version() + "\n")

    print(f"\nRun ID: {run_id}  (config: {config_path})")
    print("\n".join(describe_config(config)))
    print(f"Output: {data_dir / run_id}\nWorkers: {int(config.get('num_workers', 1))}  (games run concurrently)")
    print("-" * 60)
    run_experiments(config, data_dir, run_id, record_decisions, rotate)


def main():
    parser = argparse.ArgumentParser(description="Run Wingspan experiments")
    parser.add_argument(
        "-c",
        "--config",
        action="append",
        required=True,
        help="Config file path. Repeat to queue multiple configs (run sequentially).",
    )
    parser.add_argument(
        "-o", "--output-dir", type=str, default=None, help="Output directory"
    )
    parser.add_argument(
        "--record-decisions",
        action="store_true",
        help="Record per-decision data for RL training",
    )
    parser.add_argument("--list", action="store_true", help="List config and exit")
    parser.add_argument(
        "--rotate-every",
        type=int,
        default=None,
        help="Close the parquet files every N games and start new parts, so a long run can be "
        "copied away while it goes on",
    )
    args = parser.parse_args()

    config_paths = [Path(c) for c in args.config]

    missing = [p for p in config_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"Config not found: {p}", file=sys.stderr)
        sys.exit(1)

    data_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(__file__).parent.parent / "experiments" / "data"
    )
    signal.signal(signal.SIGINT, _signal_handler)

    for i, cfg_path in enumerate(config_paths, 1):
        if len(config_paths) > 1 and not args.list:
            print(f"\n{'#' * 60}")
            print(f"# [{i}/{len(config_paths)}] {cfg_path}")
            print(f"{'#' * 60}")
        _run_one_config(cfg_path, data_dir, args.record_decisions, args.list, args.rotate_every)
        if _shutdown_requested:
            print("Shutdown requested — skipping remaining configs.")
            break


if __name__ == "__main__":
    main()
