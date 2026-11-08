"""How do the tree's root visits and Q values look as simulations grow? Real positions (replayed from the
Rust self-play games), searched by the champion IS-MCTS at several budgets.

Per phase and budget: visit spread (effective number of moves = exp(visit entropy); equals the number of
legal moves when visits are uniform), the top move's visit share, the Q gap between the best and second
best move (in points), and how often the most-visited move is also the best-valued one.

    uv run python rust/py/visits.py [n_games] [positions_per_game]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))  # the repo root, for `lab`

import glob
import json
import math
import random
import statistics
from collections import defaultdict
from multiprocessing import Pool

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).parents[2]
DATA = ROOT / "experiments/data/selfplay_rs_local"
CHAMPION = yaml.safe_load((ROOT / "src/wingspan/ai/bots.yaml").read_text())["bots"]["mcts-v1"]["params"]
BUDGETS = (1_500, 3_000, 10_000, 30_000)


def search_game(task):
    import wingspan_rs
    from pystate import to_json

    from wingspan.engine.actions import get_actions
    from wingspan.engine.core import ScoringMode, initiate_state
    from wingspan.engine.engine import transition_state

    game_seed, scoring, rows, picks = task
    state = initiate_state(2, ScoringMode(scoring), seed=game_seed)
    out = []
    for i, row in enumerate(rows):
        while len(actions := get_actions(state)) == 1:  # forced steps are not recorded
            state = transition_state(state, actions[0])
        if i in picks:
            js, legal = json.dumps(to_json(state)), [str(a) for a in actions]
            for n in BUDGETS:
                strs, visits, values, _ = wingspan_rs.ismcts(
                    js, n, CHAMPION["exploration_constant"], CHAMPION["value_function"],
                    CHAMPION["widening_k"], CHAMPION["widening_alpha"], game_seed * 1000 + i,
                )
                stats = {s: (v, q) for s, v, q in zip(strs, visits, values) if s in legal}
                out.append({"phase": row["game_phase"], "sims": n, "n_legal": len(legal),
                            "visits": [stats.get(a, (0, math.nan))[0] for a in legal],
                            "q": [stats.get(a, (0, math.nan))[1] for a in legal]})
        state = transition_state(state, {str(a): a for a in actions}[row["action_taken"]])
    return out


def metrics(r):
    v = [x for x in r["visits"]]
    total = sum(v)
    p = [x / total for x in v if x > 0]
    eff = math.exp(-sum(x * math.log(x) for x in p))
    q = sorted((x for x in r["q"] if not math.isnan(x)), reverse=True)
    gap = 100 * (q[0] - q[1]) if len(q) > 1 else math.nan  # absolute_score: value = points / 100
    best_q = max(range(len(v)), key=lambda i: -math.inf if math.isnan(r["q"][i]) else r["q"][i])
    return {"eff_frac": eff / r["n_legal"], "eff": eff, "top_share": max(v) / total, "gap": gap,
            "agree": float(max(range(len(v)), key=v.__getitem__) == best_q), "n_legal": r["n_legal"]}


if __name__ == "__main__":
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    per_game = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    rng = random.Random(0)
    games = {}
    for f in sorted(glob.glob(str(DATA / "*/games_*.parquet"))):
        for r in pq.read_table(f, columns=["game_id", "game_seed", "scoring"]).to_pylist():
            games[r["game_id"]] = r
    decisions = defaultdict(list)
    for f in sorted(glob.glob(str(DATA / "*/decisions_*.parquet")))[:20]:
        cols = ["game_id", "decision_idx", "game_phase", "action_taken"]
        for r in pq.read_table(f, columns=cols).to_pylist():
            decisions[r["game_id"]].append(r)
    chosen = rng.sample(sorted(decisions), n_games)
    tasks = []
    for gid in chosen:
        rows = sorted(decisions[gid], key=lambda r: r["decision_idx"])
        tasks.append((games[gid]["game_seed"], games[gid]["scoring"], rows, set(rng.sample(range(len(rows)), per_game))))
    with Pool(7) as pool:
        results = [m for game in pool.map(search_game, tasks, chunksize=1) for m in game]

    by = defaultdict(list)
    for r in results:
        by[(r["phase"], r["sims"])].append(metrics(r))
        by[("ALL", r["sims"])].append(metrics(r))
    phases = ["ALL"] + sorted({p for p, _ in by if p != "ALL"}, key=lambda p: -len(by[(p, BUDGETS[0])]))
    print(f"{len(results) // len(BUDGETS)} positions from {n_games} games; champion tree, budgets {BUDGETS}\n")
    print(f"{'phase':<24}{'n':>4}{'moves':>6} | {'eff. moves / legal (1 = uniform)':^34} | {'top visit share':^31} | "
          f"{'Q gap best-2nd (pts)':^31} | {'most visited = best Q':^31}")
    print(" " * 34 + "|" + "".join(f"{n // 1000 if n >= 1000 else n:>7}k" if n % 1000 == 0 else f"{n / 1000:>7.1f}k" for n in BUDGETS) * 4)
    for ph in phases:
        rows = {n: by[(ph, n)] for n in BUDGETS}
        if not rows[BUDGETS[0]]:
            continue
        med = lambda n, k: statistics.median(x[k] for x in rows[n] if not math.isnan(x[k]))  # noqa: E731
        mean = lambda n, k: statistics.fmean(x[k] for x in rows[n])  # noqa: E731
        line = f"{ph:<24}{len(rows[BUDGETS[0]]):>4}{mean(BUDGETS[0], 'n_legal'):>6.1f} |"
        line += "".join(f"{mean(n, 'eff_frac'):>8.2f}" for n in BUDGETS) + "  |"
        line += "".join(f"{mean(n, 'top_share'):>8.2f}" for n in BUDGETS) + "  |"
        line += "".join(f"{med(n, 'gap'):>8.2f}" for n in BUDGETS) + "  |"
        line += "".join(f"{mean(n, 'agree'):>8.0%}" for n in BUDGETS)
        print(line)
    print("\nQ gap: median over positions. The others: means.")
