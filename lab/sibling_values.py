"""Does a leaf evaluation rank sibling moves as the search does? What a value net must get right to help the
search: the search never reads a value alone, it compares the values below each legal move. An error every
sibling shares costs nothing; winner accuracy mostly measures that shared level (who is ahead), not how one
move changes it.

At every full-budget decision of n games: each legal move the search visited enough is applied to the
recorded position (forced single-legal steps follow, as at a search leaf), and the resulting position is
scored by each evaluator, from the deciding player's seat, the way the search scores a leaf (from the seat
of the player to move, negated for the other):
  - each value net's margin head (what mcts_rs uses at its leaves) and value head;
  - the score gap after the move (points on the board now: no future at all);
  - the mean of n random playouts (what the search uses today), each from a re-deal of the hidden cards.
The reference is the search's own Q of each move (10k simulations: the best judgment we have; it is built
from playouts deeper in the tree, so playouts start with an advantage).

Readouts per phase: pairwise accuracy (over pairs of moves whose Q differ by at least --gap points, how often
the evaluator orders them the same way; a tie in the evaluator counts half) and top-move agreement (decisions
whose best move leads the second by at least --gap). Use games no net trained on, e.g. the newest generation.

    uv run --group train python -m lab.sibling_values experiments/data/selfplay_g2 --games 200
    uv run --group train python -m lab.sibling_values experiments/data/selfplay_g2 --value experiments/data/models/value.pt experiments/data/models/value_candidate.pt
"""

import argparse
import glob
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

FULL_BUDGET = 10_000


def run(task):
    import wingspan_rs

    from wingspan.ai.rust import state_json
    from wingspan.engine.actions import get_actions
    from wingspan.engine.core import ScoringMode, init_registries, initiate_state
    from wingspan.engine.engine import transition_state

    init_registries()
    seed, scoring, rows, min_visits, playouts = task
    s = initiate_state(2, ScoringMode(scoring), seed=seed)
    out = []
    for k, row in enumerate(rows):
        while len(actions := get_actions(s)) == 1:
            s = transition_state(s, actions[0])
        names = [str(a) for a in actions]
        visits = dict(row["visit_counts"])
        if sum(visits.values()) >= FULL_BUDGET:
            q = dict(row["mcts_action_values"])
            me = s.current_player_index
            moves = []
            for a, name in zip(actions, names):
                if visits.get(name, 0) < min_visits or q.get(name) is None:
                    continue
                leaf = transition_state(s, a)
                while len(nxt := get_actions(leaf)) == 1:
                    leaf = transition_state(leaf, nxt[0])
                js = state_json(leaf)
                sign = 1.0 if leaf.current_player_index == me else -1.0
                rollouts = wingspan_rs.rollouts(js, max(playouts, 1) if nxt else 1, seed * 1000 + k)
                moves.append({
                    "q": 50 * q[name], "sign": sign, "terminal": not nxt, "playouts": sign * float(np.mean(rollouts)),
                    "obs": np.asarray(wingspan_rs.encode_obs(js, leaf.current_player_index), np.float16),
                })  # fmt: skip
            if len(moves) > 1:
                out.append({"phase": row["game_phase"], "moves": moves})
        s = transition_state(s, actions[names.index(row["action_taken"])])
    return out


def net_estimates(paths: list[Path], obs: np.ndarray) -> dict[str, np.ndarray]:
    """Each value net on the leaf observations: its margin in points and its value, from the leaf mover's seat."""
    import torch

    from lab.train_value import MARGIN_SCALE
    from wingspan.ai.nets import ValueNet

    out = {}
    for p in paths:
        ckpt = torch.load(p, weights_only=False)
        net = ValueNet(ckpt["n_obs"], dropout=ckpt["dropout"])
        net.load_state_dict(ckpt["state"])
        net.eval()
        vs, ms = [], []
        with torch.no_grad():
            for b in range(0, len(obs), 8192):
                v, m = net(torch.from_numpy(obs[b : b + 8192].astype(np.float32)))
                vs.append(v.numpy())
                ms.append(m.numpy() * MARGIN_SCALE)
        out[f"{p.stem} margin"], out[f"{p.stem} value"] = np.concatenate(ms), np.concatenate(vs)
    return out


def readouts(est: np.ndarray, q: np.ndarray, gap: float) -> tuple[float, float, int, int]:
    """Pairwise accuracy and top-move agreement of one decision's estimates against Q, with their counts."""
    i, j = np.triu_indices(len(q), 1)
    clear = np.abs(q[i] - q[j]) >= gap
    d_est, d_q = est[i][clear] - est[j][clear], q[i][clear] - q[j][clear]
    pairs = np.where(d_est == 0, 0.5, np.sign(d_est) == np.sign(d_q)).sum()
    top_q = np.sort(q)[::-1]
    has_top = top_q[0] - top_q[1] >= gap
    best = est.max()
    top = float(est[q.argmax()] == best) / float((est == best).sum()) if has_top else 0.0
    return pairs, top, int(clear.sum()), int(has_top)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", help="a self-play output folder (its run folders): games no value net trained on")
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--value", type=Path, nargs="+", default=[Path("experiments/data/models/value.pt")],
                   help="value nets to compare (.pt checkpoints)")  # fmt: skip
    p.add_argument("--playouts", type=int, default=16, help="random playouts per move for the playout evaluator")
    p.add_argument("--min-visits", type=int, default=50, help="moves the search visited less are left out: their Q is noise")
    p.add_argument("--gap", type=float, default=0.5, help="pairs whose Q differ by less (points) are left out")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()

    files = sorted(glob.glob(f"{args.folder}/*/decisions_*.parquet"))
    cols = ["game_id", "decision_idx", "game_seed", "game_phase", "action_taken", "visit_counts", "mcts_action_values"]
    d = pd.concat(pd.read_parquet(f, columns=cols) for f in files)
    g = pd.concat(pd.read_parquet(f, columns=["game_id", "scoring"]) for f in glob.glob(f"{args.folder}/*/games_*.parquet"))
    scoring = g.drop_duplicates("game_id").set_index("game_id").scoring
    ids = pd.Series(sorted(set(d.game_id) & set(scoring.index)))
    ids = ids.sample(min(args.games, len(ids)), random_state=0)
    d = d[d.game_id.isin(ids)]
    tasks = [(int(x.game_seed.iloc[0]), scoring[gid], x.sort_values("decision_idx").to_dict("records"), args.min_visits, args.playouts)
             for gid, x in d.groupby("game_id")]  # fmt: skip
    with Pool(args.workers) as pool:
        decisions = [x for part in pool.imap_unordered(run, tasks) for x in part]

    moves = [m for dec in decisions for m in dec["moves"]]
    sign = np.array([m["sign"] for m in moves])
    terminal = np.array([m["terminal"] for m in moves])
    final = np.array([m["playouts"] for m in moves])  # at a finished game: the exact final margin
    from lab.train_value import score_gap
    from wingspan.ai.encoding import player_feature_names

    obs = np.stack([m["obs"] for m in moves])
    names = player_feature_names()
    est = {k: sign * v for k, v in net_estimates(args.value, obs).items()}
    est["score gap"] = sign * score_gap(obs, len(names), names.index("score_now"))
    est[f"{args.playouts} playouts"] = final
    for v in est.values():
        v[terminal] = final[terminal]  # every evaluator knows a finished game's result

    rows, start = [], 0
    for dec in decisions:
        n = len(dec["moves"])
        q = np.array([m["q"] for m in dec["moves"]])
        r = {"phase": dec["phase"], "moves": n}
        for k, v in est.items():
            r[k, "pairs"], r[k, "top"], r["n_pairs"], r["n_top"] = readouts(v[start : start + n], q, args.gap)
        rows.append(r)
        start += n
    t = pd.DataFrame(rows)

    def table(group: pd.DataFrame) -> pd.Series:
        out = {"decisions": len(group), "pairs": group.n_pairs.sum(), "moves": group.moves.mean()}
        for k in est:
            out[f"{k}"] = group[(k, "pairs")].sum() / max(group.n_pairs.sum(), 1)
        for k in est:
            out[f"{k} (top)"] = group[(k, "top")].sum() / max(group.n_top.sum(), 1)
        return pd.Series(out)

    tab = t.groupby("phase").apply(table)
    tab.loc["all"] = table(t)
    tab = tab[tab.pairs > 0].sort_values("pairs", ascending=False)
    print(f"{len(ids)} games from {args.folder}: {len(decisions):,} full-budget decisions, {len(moves):,} moves; "
          f"pairs: Q differs by ≥ {args.gap} points; top: the best move leads by ≥ {args.gap}")  # fmt: skip
    pd.set_option("display.width", 250)
    counts = {"decisions": "{:,.0f}".format, "pairs": "{:,.0f}".format, "moves": "{:.1f}".format}
    share = "{:.0%}".format
    print("\npairwise accuracy (same order as the search's Q)")
    print(tab[list(counts) + list(est)].to_string(formatters=counts | {k: share for k in est}))
    print("\ntop-move agreement")
    top = [f"{k} (top)" for k in est]
    print(tab[["decisions"] + top].to_string(formatters={"decisions": counts["decisions"]} | {k: share for k in top}))


if __name__ == "__main__":
    main()
