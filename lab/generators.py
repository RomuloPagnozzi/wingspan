"""Experiment generators that yield (strategies, game_seed, arm_labels) tuples."""

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
    determinize=True,
)


def _instantiate(spec: dict) -> Strategy:
    """Create a strategy from a fully-merged spec dict (with 'strategy' key)."""
    return create_strategy(
        spec["strategy"], **{k: v for k, v in spec.items() if k != "strategy"}
    )


def build_strategy(spec: dict, defaults: dict) -> Strategy:
    """Build a strategy from spec dict merged with defaults.

    The `label` key is consumed by the runner (it identifies the arm in
    results) and stripped before instantiation.
    """
    merged = {**defaults, **spec}
    merged.pop("label", None)
    return _instantiate(merged)


def continuous_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Generate games continuously for matchup experiments.

    Yields (strategies, game_seed, arm_labels) tuples indefinitely.
    Caller is responsible for stopping (e.g., via SIGINT).
    """
    defaults = config.get("defaults", {})
    matchup_specs = config["matchups"]
    games_per_round = defaults.get("games_per_round", 5)

    while True:
        for spec_list in matchup_specs:
            for _ in range(games_per_round):
                strategies = [build_strategy(spec, defaults) for spec in spec_list]
                labels = [spec["label"] for spec in spec_list]
                game_seed = random.randint(0, 2**31)
                yield strategies, game_seed, labels


def paired_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Generate paired comparison games with controlled seeds.

    For each pair of arms in compare.values, generates games with:
    - Same game_seed for position-swapped games
    - Same strategy seed for both players (only param differs)
    """
    base = config["base"]
    compare = config["compare"]
    seeds_config = config["seeds"]

    param_name = compare["parameter"]
    arms = compare["values"]  # each: {"value": ..., "label": ...}
    seed_count = seeds_config["count"]
    seed_start = seeds_config.get("start", 1)

    for arm_a, arm_b in itertools.combinations(arms, 2):
        for seed_idx in range(seed_count):
            game_seed = trial_seed = seed_start + seed_idx

            config_a = {**base, param_name: arm_a["value"], "seed": trial_seed}
            config_b = {**base, param_name: arm_b["value"], "seed": trial_seed}
            labels = [arm_a["label"], arm_b["label"]]

            # Two games per pair: A as P1, then B as P1 (position swap).
            # Fresh strategies each yield so internal RNG starts clean.
            for swap in (False, True):
                pair = [_instantiate(config_a), _instantiate(config_b)]
                if swap:
                    yield pair[::-1], game_seed, labels[::-1]
                else:
                    yield pair, game_seed, labels


def vs_reference_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Generate games of each arm against the fixed reference opponent.

    For each value in `compare.values`, runs `seeds.count` paired comparisons
    against REFERENCE_PARAMS. Same paired-comparison machinery as
    `paired_generator`, with one side fixed to the reference.
    """
    base = config["base"]
    compare = config["compare"]
    seeds_config = config["seeds"]

    param_name = compare["parameter"]
    arms = compare["values"]  # each: {"value": ..., "label": ...}
    reference_label = compare["reference_label"]
    seed_count = seeds_config["count"]
    seed_start = seeds_config.get("start", 1)

    for arm in arms:
        for seed_idx in range(seed_count):
            game_seed = trial_seed = seed_start + seed_idx
            arm_spec = {**base, param_name: arm["value"], "seed": trial_seed}
            labels = [arm["label"], reference_label]

            for swap in (False, True):
                pair = [
                    _instantiate(arm_spec),
                    MCTSStrategy(params=REFERENCE_PARAMS, seed=trial_seed),
                ]
                if swap:
                    yield pair[::-1], game_seed, labels[::-1]
                else:
                    yield pair, game_seed, labels


def get_generator(config: dict) -> Iterator[tuple[list[Strategy], int, list[str]]]:
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
        arms = config["compare"]["values"]
        seed_count = config["seeds"]["count"]
        num_pairs = len(list(itertools.combinations(arms, 2)))
        return num_pairs * seed_count * 2  # 2 games per seed (position swap)

    if mode == "vs_reference":
        arms = config["compare"]["values"]
        seed_count = config["seeds"]["count"]
        return len(arms) * seed_count * 2  # 2 games per seed (position swap)

    return None  # Continuous runs forever


# =============================================================================
# Config validation
# =============================================================================


class ConfigError(ValueError):
    """Raised when a config is missing required arm labels or is malformed."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _validate_arm(arm, idx: int, where: str) -> None:
    _require(
        isinstance(arm, dict) and "value" in arm and "label" in arm,
        f"{where}: arm #{idx} must be a mapping with both `value` and `label` "
        f"(got {arm!r})",
    )
    _require(
        isinstance(arm["label"], str) and arm["label"],
        f"{where}: arm #{idx} `label` must be a non-empty string (got {arm['label']!r})",
    )


def _validate_unique_labels(labels: list[str], where: str) -> None:
    seen: set[str] = set()
    for label in labels:
        _require(label not in seen, f"{where}: duplicate label {label!r}")
        seen.add(label)


def validate_config(config: dict) -> None:
    """Validate that every arm in the config has a mandatory `label`.

    Raises ConfigError with a precise message on the first violation.
    """
    mode = config.get("mode", "continuous")

    if mode in ("paired", "vs_reference"):
        compare = config.get("compare")
        _require(isinstance(compare, dict), f"mode={mode}: missing `compare` block")
        _require(
            "parameter" in compare, f"mode={mode}: `compare.parameter` is required"
        )
        arms = compare.get("values")
        min_arms = 1 if mode == "vs_reference" else 2
        _require(
            isinstance(arms, list) and len(arms) >= min_arms,
            f"mode={mode}: `compare.values` must be a list of at least {min_arms} "
            f"arm{'s' if min_arms > 1 else ''}",
        )
        for i, arm in enumerate(arms):
            _validate_arm(arm, i, f"compare.values")
        _validate_unique_labels([a["label"] for a in arms], "compare.values")

        if mode == "vs_reference":
            ref_label = compare.get("reference_label")
            _require(
                isinstance(ref_label, str) and ref_label,
                "mode=vs_reference: `compare.reference_label` is required "
                "(non-empty string)",
            )
            _require(
                ref_label not in {a["label"] for a in arms},
                f"mode=vs_reference: reference_label {ref_label!r} collides "
                "with an arm label",
            )
        return

    if mode == "continuous":
        matchups = config.get("matchups")
        _require(
            isinstance(matchups, list) and matchups,
            "mode=continuous: `matchups` must be a non-empty list",
        )
        for m_idx, spec_list in enumerate(matchups):
            _require(
                isinstance(spec_list, list) and len(spec_list) >= 2,
                f"matchups[{m_idx}]: must be a list of at least 2 strategy specs",
            )
            labels: list[str] = []
            for s_idx, spec in enumerate(spec_list):
                where = f"matchups[{m_idx}][{s_idx}]"
                _require(
                    isinstance(spec, dict) and "label" in spec,
                    f"{where}: missing required `label` key (got {spec!r})",
                )
                _require(
                    isinstance(spec["label"], str) and spec["label"],
                    f"{where}: `label` must be a non-empty string "
                    f"(got {spec['label']!r})",
                )
                labels.append(spec["label"])
            _validate_unique_labels(labels, f"matchups[{m_idx}]")
        return

    raise ConfigError(f"Unknown mode: {mode!r}")
