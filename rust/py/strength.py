"""Is flat_mc_rs as good as flat_mc? Budgets and settings from experiments/selfplay_flat_mc.yaml.

    uv run python rust/py/strength.py values [n_states]   # same estimates?
    uv run python rust/py/strength.py games [n_deals]     # head to head

`values`: on the same positions, run Python flat MC twice (different seeds) and Rust once. If the estimators
are equivalent, Rust vs Python disagrees no more than Python vs Python: same gap in per-move values, same
rate of picking the same move.

`games`: each deal is played twice with seats swapped; prints the running win rate and score difference.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))  # the repo root, for `lab`

import random
import statistics
import sys
from multiprocessing import Pool
from pathlib import Path

import yaml

CONFIG = Path(__file__).parents[2] / "experiments/selfplay_flat_mc.yaml"
WORKERS = 7


def params() -> dict:
    return {k: v for k, v in yaml.safe_load(CONFIG.read_text())["defaults"].items() if k != "strategy"}


def positions(n: int) -> list[tuple[int, int]]:
    """(game seed, step) of random-play positions with more than one legal move."""
    from wingspan.engine.actions import get_actions
    from wingspan.engine.core import initiate_state
    from wingspan.engine.engine import transition_state

    out, pick, seed = [], random.Random(0), 0
    while len(out) < n:
        s, step, rng = initiate_state(2, seed=seed), 0, random.Random(seed)
        while actions := get_actions(s):
            if len(actions) > 1 and pick.random() < 0.05:
                out.append((seed, step))
            s = transition_state(s, rng.choice(actions))
            step += 1
        seed += 1
    return out[:n]


def replay(seed: int, step: int):
    from wingspan.engine.actions import get_actions
    from wingspan.engine.core import initiate_state
    from wingspan.engine.engine import transition_state

    rng = random.Random(seed)  # the same moves as in positions()
    s = initiate_state(2, seed=seed)
    for _ in range(step):
        s = transition_state(s, rng.choice(get_actions(s)))
    return s


def estimate(task: tuple[int, int, str, int]) -> list[float]:
    import flat_mc_rs  # noqa: F401
    from wingspan.ai.base import create_strategy
    from wingspan.engine.actions import get_actions

    seed, step, strategy, strategy_seed = task
    s = replay(seed, step)
    legal = get_actions(s)
    st = create_strategy(strategy, seed=strategy_seed, **params())
    st.select_action(s, legal)
    values = st.get_last_action_values()
    return [values.get(a, float("-inf")) for a in legal]  # -inf: illegal in every re-dealt world


def values(n: int) -> None:
    pos = positions(n)
    tasks = [(seed, step, strat, k) for (seed, step) in pos for strat, k in (("flat_mc", 1), ("flat_mc", 2), ("flat_mc_rs", 3))]
    with Pool(WORKERS) as pool:
        out = pool.map(estimate, tasks, chunksize=1)
    def gap(u, v):
        d = [abs(x - y) for x, y in zip(u, v) if x > float("-inf") and y > float("-inf")]
        return statistics.fmean(d) if d else 0.0

    def mean(v):
        return statistics.fmean(x for x in v if x > float("-inf"))

    py_py, rs_py, same_py, same_rs = [], [], 0, 0
    for i in range(len(pos)):
        a, b, r = out[3 * i], out[3 * i + 1], out[3 * i + 2]
        py_py.append(gap(a, b))
        rs_py.append(gap(r, a))
        best = lambda v: max(range(len(v)), key=v.__getitem__)  # noqa: E731
        same_py += best(a) == best(b)
        same_rs += best(r) == best(a)
    print(f"{len(pos)} positions")
    print(f"  mean |value gap| per move: python vs python {statistics.fmean(py_py):.4f}, rust vs python {statistics.fmean(rs_py):.4f}")
    print(f"  same best move:            python vs python {same_py / len(pos):.1%}, rust vs python {same_rs / len(pos):.1%}")
    bias = [mean(r) - mean(a) for a, r in ((out[3 * i], out[3 * i + 2]) for i in range(len(pos)))]
    print(f"  mean value (rust - python): {statistics.fmean(bias):+.4f} (sd {statistics.stdev(bias):.4f}; ~0 if unbiased)")


def game(task: tuple[int, bool]) -> tuple[int, bool, int, int]:
    import flat_mc_rs  # noqa: F401
    from lab.simulation import simulate_game
    from wingspan.ai.base import create_strategy

    deal, rust_first = task
    names = ["flat_mc_rs", "flat_mc"] if rust_first else ["flat_mc", "flat_mc_rs"]
    seats = [create_strategy(n, seed=1000 * deal + i, **params()) for i, n in enumerate(names)]
    result, _ = simulate_game(seats, game_seed=deal, arm_labels=names)
    scores = {p.arm_label: p.total_score for p in result.players}
    return deal, rust_first, scores["flat_mc_rs"], scores["flat_mc"]


def games(n: int) -> None:
    tasks = [(deal, first) for deal in range(10_000, 10_000 + n) for first in (True, False)]
    wins = ties = done = 0
    diffs = []
    with Pool(WORKERS) as pool:
        for deal, first, rs, py in pool.imap_unordered(game, tasks):
            done += 1
            wins += rs > py
            ties += rs == py
            diffs.append(rs - py)
            rate = (wins + ties / 2) / done
            se = (rate * (1 - rate) / done) ** 0.5
            sd = statistics.stdev(diffs) if done > 1 else 0
            print(
                f"{done:4} games: rust win rate {rate:.1%} ± {1.96 * se:.1%}, "
                f"score diff {statistics.fmean(diffs):+.2f} ± {1.96 * sd / done**0.5:.2f}  "
                f"(deal {deal}, rust {'first' if first else 'second'}: {rs}-{py})",
                flush=True,
            )


if __name__ == "__main__":
    mode = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else (200 if mode == "values" else 120)
    {"values": values, "games": games}[mode](n)
