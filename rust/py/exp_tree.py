"""With fast search, re-check old assumptions: does a real tree (IS-MCTS) or many more simulations beat
the current data generator (flat_mc_rs with the phase-budget table)?

Every arm plays the reference on the same fresh deals, each deal twice with seats swapped; arms are
interleaved deal by deal and the run stops at a deadline. Results go to a JSONL file as games finish.

    PYTHONPATH=.:rust/py caffeinate -is uv run python rust/py/exp_tree.py [minutes] [out.jsonl]
"""

import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
REF = {k: v for k, v in yaml.safe_load((ROOT / "experiments/selfplay_flat_mc.yaml").read_text())["defaults"].items() if k != "strategy"}
CHAMPION = yaml.safe_load((ROOT / "src/wingspan/ai/bots.yaml").read_text())["bots"]["mcts-v1"]["params"]
X10 = {**REF, "playouts": REF["playouts"] * 10, "phase_playouts": {k: v * 10 for k, v in REF["phase_playouts"].items()}}

ARMS = {
    "tree_1500": ("mcts_rs", {**CHAMPION, "simulations": 1500}),
    "tree_10k": ("mcts_rs", {**CHAMPION, "simulations": 10_000}),
    "tree_10k_c0.7": ("mcts_rs", {**CHAMPION, "simulations": 10_000, "exploration_constant": 0.7}),
    "flat_1500": ("flat_mc_rs", {"playouts": 1500, "paired": True, "value_function": "absolute_score"}),
    "flat_x10": ("flat_mc_rs", X10),
}
FIRST_DEAL = 20_001


def play(task):
    import flat_mc_rs  # noqa: F401
    import mcts_rs  # noqa: F401
    from lab.simulation import simulate_game
    from wingspan.ai.base import create_strategy

    arm, deal, arm_first = task
    strategy, params = ARMS[arm]
    seats = [create_strategy(strategy, seed=deal * 10 + 1, **params), create_strategy("flat_mc_rs", seed=deal * 10 + 2, **REF)]
    labels = [arm, "reference"]
    if not arm_first:
        seats, labels = seats[::-1], labels[::-1]
    t = time.perf_counter()
    result, _ = simulate_game(seats, game_seed=deal, arm_labels=labels)
    scores = {p.arm_label: p.total_score for p in result.players}
    winner = next((p.arm_label for p in result.players if p.is_winner), None)
    return {"arm": arm, "deal": deal, "arm_first": arm_first, "arm_score": scores[arm], "ref_score": scores["reference"],
            "win": 1.0 if winner == arm else 0.0 if winner == "reference" else 0.5, "seconds": time.perf_counter() - t}


def summary(rows):
    print(f"{'arm':<15}{'games':>6}{'win rate':>16}{'score diff':>16}{'s/game':>8}")
    for arm in ARMS:
        r = [x for x in rows if x["arm"] == arm]
        if not r:
            continue
        w = statistics.fmean(x["win"] for x in r)
        d = [x["arm_score"] - x["ref_score"] for x in r]
        se_w = (w * (1 - w) / len(r)) ** 0.5
        se_d = statistics.stdev(d) / len(r) ** 0.5 if len(r) > 1 else 0.0
        print(f"{arm:<15}{len(r):>6}{w:>9.1%} ±{1.96 * se_w:>4.0%}{statistics.fmean(d):>+9.1f} ±{1.96 * se_d:>4.1f}"
              f"{statistics.fmean(x['seconds'] for x in r):>8.0f}", flush=True)


if __name__ == "__main__":
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 19
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "experiments/data/exp_tree/results.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    tasks = [(arm, deal, first) for deal in range(FIRST_DEAL, FIRST_DEAL + 1000) for arm in ARMS for first in (True, False)]
    deadline, rows = time.time() + 60 * minutes, []
    pool = Pool(7)
    with out.open("a") as f:
        for row in pool.imap_unordered(play, tasks):
            rows.append(row)
            f.write(json.dumps(row) + "\n")
            f.flush()
            if len(rows) % 25 == 0:
                print(f"--- {len(rows)} games, {(deadline - time.time()) / 60:.1f} min left", flush=True)
                summary(rows)
            if time.time() > deadline:
                break
    pool.terminate()  # games still running are dropped
    print(f"=== final: {len(rows)} games")
    summary(rows)
