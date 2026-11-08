"""Does mcts_rs search like mcts? Champion params (bots.yaml mcts-v1), same positions: Python twice
(different seeds), Rust once. Equivalent searches disagree with Python no more than Python with itself.

    PYTHONPATH=.:rust/py uv run python rust/py/mcts_check.py [n_positions]
"""

import statistics
import sys
from multiprocessing import Pool
from pathlib import Path

import yaml

from strength import positions, replay

PARAMS = yaml.safe_load((Path(__file__).parents[2] / "src/wingspan/ai/bots.yaml").read_text())["bots"]["mcts-v1"]["params"]


def search(task):
    import mcts_rs  # noqa: F401
    from wingspan.ai.base import create_strategy
    from wingspan.engine.actions import get_actions

    seed, step, strategy, k = task
    s = replay(seed, step)
    legal = get_actions(s)
    st = create_strategy(strategy, seed=k, **PARAMS)
    st.select_action(s, legal)
    v = st.get_last_visit_counts()
    total = sum(v.values()) or 1
    return [v.get(a, 0) / total for a in legal]


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    pos = positions(n)
    tasks = [(s, t, strat, k) for s, t in pos for strat, k in (("mcts", 1), ("mcts", 2), ("mcts_rs", 3))]
    with Pool(7) as pool:
        out = pool.map(search, tasks, chunksize=1)
    best = lambda v: max(range(len(v)), key=v.__getitem__)  # noqa: E731
    tv = lambda u, w: 0.5 * sum(abs(x - y) for x, y in zip(u, w))  # noqa: E731  total variation
    pp, rp, sp, sr = [], [], 0, 0
    for i in range(len(pos)):
        a, b, r = out[3 * i : 3 * i + 3]
        pp.append(tv(a, b))
        rp.append(tv(r, a))
        sp += best(a) == best(b)
        sr += best(r) == best(a)
    print(f"{len(pos)} positions, {PARAMS['simulations']} simulations")
    print(f"  visit-share distance (TV): python vs python {statistics.fmean(pp):.3f}, rust vs python {statistics.fmean(rp):.3f}")
    print(f"  same most-visited move:    python vs python {sp / len(pos):.1%}, rust vs python {sr / len(pos):.1%}")
