"""Experiment generators that yield (strategies, game_seed) tuples."""

import itertools
import random
from typing import Iterator

from lab.strategies import Strategy, create_strategy


def build_strategy(spec: dict, defaults: dict) -> Strategy:
    """Build a strategy from spec dict merged with defaults."""
    name = spec["strategy"]
    params = {**defaults, **{k: v for k, v in spec.items() if k != "strategy"}}
    return create_strategy(name, **params)


def continuous_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int]]:
    """Generate games continuously for matchup experiments.

    Yields (strategies, game_seed) tuples indefinitely.
    Caller is responsible for stopping (e.g., via SIGINT).
    """
    defaults = config.get("defaults", {})
    matchup_specs = config["matchups"]
    games_per_round = defaults.get("games_per_round", 5)

    while True:
        for spec_list in matchup_specs:
            for _ in range(games_per_round):
                strategies = [build_strategy(spec, defaults) for spec in spec_list]
                game_seed = random.randint(0, 2**31)
                yield strategies, game_seed


def paired_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int]]:
    """Generate paired comparison games with controlled seeds.

    For each pair of parameter values, generates games with:
    - Same game_seed for position-swapped games
    - Same strategy seed for both players (only param differs)

    Yields (strategies, game_seed) tuples.
    """
    base = config["base"]
    compare = config["compare"]
    seeds_config = config["seeds"]

    param_name = compare["parameter"]
    param_values = compare["values"]
    seed_count = seeds_config["count"]
    seed_start = seeds_config.get("start", 1)

    pairs = list(itertools.combinations(param_values, 2))

    for val_a, val_b in pairs:
        for seed_idx in range(seed_count):
            game_seed = seed_start + seed_idx
            mcts_seed = seed_start + seed_idx

            config_a = {**base, param_name: val_a, "seed": mcts_seed}
            config_b = {**base, param_name: val_b, "seed": mcts_seed}

            # Game 1: A as P1, B as P2
            strategy_a = create_strategy(
                config_a["strategy"],
                **{k: v for k, v in config_a.items() if k != "strategy"},
            )
            strategy_b = create_strategy(
                config_b["strategy"],
                **{k: v for k, v in config_b.items() if k != "strategy"},
            )
            yield [strategy_a, strategy_b], game_seed

            # Game 2: B as P1, A as P2 (position swap)
            strategy_a = create_strategy(
                config_a["strategy"],
                **{k: v for k, v in config_a.items() if k != "strategy"},
            )
            strategy_b = create_strategy(
                config_b["strategy"],
                **{k: v for k, v in config_b.items() if k != "strategy"},
            )
            yield [strategy_b, strategy_a], game_seed


def get_generator(config: dict) -> Iterator[tuple[list[Strategy], int]]:
    """Get the appropriate generator based on config mode."""
    mode = config.get("mode", "continuous")

    if mode == "paired":
        return paired_generator(config)
    elif mode == "continuous":
        return continuous_generator(config)
    else:
        raise ValueError(f"Unknown mode: {mode}")


def count_games(config: dict) -> int | None:
    """Return total game count for finite experiments, None for infinite."""
    mode = config.get("mode", "continuous")

    if mode == "paired":
        param_values = config["compare"]["values"]
        seed_count = config["seeds"]["count"]
        num_pairs = len(list(itertools.combinations(param_values, 2)))
        return num_pairs * seed_count * 2  # 2 games per seed (position swap)

    return None  # Continuous runs forever
