"""Self-play throughput with 7 worker processes, as in experiments/selfplay_flat_mc.yaml: Python flat_mc
vs flat_mc_rs. Each engine gets its own pool and a fixed number of games.

    uv run python rust/py/throughput_bench.py [python_games] [rust_games] [workers]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))  # the repo root, for `lab`

import time
from multiprocessing import Pool

import yaml

CONFIG = Path(__file__).parents[2] / "experiments/selfplay_flat_mc.yaml"


def play(task: tuple[str, int]) -> float:
    import flat_mc_rs  # noqa: F401  (registers flat_mc_rs)
    from lab.simulation import simulate_game
    from wingspan.ai.base import create_strategy

    strategy, g = task
    params = {k: v for k, v in yaml.safe_load(CONFIG.read_text())["defaults"].items() if k != "strategy"}
    seats = [create_strategy(strategy, seed=1000 * g + i, **params) for i in range(2)]
    t = time.perf_counter()
    simulate_game(seats, game_seed=g, arm_labels=["a", "b"], record_decisions=True)
    return time.perf_counter() - t


def run(strategy: str, n: int, workers: int) -> None:
    if not n:
        return
    t = time.perf_counter()
    with Pool(workers) as pool:
        per_game = pool.map(play, [(strategy, g) for g in range(n)], chunksize=1)
    wall = time.perf_counter() - t
    print(
        f"{strategy:<11} {n:3} games on {workers} workers: wall {wall:6.1f}s, "
        f"{sum(per_game) / n:6.1f}s per game in a worker, {3600 * n / wall:6.0f} games/hour",
        flush=True,
    )


if __name__ == "__main__":
    n_py = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    n_rs = int(sys.argv[2]) if len(sys.argv) > 2 else 70
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    run("flat_mc_rs", n_rs, workers)
    run("flat_mc", n_py, workers)
