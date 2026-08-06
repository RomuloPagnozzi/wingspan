"""Run a single Optuna trial: N paired seeds vs REFERENCE_PARAMS, return win rate.

Mirrors `vs_reference` semantics: for each game_seed, run two games with
position swap, attribute by position. Reports running win rate to Optuna
after each seed so the pruner can short-circuit losers.
"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
from typing import Any, Iterator

import optuna

from lab.data import DecisionsWriter, GamesWriter
from lab.generators import REFERENCE_PARAMS
from lab.simulation import game_worker_init, run_one_game
from lab.strategies import MCTSConfig, MCTSStrategy, Strategy, ValueFunction


# Mirrors lab/__main__._attribute_by_position. Kept local to avoid coupling.
def _attribute(result, in_pair_idx: int) -> str:
    """Arm A is P0 on even in-pair idx, P1 on odd (position-swap aware)."""
    a_idx = 0 if in_pair_idx % 2 == 0 else 1
    if result.players[a_idx].is_winner:
        return "A"
    if any(p.is_winner for p in result.players):
        return "B"
    return "ties"


def _build_arm_config(base: dict, sampled: dict[str, Any]) -> MCTSConfig:
    """Merge base + sampled params into an MCTSConfig.

    `value_function` arrives as a string from YAML/categorical; coerce.
    """
    merged = {**base, **sampled}
    vf = merged.get("value_function")
    if isinstance(vf, str):
        merged["value_function"] = ValueFunction(vf)
    valid = MCTSConfig.__dataclass_fields__.keys()
    unknown = set(merged) - set(valid)
    if unknown:
        raise ValueError(f"unknown MCTSConfig field(s): {sorted(unknown)}")
    return MCTSConfig(**merged)


def _trial_pairs(
    arm_cfg: MCTSConfig,
    seed_count: int,
    seed_start: int,
    arm_label: str,
    ref_label: str,
) -> Iterator[tuple[int, list[Strategy], int, list[str]]]:
    """Yield (seed_idx, strategies, game_seed, labels) for both swap positions.

    Two games per seed_idx (swap=False then swap=True). Caller groups by
    seed_idx for per-seed pruning.
    """
    for seed_idx in range(seed_count):
        game_seed = trial_seed = seed_start + seed_idx
        labels = [arm_label, ref_label]
        for swap in (False, True):
            pair = [
                MCTSStrategy(params=arm_cfg, seed=trial_seed),
                MCTSStrategy(params=REFERENCE_PARAMS, seed=trial_seed),
            ]
            if swap:
                yield seed_idx, pair[::-1], game_seed, labels[::-1]
            else:
                yield seed_idx, pair, game_seed, labels


def run_trial(
    trial: optuna.Trial,
    arm_cfg: MCTSConfig,
    seed_count: int,
    seed_start: int,
    num_workers: int,
    run_dir: Path,
    run_id: str,
    arm_label: str = "candidate",
    ref_label: str = "reference",
) -> float:
    """Run one trial's worth of paired games and return win rate (ties=0.5).

    Reports running win rate after each completed seed pair (2 games) so the
    pruner can short-circuit. Raises optuna.TrialPruned if pruner says so.

    Games are streamed to `run_dir/<run_id>/games.parquet` under the existing
    schema. The trial's run_id is the cross-reference key into trials.csv.
    """
    pairs = _trial_pairs(arm_cfg, seed_count, seed_start, arm_label, ref_label)
    work = ((s, gs, lbl, idx, True) for idx, (_, s, gs, lbl) in enumerate(pairs))

    # Buffer per seed_idx: each seed produces 2 games. We can report once
    # both are in. Track per-seed tallies for incremental reporting.
    tally = {"A": 0, "B": 0, "ties": 0}
    games_in_seed = 0
    seed_idx_done = 0

    def _record(result, game_idx: int):
        nonlocal games_in_seed, seed_idx_done
        # game_idx within trial: even=swap False (A=P0), odd=swap True (A=P1)
        tally[_attribute(result, game_idx)] += 1
        games_in_seed += 1
        if games_in_seed == 2:
            games_in_seed = 0
            seed_idx_done += 1
            wr = (tally["A"] + 0.5 * tally["ties"]) / sum(tally.values())
            trial.report(wr, step=seed_idx_done)
            if trial.should_prune():
                raise optuna.TrialPruned(
                    f"pruned at seed {seed_idx_done}/{seed_count} "
                    f"(running win rate {wr:.3f})"
                )

    with GamesWriter(run_dir, run_id) as writer:
        decisions_writer = DecisionsWriter(run_dir, run_id)
        try:
            if num_workers <= 1:
                for game_idx, item in enumerate(work):
                    result, decisions, _meta = run_one_game(item)
                    writer.add_game(result)
                    if decisions:
                        decisions_writer.add_game_decisions(decisions)
                    _record(result, game_idx)
            else:
                ctx = mp.get_context("spawn")
                # imap (not imap_unordered) so completion order == submission
                # order → game_idx parity correctly reflects swap state.
                with ctx.Pool(num_workers, initializer=game_worker_init) as pool:
                    for game_idx, (result, decisions, _m) in enumerate(
                        pool.imap(run_one_game, work, chunksize=1)
                    ):
                        writer.add_game(result)
                        if decisions:
                            decisions_writer.add_game_decisions(decisions)
                        _record(result, game_idx)
        finally:
            decisions_writer.close()

    total = sum(tally.values())
    if total == 0:
        return 0.0
    return (tally["A"] + 0.5 * tally["ties"]) / total
