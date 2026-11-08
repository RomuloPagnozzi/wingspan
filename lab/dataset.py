"""Replay dataset: decisions.parquet -> the arrays the networks train on.

decisions.parquet keeps only action strings, so each game is replayed from its seed: forced
single-legal steps are applied, and every recorded decision is encoded from the deciding player's
seat. A replay that disagrees with the recording (different legal moves, a different player to
move) stops the build. Everything is stored raw: visit counts, Q values, the move taken, final
scores. Targets and weights (softmax(Q/τ), per-phase reliability) are chosen at training time.

    uv run python -m lab.dataset experiments/data/selfplay/* --out experiments/data/datasets/selfplay

N decisions, M legal moves in total. Ragged arrays are sliced by their offsets:
row i's moves are act[act_off[i]:act_off[i + 1]].

    obs        [N, 1935] float16   Observation.flat(): me | opponents | shared
    hand, tray            int16    the viewer's hand and the tray as bird ids (hand_off, tray_off)
    act        [M, 146]  float16   encode_action, in get_actions order (act_off)
    act_birds             int16    action_bird_ids of each move (act_birds_off, length M + 1)
    visits     [M] int32           MCTS visit count (0: not visited)
    q          [M] float32         MCTS mean value of the move (NaN: none)
    taken      [N] int16           index of the move played, within the decision's moves
    game [N] int32, phase [N] int8 (index into PHASES), round [N] int8, player [N] int8
    outcome [N] float32 (+1 won, 0 tie, -1 lost), score [N] int16, opp_score [N] int16

meta.json holds the feature names, the phases, each game's id and seed, and the data's source.
"""

import argparse
import json
import math
from contextlib import nullcontext
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.format import open_memmap

from wingspan.ai.encoding import (
    PHASES,
    action_bird_ids,
    action_feature_names,
    encode_action,
    encode_obs,
    player_feature_names,
    shared_feature_names,
)
from wingspan.engine.actions import get_actions
from wingspan.engine.core import ScoringMode, init_registries, initiate_state
from wingspan.engine.engine import transition_state

DECISION_COLUMNS = ["game_id", "decision_idx", "game_seed", "player_position", "round",
                    "action_taken", "legal_actions", "visit_counts", "mcts_action_values", "outcome"]  # fmt: skip


def encode_game(task: tuple[int, int, list[dict], str]) -> dict[str, list]:
    """Replay one game, in the scoring mode it was played in, and encode its recorded decisions."""
    game_seed, n_players, rows, scoring = task
    state = initiate_state(n_players, ScoringMode(scoring), seed=game_seed)
    out: dict[str, list] = {k: [] for k in (
        "obs", "hand", "tray", "act", "act_birds", "visits", "q", "n_act", "taken", "phase", "round", "player", "outcome",
    )}  # fmt: skip
    for row in rows:
        while len(actions := get_actions(state)) == 1:  # forced steps are not recorded
            state = transition_state(state, actions[0])
        by_str = {str(a): a for a in actions}
        if sorted(by_str) != sorted(row["legal_actions"]):
            raise ValueError(f"seed {game_seed}: replay diverged at decision {row['decision_idx']}")
        me = state.current_player_index
        if me != row["player_position"] - 1:
            raise ValueError(f"seed {game_seed}: wrong player at decision {row['decision_idx']}")

        obs = encode_obs(state, me)
        visits = dict(row["visit_counts"] or ())
        values = dict(row["mcts_action_values"] or ())
        out["obs"].append(obs.flat())
        out["hand"].append(obs.hand)
        out["tray"].append(obs.tray)
        for action in actions:
            out["act"].append(encode_action(state, action))
            out["act_birds"].append(action_bird_ids(action))
            out["visits"].append(visits.get(str(action), 0))
            out["q"].append(values.get(str(action), math.nan))
        out["n_act"].append(len(actions))
        out["taken"].append([str(a) for a in actions].index(row["action_taken"]))
        out["phase"].append(PHASES.index(state.game_phase.value))
        out["round"].append(row["round"])
        out["player"].append(me)
        out["outcome"].append(row["outcome"])
        state = transition_state(state, by_str[row["action_taken"]])
    return out


def _ragged(lists: list[list[int]]) -> tuple[np.ndarray, np.ndarray]:
    """Flat values and offsets for a list of variable-length lists."""
    off = np.zeros(len(lists) + 1, dtype=np.int64)
    off[1:] = np.cumsum([len(x) for x in lists])
    return np.fromiter((v for x in lists for v in x), dtype=np.int16, count=int(off[-1])), off


def build(srcs: list[Path], out: Path, workers: int = 7, max_games: int | None = None) -> None:
    """`srcs`: run folders (e.g. the chunks of one cloud run), combined into one dataset."""
    # games.parquet, or the games_NNNN.parquet parts of a rotating run (never the open .tmp)
    d = pd.concat(pd.read_parquet(f, columns=DECISION_COLUMNS) for s in srcs for f in sorted(s.glob("decisions*.parquet")))
    g = pd.concat(
        pd.read_parquet(f).reindex(columns=["game_id", "player_position", "player_count", "total_score", "scoring"])
        for s in srcs
        for f in sorted(s.glob("games*.parquet"))
    )
    d = d[d.game_id.isin(g.game_id)]  # a rotating run can hold a game's decisions before its result
    game_ids = sorted(d.game_id.unique())[:max_games]
    d = d[d.game_id.isin(game_ids)].sort_values(["game_id", "decision_idx"])
    if g[g.game_id.isin(game_ids)].player_count.nunique() != 1:
        raise ValueError("games with different player counts have different observation sizes")
    n_players = int(g.player_count.iloc[0])
    score = {(r.game_id, r.player_position - 1): r.total_score for r in g.itertuples()}

    n, m = len(d), int(d.legal_actions.map(len).sum())
    n_obs = n_players * len(player_feature_names()) + len(shared_feature_names())
    out.mkdir(parents=True, exist_ok=True)
    obs = open_memmap(out / "obs.npy", "w+", np.float16, (n, n_obs))
    act = open_memmap(out / "act.npy", "w+", np.float16, (m, len(action_feature_names())))

    seeds = d.groupby("game_id").game_seed.first()
    scoring = g.groupby("game_id").scoring.first()
    # One game at a time. A pool queues every task up front, so with one worker it is skipped
    # and only one game's rows are ever held as Python objects.
    tasks = ((int(seeds[gid]), n_players, x.to_dict("records"), scoring[gid]) for gid, x in d.groupby("game_id", sort=True))
    pool = Pool(workers, initializer=init_registries) if workers > 1 else None
    if pool is None:
        init_registries()
    small: dict[str, list] = {}
    i = j = 0
    with pool or nullcontext():
        for k, res in enumerate(pool.imap(encode_game, tasks, chunksize=2) if pool else map(encode_game, tasks)):
            obs[i : i + len(res["obs"])] = res["obs"]
            act[j : j + len(res["act"])] = res["act"]
            i, j = i + len(res["obs"]), j + len(res["act"])
            for key, v in res.items():
                if key not in ("obs", "act"):
                    small.setdefault(key, []).extend(v)
            small.setdefault("game", []).extend([k] * len(res["obs"]))
            gid = game_ids[k]
            small.setdefault("score", []).extend(score[gid, p] for p in res["player"])
            small.setdefault("opp_score", []).extend(
                max(score[gid, o] for o in range(n_players) if o != p) for p in res["player"]
            )
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{len(game_ids)} games", flush=True)
    assert (i, j) == (n, m), "every recorded decision and move is written"
    obs.flush()
    act.flush()

    arrays = {
        "visits": np.array(small["visits"], np.int32), "q": np.array(small["q"], np.float32),
        "taken": np.array(small["taken"], np.int16), "game": np.array(small["game"], np.int32),
        "phase": np.array(small["phase"], np.int8), "round": np.array(small["round"], np.int8),
        "player": np.array(small["player"], np.int8), "outcome": np.array(small["outcome"], np.float32),
        "score": np.array(small["score"], np.int16), "opp_score": np.array(small["opp_score"], np.int16),
        "act_off": np.concatenate([[0], np.cumsum(small["n_act"])]).astype(np.int64),
    }  # fmt: skip
    for name in ("hand", "tray", "act_birds"):
        arrays[name], arrays[f"{name}_off"] = _ragged(small[name])
    for name, a in arrays.items():
        np.save(out / f"{name}.npy", a)
    meta = dict(
        sources=[str(s) for s in srcs], games=game_ids, seeds=[int(seeds[gid]) for gid in game_ids], n_players=n_players, n_decisions=n, n_moves=m, phases=list(PHASES),
        player_features=list(player_feature_names()), shared_features=list(shared_feature_names()),
        action_features=list(action_feature_names()),
    )  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta))
    print(f"{n:,} decisions, {m:,} moves from {len(game_ids):,} games -> {out}")


def load(path: Path) -> tuple[dict[str, np.ndarray], dict]:
    """The arrays (memory-mapped: read from disk as used) and meta.json."""
    path = Path(path)
    arrays = {p.stem: np.load(p, mmap_mode="r") for p in path.glob("*.npy")}
    return arrays, json.loads((path / "meta.json").read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a training dataset by replaying recorded games")
    parser.add_argument("srcs", type=Path, nargs="+", help="run folders with games.parquet and decisions.parquet")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--max-games", type=int, default=None)
    args = parser.parse_args()
    build(args.srcs, args.out, args.workers, args.max_games)
