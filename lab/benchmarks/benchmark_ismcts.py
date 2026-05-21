"""Benchmark IS-MCTS per-sim cost vs peek-MCTS at matched sim counts.

The expected slowdown comes from per-simulation redeterminization (one shuffle
+ list slicing) plus re-walking the tree from a fresh root each sim instead
of resuming from cached node states.
"""

import time
from statistics import mean, stdev

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import MCTSStrategy, MCTSConfig, RandomStrategy


def _advance_to_branching_state(state, min_actions: int = 3):
    """Advance the game with random play until we hit a decision with multiple actions."""
    random_strategy = RandomStrategy(seed=42)
    while True:
        actions = get_actions(state)
        if not actions:
            return None
        if len(actions) >= min_actions:
            return state
        state = transition_state(state, random_strategy.select_action(state, actions))


def _time_one_decision(state, params: MCTSConfig) -> float:
    strategy = MCTSStrategy(params=params, seed=123)
    actions = get_actions(state)
    start = time.perf_counter()
    strategy.select_action(state, actions)
    return time.perf_counter() - start


def benchmark(sim_counts: list[int], moves_per_count: int = 5) -> None:
    print(f"IS-MCTS vs peek-MCTS per-sim cost ({moves_per_count} decisions averaged)\n")
    header = (
        f"{'Sims':>6} | {'peek (s)':>10} | {'ismcts (s)':>11} | "
        f"{'peek µs/sim':>12} | {'ismcts µs/sim':>14} | {'ratio':>6}"
    )
    print(header)
    print("-" * len(header))

    for sims in sim_counts:
        peek_times: list[float] = []
        ismcts_times: list[float] = []

        for trial in range(moves_per_count):
            state = initiate_state(2, seed=trial)
            branching = _advance_to_branching_state(state)
            if branching is None:
                continue
            peek_times.append(
                _time_one_decision(
                    branching, MCTSConfig(simulations=sims, determinize=False)
                )
            )
            ismcts_times.append(
                _time_one_decision(
                    branching, MCTSConfig(simulations=sims, determinize=True)
                )
            )

        if not peek_times or not ismcts_times:
            continue

        peek_avg = mean(peek_times)
        ismcts_avg = mean(ismcts_times)
        peek_per_sim_us = (peek_avg / sims) * 1_000_000
        ismcts_per_sim_us = (ismcts_avg / sims) * 1_000_000
        ratio = ismcts_avg / peek_avg if peek_avg > 0 else float("inf")

        print(
            f"{sims:>6} | {peek_avg:>10.3f} | {ismcts_avg:>11.3f} | "
            f"{peek_per_sim_us:>12.1f} | {ismcts_per_sim_us:>14.1f} | {ratio:>5.2f}x"
        )


if __name__ == "__main__":
    benchmark([50, 100, 250, 500], moves_per_count=3)
