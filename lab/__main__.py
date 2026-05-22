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
from lab.data import GameResult, GameDecisions, GamesWriter, DecisionsWriter
from lab.simulation import game_worker_init, run_one_game
from lab.generators import REFERENCE_PARAMS, build_strategy, count_games, get_generator

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        sys.exit(1)
    print("\nShutdown requested. Finishing in-flight games...")
    _shutdown_requested = True


def format_matchup(strategies: list[Strategy]) -> str:
    return " vs ".join(str(s) for s in strategies)


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
        param_name = compare["parameter"]
        param_values = compare["values"]
        pairs = list(itertools.combinations(param_values, 2))

        print(f"Parameter: {param_name}")
        print(f"Values: {param_values}")
        print(f"Pairs: {len(pairs)}")
        print(
            f"Seeds: {seeds_config['count']} (starting at {seeds_config.get('start', 1)})"
        )
        print(f"Total games: {total_games}")
    elif mode == "vs_reference":
        compare = config["compare"]
        seeds_config = config["seeds"]
        print(
            f"Reference: MCTS(sims={REFERENCE_PARAMS.simulations}, "
            f"c={REFERENCE_PARAMS.exploration_constant}, "
            f"vf={REFERENCE_PARAMS.value_function.value})"
        )
        print(f"Sweep: {compare['parameter']} = {compare['values']}")
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
            print(f"  {i}. {format_matchup(strategies)}")
        print(f"Games per round: {games_per_round}")
        print("Total games: infinite (Ctrl+C to stop)")

    print("-" * 60)


def _work_iter(
    generator: Iterator[tuple[list[Strategy], int]],
    total_games: int | None,
    record_decisions: bool,
) -> Iterator[tuple[list[Strategy], int, int, bool]]:
    """Yield work items `(strategies, game_seed, game_idx, record_decisions)`,
    halting on shutdown or when total_games is reached.

    `game_idx` is the 0-based global index; the receiver derives
    `(group_idx, in_group_idx)` from it.
    """
    for game_idx, (strategies, game_seed) in enumerate(generator):
        if _shutdown_requested:
            return
        if total_games is not None and game_idx >= total_games:
            return
        yield (strategies, game_seed, game_idx, record_decisions)


def _iter_results(
    work: Iterable[tuple[list[Strategy], int, int, bool]],
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


def run_experiments(config: dict, data_dir: Path, record_decisions: bool = False):
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
        param_name = compare["parameter"]
        games_per_group = config["seeds"]["count"] * 2  # ×2 for position swap

        if mode == "paired":
            groups = list(itertools.combinations(compare["values"], 2))
            header_fn = lambda g: f"{param_name}={g[0]} vs {param_name}={g[1]}"
            labels_fn = lambda g: (str(g[0]), str(g[1]))
        else:  # vs_reference
            groups = list(compare["values"])
            header_fn = lambda g: f"{param_name}={g} vs reference"
            labels_fn = lambda g: ("arm", "reference")

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

    with GamesWriter(data_dir) as games_writer:
        decisions_writer = DecisionsWriter(data_dir) if record_decisions else None

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


def main():
    parser = argparse.ArgumentParser(description="Run Wingspan experiments")
    parser.add_argument(
        "-c", "--config", type=str, default=None, help="Config file path"
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

    config_path = (
        Path(args.config)
        if args.config
        else Path(__file__).parent.parent / "experiments" / "configs" / "config.yaml"
    )
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)

    if args.list:
        mode = config.get("mode", "continuous")
        if mode == "continuous":
            defaults = config.get("defaults", {})
            print("Configured matchups:")
            for i, spec_list in enumerate(config["matchups"], 1):
                strategies = [build_strategy(spec, defaults) for spec in spec_list]
                print(f"  {i}. {format_matchup(strategies)}")
        elif mode == "paired":
            compare = config["compare"]
            print(f"Paired comparison: {compare['parameter']}")
            print(f"Values: {compare['values']}")
        elif mode == "vs_reference":
            compare = config["compare"]
            print(f"vs_reference sweep: {compare['parameter']}")
            print(f"Values: {compare['values']}")
        return

    data_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(__file__).parent.parent / "experiments" / "data"
    )
    signal.signal(signal.SIGINT, _signal_handler)

    print_config_summary(config, data_dir)
    run_experiments(config, data_dir, args.record_decisions)


if __name__ == "__main__":
    main()
