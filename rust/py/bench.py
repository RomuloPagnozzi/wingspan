"""Python vs Rust random-play speed on the same rules (no powers, M1).

    uv run python rust/py/bench.py [n_games]
"""

import random
import sys
import time

from wingspan.engine.actions import get_actions
from wingspan.engine.core import initiate_state
from wingspan.engine.engine import transition_state_inplace


def python_games(n: int) -> tuple[int, float]:
    t, steps = time.perf_counter(), 0
    for seed in range(n):
        s, rng = initiate_state(2, seed=seed), random.Random(seed)
        while actions := get_actions(s):
            transition_state_inplace(s, rng.choice(actions))
            steps += 1
    return steps, time.perf_counter() - t


def report(name: str, n: int, steps: int, secs: float) -> float:
    print(f"{name:<22} {n / secs:9.0f} games/s  {secs * 1e6 / steps:7.2f} us/decision")
    return secs / steps


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    report("python (with powers)", n, *python_games(n))
    import nopowers  # noqa: F401
    import wingspan_rs

    py = report("python (no powers)", n, *python_games(n))
    wingspan_rs.bench_games(10, 0)
    rs = report("rust (no powers)", 20 * n, *wingspan_rs.bench_games(20 * n, 1))
    print(f"speedup per decision, same rules: {py / rs:.0f}x")
