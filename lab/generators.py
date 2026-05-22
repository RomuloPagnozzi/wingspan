"""Experiment generators that yield (strategies, game_seed) tuples."""

import itertools
import random
from typing import Iterator

from lab.strategies import (
    MCTSConfig,
    MCTSStrategy,
    Strategy,
    ValueFunction,
    create_strategy,
)

# Project-wide fixed reference opponent. Locked strategic params. Changing
# these constants invalidates cross-experiment comparability — pre-change
# and post-change win rates do not live on the same scale.
REFERENCE_PARAMS = MCTSConfig(
    simulations=500,
    exploration_constant=1.41,
    value_function=ValueFunction.SCORE_DELTA,
)


def _instantiate(spec: dict) -> Strategy:
    """Create a strategy from a fully-merged spec dict (with 'strategy' key)."""
    return create_strategy(
        spec["strategy"], **{k: v for k, v in spec.items() if k != "strategy"}
    )


def build_strategy(spec: dict, defaults: dict) -> Strategy:
    """Build a strategy from spec dict merged with defaults."""
    return _instantiate({**defaults, **spec})


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

    for val_a, val_b in itertools.combinations(param_values, 2):
        for seed_idx in range(seed_count):
            game_seed = trial_seed = seed_start + seed_idx

            config_a = {**base, param_name: val_a, "seed": trial_seed}
            config_b = {**base, param_name: val_b, "seed": trial_seed}

            # Two games per pair: A as P1, then B as P1 (position swap).
            # Fresh strategies each yield so internal RNG starts clean.
            for swap in (False, True):
                pair = [_instantiate(config_a), _instantiate(config_b)]
                yield (pair[::-1] if swap else pair), game_seed


def vs_reference_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int]]:
    """Generate games of each arm against the fixed reference opponent.

    For each value in `compare.values`, runs `seeds.count` paired comparisons
    against REFERENCE_PARAMS. The trial seed is shared between arm and
    reference each game, and position is swapped between the two games of
    each pair — the same paired-comparison machinery as `paired_generator`,
    just with one side fixed to the reference.
    """
    base = config["base"]
    compare = config["compare"]
    seeds_config = config["seeds"]

    param_name = compare["parameter"]
    param_values = compare["values"]
    seed_count = seeds_config["count"]
    seed_start = seeds_config.get("start", 1)

    for val in param_values:
        for seed_idx in range(seed_count):
            game_seed = trial_seed = seed_start + seed_idx
            arm_spec = {**base, param_name: val, "seed": trial_seed}

            # Two games per arm: arm as P1, then reference as P1 (position swap).
            # Fresh strategies each yield so internal RNG starts clean.
            for swap in (False, True):
                pair = [
                    _instantiate(arm_spec),
                    MCTSStrategy(params=REFERENCE_PARAMS, seed=trial_seed),
                ]
                yield (pair[::-1] if swap else pair), game_seed


def get_generator(config: dict) -> Iterator[tuple[list[Strategy], int]]:
    """Get the appropriate generator based on config mode."""
    mode = config.get("mode", "continuous")

    if mode == "paired":
        return paired_generator(config)
    elif mode == "vs_reference":
        return vs_reference_generator(config)
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

    if mode == "vs_reference":
        param_values = config["compare"]["values"]
        seed_count = config["seeds"]["count"]
        return len(param_values) * seed_count * 2  # 2 games per seed (position swap)

    return None  # Continuous runs forever
