"""Run games between strategies and save results to parquet."""

import argparse
import itertools
import signal
import sys
from pathlib import Path

import yaml

from lab.strategies import Strategy
from lab.data import GamesWriter, DecisionsWriter
from lab.simulation import simulate_game
from lab.generators import get_generator, count_games, build_strategy

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    if _shutdown_requested:
        sys.exit(1)
    print("\nShutdown requested. Finishing current game...")
    _shutdown_requested = True


def format_matchup(strategies: list[Strategy]) -> str:
    return " vs ".join(str(s) for s in strategies)


def print_config_summary(config: dict, data_dir: Path):
    """Print experiment configuration summary."""
    mode = config.get("mode", "continuous")
    total_games = count_games(config)

    print(f"Experiment Mode: {mode}")
    print(f"Output: {data_dir}")

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


def run_experiments(config: dict, data_dir: Path, record_decisions: bool = False):
    global _shutdown_requested

    mode = config.get("mode", "continuous")
    total_games = count_games(config)
    generator = get_generator(config)

    param_name = ""
    pairs: list[tuple] = []
    results: dict[tuple, dict[str, int]] = {}
    current_pair_idx = 0
    games_in_pair = 0
    seeds_per_pair = 0

    if mode == "paired":
        compare = config["compare"]
        param_name = compare["parameter"]
        param_values = compare["values"]
        pairs = list(itertools.combinations(param_values, 2))
        results = {pair: {"A_wins": 0, "B_wins": 0, "ties": 0} for pair in pairs}
        seeds_per_pair = config["seeds"]["count"] * 2

    games_played = 0

    with GamesWriter(data_dir) as games_writer:
        decisions_writer = DecisionsWriter(data_dir) if record_decisions else None

        try:
            for strategies, game_seed in generator:
                if _shutdown_requested:
                    break

                result, game_decisions = simulate_game(
                    strategies, game_seed, record_decisions=record_decisions
                )
                games_writer.add_game(result)
                games_played += 1

                if decisions_writer and game_decisions:
                    decisions_writer.add_game_decisions(game_decisions)

                # Track wins for paired mode
                if mode == "paired":
                    pair = pairs[current_pair_idx]
                    winner = next((p for p in result.players if p.is_winner), None)
                    if winner:
                        winner_value = winner.strategy_config.get(param_name)
                        if winner_value == str(pair[0]):
                            results[pair]["A_wins"] += 1
                        else:
                            results[pair]["B_wins"] += 1
                    else:
                        results[pair]["ties"] += 1

                    games_in_pair += 1
                    if games_in_pair >= seeds_per_pair:
                        # Print pair summary
                        r = results[pair]
                        total = r["A_wins"] + r["B_wins"] + r["ties"]
                        print(f"\n{param_name}={pair[0]} vs {param_name}={pair[1]}:")
                        print(
                            f"  {pair[0]}: {r['A_wins']} wins ({r['A_wins']/total*100:.1f}%)"
                        )
                        print(
                            f"  {pair[1]}: {r['B_wins']} wins ({r['B_wins']/total*100:.1f}%)"
                        )
                        if r["ties"] > 0:
                            print(f"  Ties: {r['ties']}")

                        current_pair_idx += 1
                        games_in_pair = 0

                # Progress for continuous mode
                elif games_played % 10 == 0:
                    print(f"Games played: {games_played}")

                # Check if finite experiment is done
                if total_games and games_played >= total_games:
                    break

        finally:
            if decisions_writer:
                decisions_writer.close()

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS ({games_played} games)")
    print("=" * 60)

    if mode == "paired":
        for pair, r in results.items():
            total = r["A_wins"] + r["B_wins"] + r["ties"]
            if total > 0:
                print(f"\n{param_name}={pair[0]} vs {param_name}={pair[1]}:")
                print(
                    f"  {pair[0]}: {r['A_wins']}/{total} ({r['A_wins']/total*100:.1f}%)"
                )
                print(
                    f"  {pair[1]}: {r['B_wins']}/{total} ({r['B_wins']/total*100:.1f}%)"
                )


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
        else:
            compare = config["compare"]
            print(f"Paired comparison: {compare['parameter']}")
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
