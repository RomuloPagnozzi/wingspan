"""Run games between strategies and save results to parquet."""

import argparse
import itertools
import multiprocessing as mp
import signal
import sys
from pathlib import Path
from typing import Iterable, Iterator

import yaml
from tqdm import tqdm

from lab.strategies import Strategy
from lab.data import (
    GameResult,
    GameDecisions,
    GamesWriter,
    DecisionsWriter,
    generate_run_id,
)
from lab.simulation import game_worker_init, run_one_game
from lab.generators import (
    REFERENCE_PARAMS,
    ConfigError,
    build_strategy,
    count_games,
    get_generator,
    validate_config,
)

_shutdown_requested = False


def _arm_desc(arm: dict, param_name: str | None) -> str:
    """Short human-readable description of one paired/vs_reference arm."""
    if "overrides" in arm:
        return ", ".join(f"{k}={v}" for k, v in arm["overrides"].items())
    return f"{param_name}={arm['value']}"


def _signal_handler(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        sys.exit(1)
    print("\nShutdown requested. Finishing in-flight games...")
    _shutdown_requested = True


def _attribute_by_position(result, in_group_idx: int) -> str:
    """Attribute a game result to arm A, arm B, or ties.

    Arm A occupies player position 0 on even in-group games, position 1 on
    odd ones (position swap). Identical attribution rule for both paired and
    vs_reference modes — they only differ in what A and B *are*, not where
    they sit in the player list.
    """
    a_idx = 0 if in_group_idx % 2 == 0 else 1
    if result.players[a_idx].is_winner:
        return "A"
    if any(p.is_winner for p in result.players):
        return "B"
    return "ties"


def _print_group_via(write_fn, header: str, r: dict, a_label: str, b_label: str):
    """Print group summary via a writer (use tqdm.write to avoid clobbering progress bar)."""
    total = sum(r.values())
    if total == 0:
        return
    write_fn(f"\n{header}:")
    write_fn(f"  {a_label}: {r['A']}/{total} ({r['A'] / total * 100:.1f}%)")
    write_fn(f"  {b_label}: {r['B']}/{total} ({r['B'] / total * 100:.1f}%)")
    if r["ties"] > 0:
        write_fn(f"  ties: {r['ties']}")


def print_config_summary(config: dict, data_dir: Path):
    """Print experiment configuration summary."""
    mode = config.get("mode", "continuous")
    total_games = count_games(config)
    num_workers = int(config.get("num_workers", 1))

    print(f"Experiment Mode: {mode}")
    print(f"Output: {data_dir}")
    print(f"Workers: {num_workers}  (games run concurrently)")

    if mode == "paired":
        compare = config["compare"]
        seeds_config = config["seeds"]
        param_name = compare.get("parameter")
        arms = compare["values"]
        pairs = list(itertools.combinations(arms, 2))

        if param_name:
            print(f"Parameter: {param_name}")
        print("Arms:")
        for arm in arms:
            print(f"  - {arm['label']} ({_arm_desc(arm, param_name)})")
        print(f"Pairs: {len(pairs)}")
        print(
            f"Seeds: {seeds_config['count']} (starting at {seeds_config.get('start', 1)})"
        )
        print(f"Total games: {total_games}")
    elif mode == "vs_reference":
        compare = config["compare"]
        seeds_config = config["seeds"]
        print(
            f"Reference ({compare['reference_label']}): MCTS("
            f"sims={REFERENCE_PARAMS.simulations}, "
            f"c={REFERENCE_PARAMS.exploration_constant}, "
            f"vf={REFERENCE_PARAMS.value_function.value})"
        )
        param_name = compare.get("parameter")
        if param_name:
            print(f"Sweep: {param_name}")
        for arm in compare["values"]:
            print(f"  - {arm['label']} ({_arm_desc(arm, param_name)})")
        print(
            f"Seeds: {seeds_config['count']} (starting at {seeds_config.get('start', 1)})"
        )
        print(f"Total games: {total_games}")
    else:
        defaults = config.get("defaults", {})
        matchup_specs = config["matchups"]
        games_per_round = defaults.get("games_per_round", 5)

        print(f"Matchups: {len(matchup_specs)}")
        for i, spec_list in enumerate(matchup_specs, 1):
            strategies = [build_strategy(spec, defaults) for spec in spec_list]
            labels = [spec["label"] for spec in spec_list]
            named = " vs ".join(
                f"{label} ({s})" for label, s in zip(labels, strategies)
            )
            print(f"  {i}. {named}")
        print(f"Games per round: {games_per_round}")
        print("Total games: infinite (Ctrl+C to stop)")

    print("-" * 60)


def _work_iter(
    generator: Iterator[tuple[list[Strategy], int, list[str]]],
    total_games: int | None,
    record_decisions: bool,
) -> Iterator[tuple[list[Strategy], int, list[str], int, bool]]:
    """Yield work items `(strategies, game_seed, arm_labels, game_idx, record_decisions)`,
    halting on shutdown or when total_games is reached.

    `game_idx` is the 0-based global index; the receiver derives
    `(group_idx, in_group_idx)` from it.
    """
    for game_idx, (strategies, game_seed, arm_labels) in enumerate(generator):
        if _shutdown_requested:
            return
        if total_games is not None and game_idx >= total_games:
            return
        yield (strategies, game_seed, arm_labels, game_idx, record_decisions)


def _iter_results(
    work: Iterable[tuple[list[Strategy], int, list[str], int, bool]],
    num_workers: int,
) -> Iterator[tuple[GameResult, GameDecisions | None, int]]:
    """Dispatch `work` items to either an in-process loop (num_workers == 1)
    or a spawn-based Pool (num_workers > 1) and yield result triples
    `(result, decisions, game_idx)`.

    Process pool (not thread pool): CPython's GIL serializes pure-Python
    threads, and free-threaded 3.13t was empirically slower for this
    workload due to atomic-refcount overhead on shared registry lookups.
    """
    if num_workers <= 1:
        for item in work:
            yield run_one_game(item)
        return

    ctx = mp.get_context("spawn")
    with ctx.Pool(num_workers, initializer=game_worker_init) as pool:
        # chunksize=1 → each item submitted individually; shutdown can drain
        # in-flight without buffered work piling up in worker queues.
        for result, decisions, meta in pool.imap_unordered(
            run_one_game, work, chunksize=1
        ):
            yield result, decisions, meta


def run_experiments(
    config: dict,
    data_dir: Path,
    run_id: str,
    record_decisions: bool = False,
):
    mode = config.get("mode", "continuous")
    total_games = count_games(config)
    num_workers = int(config.get("num_workers", 1))
    generator = get_generator(config)

    # Group-based modes (paired, vs_reference) share tracking machinery.
    # They differ only in how groups are defined and what A/B mean.
    groups: list = []
    header_fn = None
    labels_fn = None
    results: dict = {}
    games_per_group = 0

    if mode in ("paired", "vs_reference"):
        compare = config["compare"]
        games_per_group = config["seeds"]["count"] * 2  # ×2 for position swap

        if mode == "paired":
            # Each group is the (label_A, label_B) pair from compare.values.
            groups = [
                (a["label"], b["label"])
                for a, b in itertools.combinations(compare["values"], 2)
            ]
        else:  # vs_reference
            # Each group is (arm_label, reference_label).
            ref_label = compare["reference_label"]
            groups = [(a["label"], ref_label) for a in compare["values"]]

        header_fn = lambda g: f"{g[0]} vs {g[1]}"
        labels_fn = lambda g: g
        results = {g: {"A": 0, "B": 0, "ties": 0} for g in groups}

    games_played = 0
    group_completed: dict = {g: 0 for g in groups}
    group_done_printed: set = set()
    progress = tqdm(
        total=total_games,
        desc="games",
        unit="game",
        dynamic_ncols=True,
        smoothing=0.1,
    )

    with GamesWriter(data_dir, run_id) as games_writer:
        decisions_writer = (
            DecisionsWriter(data_dir, run_id) if record_decisions else None
        )

        try:
            work = _work_iter(generator, total_games, record_decisions)
            for result, game_decisions, game_idx in _iter_results(work, num_workers):
                games_writer.add_game(result)
                games_played += 1
                progress.update(1)

                if decisions_writer and game_decisions:
                    decisions_writer.add_game_decisions(game_decisions)

                if groups:
                    group_idx = game_idx // games_per_group
                    in_group_idx = game_idx % games_per_group
                    group = groups[group_idx]
                    outcome = _attribute_by_position(result, in_group_idx)
                    results[group][outcome] += 1
                    group_completed[group] += 1

                    # Live A/B tally on the progress bar for the most-recent group.
                    a_label, b_label = labels_fn(group)
                    r = results[group]
                    completed = group_completed[group]
                    progress.set_postfix_str(
                        f"{header_fn(group)} | "
                        f"{a_label}:{r['A']} {b_label}:{r['B']} ties:{r['ties']} "
                        f"({completed}/{games_per_group})"
                    )

                    if completed >= games_per_group and group not in group_done_printed:
                        group_done_printed.add(group)
                        progress.write("")
                        _print_group_via(
                            progress.write,
                            header_fn(group),
                            r,
                            a_label,
                            b_label,
                        )

        finally:
            progress.close()
            if decisions_writer:
                decisions_writer.close()

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS ({games_played} games)")
    print("=" * 60)

    if groups:
        for group, r in results.items():
            a_label, b_label = labels_fn(group)
            _print_group_via(print, header_fn(group), r, a_label, b_label)


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def _print_config_listing(config: dict) -> None:
    mode = config.get("mode", "continuous")
    if mode == "continuous":
        defaults = config.get("defaults", {})
        print("Configured matchups:")
        for i, spec_list in enumerate(config["matchups"], 1):
            strategies = [build_strategy(spec, defaults) for spec in spec_list]
            labels = [spec["label"] for spec in spec_list]
            named = " vs ".join(
                f"{label} ({s})" for label, s in zip(labels, strategies)
            )
            print(f"  {i}. {named}")
    elif mode == "paired":
        compare = config["compare"]
        param_name = compare.get("parameter")
        print(f"Paired comparison{f': {param_name}' if param_name else ''}")
        for arm in compare["values"]:
            print(f"  - {arm['label']} ({_arm_desc(arm, param_name)})")
    elif mode == "vs_reference":
        compare = config["compare"]
        param_name = compare.get("parameter")
        print(f"vs_reference sweep{f': {param_name}' if param_name else ''}")
        print(f"  reference: {compare['reference_label']}")
        for arm in compare["values"]:
            print(f"  - {arm['label']} ({_arm_desc(arm, param_name)})")


def _run_one_config(
    config_path: Path,
    data_dir: Path,
    record_decisions: bool,
    list_only: bool,
) -> None:
    config = load_config(config_path)

    try:
        validate_config(config)
    except ConfigError as e:
        print(f"Config error in {config_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if list_only:
        _print_config_listing(config)
        return

    run_id = generate_run_id()

    # Each run gets its own folder containing games, decisions, and config.
    # Copy the source YAML into it so the run is fully self-contained.
    # Ad-hoc/non-CLI runs have no YAML and skip this — the `run_id` column
    # still groups rows.
    run_dir = data_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_bytes(config_path.read_bytes())

    print(f"\nRun ID: {run_id}  (config: {config_path})")
    print_config_summary(config, data_dir)
    run_experiments(config, data_dir, run_id, record_decisions)


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
        _run_one_config(cfg_path, data_dir, args.record_decisions, args.list)
        if _shutdown_requested:
            print("Shutdown requested — skipping remaining configs.")
            break


if __name__ == "__main__":
    main()
