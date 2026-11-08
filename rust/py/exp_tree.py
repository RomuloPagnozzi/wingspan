"""With fast search, re-check old assumptions: does a real tree (IS-MCTS) or more simulations beat the
current data generator (flat_mc_rs with the phase-budget table)?

Every arm plays that reference on the same fresh deals, each deal twice with seats swapped. Arms are
interleaved deal by deal. Results are appended to a JSONL file as games finish, and a restart continues
after the last deal in the file, so a run can be stopped (Ctrl+C) and resumed at will.

    # run (no --minutes: until Ctrl+C)
    PYTHONPATH=.:rust/py caffeinate -is uv run python rust/py/exp_tree.py run scaling [--minutes 19]
    # results so far (also while it runs)
    PYTHONPATH=.:rust/py uv run python rust/py/exp_tree.py report scaling

Sets: `tree` (EXP-013: tree and flat variants, 2026-11-08), `scaling` (the tree at 3k..100k simulations,
and at 10k with the flat-MC phase table scaled to the tree: is the table useful at big budgets?).
"""

import argparse
import collections
import json
import signal
import statistics
import time
from multiprocessing import Pool, TimeoutError
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
REF = {k: v for k, v in yaml.safe_load((ROOT / "experiments/selfplay_flat_mc.yaml").read_text())["defaults"].items() if k != "strategy"}
CHAMPION = yaml.safe_load((ROOT / "src/wingspan/ai/bots.yaml").read_text())["bots"]["mcts-v1"]["params"]
# The flat-MC phase table (EXP-012) as ratios of its default budget, to scale for the tree
TABLE_RATIO = {k: v / REF["playouts"] for k, v in REF["phase_playouts"].items()}


def tree_table(n: int) -> tuple[str, dict]:
    """The champion tree with `n` simulations by default and the phase table scaled to it."""
    return ("mcts_rs", {**CHAMPION, "simulations": n, "phase_simulations": {k: round(r * n) for k, r in TABLE_RATIO.items()}})


X10 = {**REF, "playouts": REF["playouts"] * 10, "phase_playouts": {k: v * 10 for k, v in REF["phase_playouts"].items()}}

SETS = {
    "tree": {
        "first_deal": 20_001,
        "arms": {
            "tree_1500": ("mcts_rs", {**CHAMPION, "simulations": 1500}),
            "tree_10k": ("mcts_rs", {**CHAMPION, "simulations": 10_000}),
            "tree_10k_c0.7": ("mcts_rs", {**CHAMPION, "simulations": 10_000, "exploration_constant": 0.7}),
            "flat_1500": ("flat_mc_rs", {"playouts": 1500, "paired": True, "value_function": "absolute_score"}),
            "flat_x10": ("flat_mc_rs", X10),
        },
    },
    "scaling": {
        "first_deal": 30_001,
        "arms": {
            **{f"tree_{n // 1000}k": ("mcts_rs", {**CHAMPION, "simulations": n}) for n in (3_000, 10_000, 30_000, 100_000)},
            "tree_table_10k": tree_table(10_000),
        },
    },
}


def play(task):
    import flat_mc_rs  # noqa: F401
    import mcts_rs  # noqa: F401
    from lab.simulation import simulate_game
    from wingspan.ai.base import create_strategy

    set_name, arm, deal, arm_first = task
    strategy, params = SETS[set_name]["arms"][arm]
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


def summary(rows, arms):
    """Per arm: win rate and score difference over all games, and the score difference averaged per deal
    over deals with both seats played (removes the luck of the deal)."""
    print(f"{'arm':<15}{'games':>6}{'win rate':>14}{'score diff':>14}{'deals':>7}{'per-deal diff':>16}{'s/game':>8}")
    for arm in arms:
        r = [x for x in rows if x["arm"] == arm]
        if not r:
            continue
        w = statistics.fmean(x["win"] for x in r)
        d = [x["arm_score"] - x["ref_score"] for x in r]
        se = lambda v: statistics.stdev(v) / len(v) ** 0.5 if len(v) > 1 else 0.0  # noqa: E731
        by_deal = collections.defaultdict(list)
        for x in r:
            by_deal[x["deal"]].append(x["arm_score"] - x["ref_score"])
        paired = [statistics.fmean(v) for v in by_deal.values() if len(v) == 2]
        pd = f"{statistics.fmean(paired):+.1f} ± {1.96 * se(paired):.1f}" if paired else "-"
        print(f"{arm:<15}{len(r):>6}{w:>8.1%} ±{1.96 * (w * (1 - w) / len(r)) ** 0.5:>4.0%}"
              f"{statistics.fmean(d):>+8.1f} ±{1.96 * se(d):>4.1f}{len(paired):>7}{pd:>16}"
              f"{statistics.fmean(x['seconds'] for x in r):>8.0f}", flush=True)


def read(out: Path) -> list[dict]:
    return [json.loads(line) for line in out.open()] if out.exists() else []


def run(set_name: str, out: Path, minutes: float | None, workers: int) -> None:
    cfg = SETS[set_name]
    arms = cfg["arms"]
    old = read(out)
    first = max([x["deal"] for x in old], default=cfg["first_deal"] - 1) + 1
    print(f"{set_name}: {len(old)} games already in {out}; starting at deal {first}", flush=True)
    tasks = ((set_name, arm, deal, f) for deal in range(first, first + 1_000_000) for arm in arms for f in (True, False))
    deadline = time.time() + 60 * minutes if minutes else None
    rows = []
    # Workers ignore Ctrl+C; the parent stops them, so an interrupt leaves no tracebacks behind
    pool = Pool(workers, initializer=signal.signal, initargs=(signal.SIGINT, signal.SIG_IGN))
    results = pool.imap_unordered(play, tasks)
    try:
        with out.open("a") as f:
            while not (deadline and time.time() > deadline):
                try:
                    # A timeout, so Ctrl+C and the deadline are noticed while games are running
                    row = results.next(timeout=1)
                except TimeoutError:
                    continue
                rows.append(row)
                f.write(json.dumps(row) + "\n")
                f.flush()
                if len(rows) % 20 == 0:
                    left = f", {(deadline - time.time()) / 60:.0f} min left" if deadline else ""
                    print(f"--- {len(rows)} games this session{left}", flush=True)
                    summary(old + rows, arms)
    except KeyboardInterrupt:
        print("\nstopped (games in progress are dropped)")
    finally:
        pool.terminate()
    print(f"=== {len(old) + len(rows)} games in total")
    summary(old + rows, arms)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "report"])
    ap.add_argument("set", choices=list(SETS))
    ap.add_argument("--minutes", type=float, default=None, help="stop after this long (default: until Ctrl+C)")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--out", type=Path, default=None, help="default: experiments/data/exp_<set>/results.jsonl")
    a = ap.parse_args()
    out = a.out or ROOT / f"experiments/data/exp_{a.set}/results.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.mode == "run":
        run(a.set, out, a.minutes, a.workers)
    else:
        rows = read(out)
        print(f"{len(rows)} games in {out}")
        summary(rows, SETS[a.set]["arms"])
