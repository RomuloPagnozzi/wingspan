"""Benchmark MCTS performance at different simulation counts."""

import time
from statistics import mean, stdev

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import MCTSStrategy, MCTSConfig, RandomStrategy


def benchmark_single_move(state, strategy) -> float:
    """Time a single move decision. Returns seconds."""
    actions = get_actions(state)
    if not actions:
        return 0.0

    start = time.perf_counter()
    strategy.select_action(state, actions)
    return time.perf_counter() - start


def advance_to_main_turn(state):
    """Play random moves until we reach a MAIN_TURN phase with choices."""
    random_strategy = RandomStrategy(seed=42)

    while True:
        actions = get_actions(state)
        if not actions:
            return None  # Game over

        # Check if we have meaningful choices (more than 1 action)
        if len(actions) > 2:
            return state

        action = random_strategy.select_action(state, actions)
        state = transition_state(state, action)


def benchmark_simulations(sim_counts: list[int], moves_per_count: int = 5):
    """Benchmark MCTS at different simulation counts."""
    print(f"Benchmarking MCTS (averaging over {moves_per_count} moves per config)\n")
    print(
        f"{'Simulations':>12} | {'Mean (s)':>10} | {'Std (s)':>10} | {'Per sim (ms)':>12}"
    )
    print("-" * 55)

    for sims in sim_counts:
        strategy = MCTSStrategy(config=MCTSConfig(simulations=sims), seed=123)
        times = []

        for i in range(moves_per_count):
            # Fresh game state for each measurement
            state = initiate_state(2)
            state = advance_to_main_turn(state)

            if state is None:
                continue

            elapsed = benchmark_single_move(state, strategy)
            times.append(elapsed)

        if times:
            avg = mean(times)
            std = stdev(times) if len(times) > 1 else 0.0
            per_sim_ms = (avg / sims) * 1000

            print(f"{sims:>12} | {avg:>10.3f} | {std:>10.3f} | {per_sim_ms:>12.4f}")


def estimate_game_time(sims: int, moves_per_game: int = 200):
    """Estimate total time for one game at given simulation count."""
    strategy = MCTSStrategy(config=MCTSConfig(simulations=sims), seed=123)

    state = initiate_state(2)
    state = advance_to_main_turn(state)

    if state is None:
        return

    elapsed = benchmark_single_move(state, strategy)
    estimated_game = elapsed * moves_per_game

    print(f"\nEstimated time per game with {sims} simulations:")
    print(
        f"  ~{moves_per_game} moves/game × {elapsed:.3f}s/move = {estimated_game:.1f}s ({estimated_game/60:.1f} min)"
    )


def benchmark_parallel(sims: int = 500, worker_counts: list[int] = []):
    """Benchmark parallelization speedup."""
    if not worker_counts:
        worker_counts = [1, 2, 4]

    print(f"\n{'='*60}")
    print(f"Parallelization Benchmark ({sims} simulations/move)")
    print("=" * 60)
    print(f"{'Workers':>8} | {'Time (s)':>10} | {'Speedup':>10}")
    print("-" * 35)

    baseline_time = None

    for workers in worker_counts:
        config = MCTSConfig(simulations=sims, num_workers=workers)
        strategy = MCTSStrategy(config=config, seed=42)

        state = initiate_state(2)
        state = advance_to_main_turn(state)

        if state is None:
            continue

        elapsed = benchmark_single_move(state, strategy)

        if baseline_time is None:
            baseline_time = elapsed
            speedup = 1.0
        else:
            speedup = baseline_time / elapsed

        print(f"{workers:>8} | {elapsed:>10.3f} | {speedup:>10.2f}x")


if __name__ == "__main__":
    sim_counts = [10, 50, 100, 250, 500, 1000]

    benchmark_simulations(sim_counts, moves_per_count=3)
    estimate_game_time(100)
    estimate_game_time(500)
    benchmark_parallel(sims=500, worker_counts=[1, 2, 4])
