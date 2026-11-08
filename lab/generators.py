"""Experiment generators that yield (strategies, game_seed, arm_labels) tuples."""

import itertools
import random
import time
from dataclasses import asdict
from enum import Enum
from typing import Iterator

from wingspan.ai import MCTSConfig, Strategy, ValueFunction, create_strategy

# Project-wide fixed reference opponent. Locked strategic params. Changing
# these constants invalidates cross-experiment comparability — pre-change
# and post-change win rates do not live on the same scale.
REFERENCE_PARAMS = MCTSConfig(
    simulations=1500,
    exploration_constant=2.27,
    value_function=ValueFunction.ABSOLUTE_SCORE,
    determinize=True,
    widening_alpha=0.83,
    widening_k=1.7,
)


def instantiate(spec: dict) -> Strategy:
    """Create a strategy from a fully-merged spec dict (with 'strategy' key)."""
    return create_strategy(
        spec["strategy"], **{k: v for k, v in spec.items() if k != "strategy"}
    )


def seed_range(seeds: dict) -> Iterator[int]:
    """The game seeds of a `seeds: {start, count}` block: `count` seeds from `start` (default 1), or
    endless without a count. `start: clock` starts from the current time in seconds, a range no
    earlier run can have used."""
    start, count = seeds.get("start", 1), seeds.get("count")
    if start == "clock":
        start = int(time.time())
    return itertools.count(start) if count is None else iter(range(start, start + count))


def build_strategy(spec: dict, defaults: dict) -> Strategy:
    """Build a strategy from spec dict merged with defaults.

    The `label` key is consumed by the runner (it identifies the arm in
    results) and stripped before instantiation.
    """
    merged = {**defaults, **spec}
    merged.pop("label", None)
    return instantiate(merged)


def continuous_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Generate games continuously for matchup experiments.

    Yields (strategies, game_seed, arm_labels) tuples indefinitely, with random seeds; the caller
    stops it (e.g., via SIGINT). With a `seeds` block (see `seed_range`) it plays exactly one game per
    seed instead, cycling through the matchups: each game gets its own deal, and the players'
    strategy seeds derive from it, so the run can be reproduced.
    """
    defaults = config.get("defaults", {})
    matchup_specs = config["matchups"]
    games_per_round = defaults.get("games_per_round", 5)

    if "seeds" in config:  # reproducible: one game per seed, a new deal each
        for k, game_seed in enumerate(seed_range(config["seeds"])):
            spec_list = matchup_specs[k % len(matchup_specs)]
            strategies = [
                build_strategy({**spec, "seed": 2 * game_seed + i}, defaults)
                for i, spec in enumerate(spec_list)
            ]
            yield strategies, game_seed, [spec["label"] for spec in spec_list]
        return

    while True:
        for spec_list in matchup_specs:
            for _ in range(games_per_round):
                strategies = [build_strategy(spec, defaults) for spec in spec_list]
                labels = [spec["label"] for spec in spec_list]
                game_seed = random.randint(0, 2**31)
                yield strategies, game_seed, labels


def _arm_overrides(arm: dict, param_name: str | None) -> dict:
    """Return the dict of MCTSConfig fields this arm overrides on top of base.

    Supports two shapes:
    - {label, value}            paired with compare.parameter (single-field sweep)
    - {label, overrides: {...}} arbitrary multi-field override (no parameter needed)
    """
    if "overrides" in arm:
        return arm["overrides"] or {}
    return {param_name: arm["value"]}


def both_seats(
    spec_a: dict, spec_b: dict, game_seed: int, labels: list[str]
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """The same deal twice: A in the first seat, then in the second (position swap). Strategies are
    built fresh for every game, so their internal RNG starts clean."""
    yield [instantiate(spec_a), instantiate(spec_b)], game_seed, labels
    yield [instantiate(spec_b), instantiate(spec_a)], game_seed, labels[::-1]


def paired_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Every pair of arms in `compare.values` plays each seed from both seats.

    Seed-major: all pairs play a seed before the next one starts, so a run stopped at any point (or an
    open-ended one, see `seed_range`) has about as many games for every pair. Both players get the
    seed as their strategy seed; only their params differ.
    """
    base, compare = config["base"], config["compare"]
    param_name = compare.get("parameter")
    pairs = list(itertools.combinations(compare["values"], 2))
    for game_seed in seed_range(config["seeds"]):
        for a, b in pairs:
            yield from both_seats(
                {**base, **_arm_overrides(a, param_name), "seed": game_seed},
                {**base, **_arm_overrides(b, param_name), "seed": game_seed},
                game_seed,
                [a["label"], b["label"]],
            )


def reference_spec(block: dict) -> dict:
    """The opponent of a `vs_reference` run (`block` = its `compare`) or a tuning study (`block` = the
    whole config), as a strategy spec: `block["reference"]` if given (e.g. `{strategy: flat_mc_rs,
    playouts: 1500}`), else the project-wide REFERENCE_PARAMS."""
    default = {k: v.value if isinstance(v, Enum) else v for k, v in asdict(REFERENCE_PARAMS).items()}
    return block.get("reference") or {"strategy": "mcts", **default}


def vs_reference_generator(
    config: dict,
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    """Every arm in `compare.values` plays the reference on each seed from both seats.

    Seed-major like `paired_generator`, so the arms stay balanced however long the run goes.
    """
    base, compare = config["base"], config["compare"]
    param_name = compare.get("parameter")
    reference = reference_spec(compare)
    for game_seed in seed_range(config["seeds"]):
        for arm in compare["values"]:
            yield from both_seats(
                {**base, **_arm_overrides(arm, param_name), "seed": game_seed},
                {**reference, "seed": game_seed},
                game_seed,
                [arm["label"], compare["reference_label"]],
            )


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

    count = config.get("seeds", {}).get("count")  # None: endless
    if count is None:
        return None
    arms = config["compare"]["values"] if mode in ("paired", "vs_reference") else []
    if mode == "paired":
        return len(list(itertools.combinations(arms, 2))) * count * 2  # ×2: position swap
    if mode == "vs_reference":
        return len(arms) * count * 2
    return count  # continuous with seeds: one game per seed


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
        isinstance(arm, dict)
        and "label" in arm
        and ("value" in arm or "overrides" in arm),
        f"{where}: arm #{idx} must be a mapping with `label` and either "
        f"`value` (single-field sweep) or `overrides` (multi-field) (got {arm!r})",
    )
    _require(
        isinstance(arm["label"], str) and arm["label"],
        f"{where}: arm #{idx} `label` must be a non-empty string (got {arm['label']!r})",
    )
    if "overrides" in arm:
        _require(
            isinstance(arm["overrides"], dict) and arm["overrides"],
            f"{where}: arm #{idx} `overrides` must be a non-empty mapping "
            f"(got {arm['overrides']!r})",
        )


def validate_seeds(seeds, where: str) -> None:
    """A `seeds` block: `start` an int or "clock" (default 1), `count` a positive int or absent (endless)."""
    _require(isinstance(seeds, dict), f"{where}: `seeds` must be a mapping with `start` and/or `count`")
    start, count = seeds.get("start", 1), seeds.get("count")
    _require(start == "clock" or isinstance(start, int), f"{where}: `seeds.start` must be an int or \"clock\"")
    _require(count is None or (isinstance(count, int) and count > 0), f"{where}: `seeds.count` must be a positive int")


def validate_strategy_spec(spec, where: str) -> None:
    _require(isinstance(spec, dict) and isinstance(spec.get("strategy"), str),
             f"{where}: must be a strategy spec, a mapping with a `strategy` name (got {spec!r})")


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
        arms = compare.get("values")
        # `parameter` is required only when at least one arm uses {value: ...}.
        if isinstance(arms, list) and any(
            isinstance(a, dict) and "overrides" not in a for a in arms
        ):
            _require(
                "parameter" in compare,
                f"mode={mode}: `compare.parameter` is required when arms use `value`",
            )
        min_arms = 1 if mode == "vs_reference" else 2
        _require(
            isinstance(arms, list) and len(arms) >= min_arms,
            f"mode={mode}: `compare.values` must be a list of at least {min_arms} "
            f"arm{'s' if min_arms > 1 else ''}",
        )
        for i, arm in enumerate(arms):
            _validate_arm(arm, i, "compare.values")
        _validate_unique_labels([a["label"] for a in arms], "compare.values")
        validate_seeds(config.get("seeds"), f"mode={mode}")

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
            if "reference" in compare:
                validate_strategy_spec(compare["reference"], "compare.reference")
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
        if "seeds" in config:
            validate_seeds(config["seeds"], "mode=continuous")
        return

    raise ConfigError(f"Unknown mode: {mode!r}")
