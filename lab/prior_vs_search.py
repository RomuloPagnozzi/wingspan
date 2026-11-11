"""Self-play with PUCT: does the search just confirm the policy's top move? Per phase, at every full-budget
decision of n games from a self-play folder: how often the search's most visited move is the policy's top
move, the policy's probability on that move, and the search's share of visits on it. A search that keeps
agreeing (90%+) while the policy grows confident would make the loop reinforce itself: raise root_noise or c.

    uv run python -m lab.prior_vs_search experiments/data/selfplay_g1 --games 300
"""

import argparse

import glob
from multiprocessing import Pool

import pandas as pd

def run(task):
    import wingspan_rs

    from wingspan.ai.rust import state_json
    from wingspan.engine.actions import get_actions
    from wingspan.engine.core import ScoringMode, init_registries, initiate_state
    from wingspan.engine.engine import transition_state

    init_registries()
    seed, scoring, rows, policy = task
    s = initiate_state(2, ScoringMode(scoring), seed=seed)
    out = []
    for row in rows:
        while len(actions := get_actions(s)) == 1:
            s = transition_state(s, actions[0])
        names = [str(a) for a in actions]
        visits = dict(row["visit_counts"])
        if sum(visits.values()) >= 10_000:
            prior = wingspan_rs.policy_net(policy, state_json(s))
            p_top = names[max(range(len(names)), key=prior.__getitem__)]
            s_top = max(names, key=lambda a: visits.get(a, 0))
            total = sum(visits.values())
            out.append({"phase": row["game_phase"], "n": len(names), "agree": p_top == s_top,
                        "prior_top": max(prior), "visits_on_prior_top": visits.get(p_top, 0) / total})  # fmt: skip
        s = transition_state(s, actions[names.index(row["action_taken"])])
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", help="a self-play output folder (its run folders)")
    p.add_argument("--games", type=int, default=300)
    p.add_argument("--policy", default="experiments/data/models/policy.bin", help="the policy that guided the search")
    args = p.parse_args()
    files = sorted(glob.glob(f"{args.folder}/*/decisions_*.parquet"))
    d = pd.concat(pd.read_parquet(f, columns=["game_id", "decision_idx", "game_seed", "game_phase", "action_taken", "visit_counts"]) for f in files)
    g = pd.concat(pd.read_parquet(f, columns=["game_id", "scoring"]) for f in glob.glob(f"{args.folder}/*/games_*.parquet"))
    scoring = g.drop_duplicates("game_id").set_index("game_id").scoring
    ids = pd.Series(sorted(set(d.game_id) & set(scoring.index))).sample(args.games, random_state=0)
    d = d[d.game_id.isin(ids)]
    tasks = [(int(x.game_seed.iloc[0]), scoring[gid], x.sort_values("decision_idx").to_dict("records"), args.policy) for gid, x in d.groupby("game_id")]
    with Pool(4) as pool:
        r = pd.DataFrame([x for part in pool.imap_unordered(run, tasks) for x in part])
    tab = r.groupby("phase").agg(decisions=("agree", "size"), moves=("n", "mean"), search_keeps_policy_top=("agree", "mean"),
                                 prior_on_top=("prior_top", "mean"), visits_on_prior_top=("visits_on_prior_top", "mean"))  # fmt: skip
    tab.loc["all"] = [len(r), r.n.mean(), r.agree.mean(), r.prior_top.mean(), r.visits_on_prior_top.mean()]
    print(tab.sort_values("decisions", ascending=False).round(2).to_string())
