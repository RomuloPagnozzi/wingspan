"""Run a single Optuna trial: N seeds vs the reference, each from both seats; return the win rate.

Same games as a `vs_reference` run (`lab.generators.both_seats`), with any registered strategy as the
candidate (`mcts`, `mcts_rs`, `flat_mc`, ...) and any strategy spec as the reference. Reports the
running win rate to Optuna after each seed so the pruner can cut losers short.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import optuna

from lab.data import DecisionsWriter, GamesWriter
from lab.generators import both_seats, instantiate
from lab.simulation import play_games
from wingspan.ai import Strategy

NOT_PARAMS = {"strategy", "seed"}


def arm_spec(base: dict, sampled: dict[str, Any]) -> dict:
    """The candidate's strategy spec: `base` (default strategy `mcts`) plus the sampled params.

    Strategies drop keyword arguments they don't know, which would silently turn a typo in `base` or
    `space` into a no-op; so every key must show up in the strategy's config.
    """
    spec = {"strategy": "mcts", **base, **sampled}
    unknown = set(spec) - NOT_PARAMS - set(instantiate(spec).config)
    if unknown:
        raise ValueError(f"unknown {spec['strategy']} param(s): {sorted(unknown)}")
    return spec


def _trial_games(
    arm: dict, reference: dict, seed_count: int, seed_start: int, arm_label: str, ref_label: str
) -> Iterator[tuple[list[Strategy], int, list[str]]]:
    for game_seed in range(seed_start, seed_start + seed_count):
        yield from both_seats({**arm, "seed": game_seed}, {**reference, "seed": game_seed}, game_seed, [arm_label, ref_label])


def run_trial(
    trial: optuna.Trial,
    arm: dict,
    reference: dict,
    seed_count: int,
    seed_start: int,
    num_workers: int,
    run_dir: Path,
    run_id: str,
    arm_label: str = "candidate",
    ref_label: str = "reference",
) -> float:
    """Play one trial's games and return the candidate's win rate (ties count 0.5).

    Games and decisions are streamed to `run_dir/<run_id>/`; the run_id is the key into trials.csv.
    Raises optuna.TrialPruned when the pruner says so.
    """
    games = _trial_games(arm, reference, seed_count, seed_start, arm_label, ref_label)
    work = ((s, gs, labels, idx, True) for idx, (s, gs, labels) in enumerate(games))
    points, played = 0.0, 0

    with GamesWriter(run_dir, run_id) as writer, DecisionsWriter(run_dir, run_id) as decisions_writer:
        # In order, so every two consecutive results are one seed's pair of games
        for result, decisions, _idx in play_games(work, num_workers, ordered=True):
            writer.add_game(result)
            if decisions:
                decisions_writer.add_game_decisions(decisions)
            winner = result.winner_label()
            points += 1.0 if winner == arm_label else 0.5 if winner is None else 0.0
            played += 1
            if played % 2 == 0:
                trial.report(points / played, step=played // 2)
                if trial.should_prune():
                    raise optuna.TrialPruned(
                        f"pruned at seed {played // 2}/{seed_count} (running win rate {points / played:.3f})"
                    )
    return points / played if played else 0.0
