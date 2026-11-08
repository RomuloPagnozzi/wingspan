"""Time full self-play games with the config of experiments/selfplay_flat_mc.yaml: Python flat_mc vs
flat_mc_rs (Rust playouts), both seats, one process.

    uv run python rust/py/selfplay_bench.py [n_rust_games] [n_python_games]
"""

import sys
import time
from pathlib import Path

import yaml

import flat_mc_rs  # noqa: F401  (registers flat_mc_rs)

from lab.simulation import simulate_game
from wingspan.ai.base import create_strategy

CONFIG = Path(__file__).parents[2] / "experiments/selfplay_flat_mc.yaml"


def time_games(strategy: str, n: int) -> list[tuple[float, list[int]]]:
    params = {k: v for k, v in yaml.safe_load(CONFIG.read_text())["defaults"].items() if k != "strategy"}
    out = []
    for g in range(n):
        seats = [create_strategy(strategy, seed=1000 * g + i, **params) for i in range(2)]
        t = time.perf_counter()
        result, _ = simulate_game(seats, game_seed=g, arm_labels=["a", "b"], record_decisions=True)
        out.append((time.perf_counter() - t, [p.total_score for p in result.players]))
        print(f"  {strategy} game {g}: {out[-1][0]:6.1f}s  scores {out[-1][1]}", flush=True)
    return out


if __name__ == "__main__":
    n_rs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    n_py = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rs = time_games("flat_mc_rs", n_rs)
    py = time_games("flat_mc", n_py)
    t_rs = sum(t for t, _ in rs) / len(rs)
    t_py = sum(t for t, _ in py) / len(py) if py else float("nan")
    print(f"seconds/game: python {t_py:.1f}, rust {t_rs:.2f} -> {t_py / t_rs:.0f}x")
