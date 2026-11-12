"""Replay dataset: decisions.parquet -> the arrays the networks train on.

decisions.parquet keeps only action strings, so each game is replayed from its seed (in Rust, with the
encodings of wingspan.ai.encoding ported value for value: rust/py/encoding_parity.py): forced
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

meta.json holds the feature names, the phases, each game's id, seed and folder (the output folder of the
run that played it, e.g. selfplay_g1: training reports validation per folder), and the data's source.
"""

import argparse
import json
from contextlib import nullcontext
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
from numpy.lib.format import open_memmap

import wingspan_rs
from wingspan.ai.encoding import PHASES, action_feature_names, player_feature_names, shared_feature_names
from wingspan.ai.rust import state_json
from wingspan.engine.core import ScoringMode, init_registries, initiate_state

DECISION_COLUMNS = ["game_id", "decision_idx", "game_seed", "player_position", "round",
                    "action_taken", "legal_actions", "visit_counts", "mcts_action_values", "outcome"]  # fmt: skip


def encode_game(task: tuple[int, int, list[dict], str]) -> dict:
    """Replay one game, in the scoring mode it was played in, and encode its recorded decisions. The deal
    is made here; the replay runs in Rust (rust/src/replay.rs), drawing dice and shuffles from the game's
    own random generator, so it reaches exactly the states the game was played in."""
    game_seed, n_players, rows, scoring = task
    state = initiate_state(n_players, ScoringMode(scoring), seed=game_seed)
    recorded = [
        (r["decision_idx"], list(r["legal_actions"]), r["action_taken"], r["player_position"] - 1,
         list(dict(r["visit_counts"] or ()).items()), list(dict(r["mcts_action_values"] or ()).items()))
        for r in rows
    ]  # fmt: skip
    try:
        out = wingspan_rs.replay_game(state_json(state), list(state.rng.getstate()[1]), recorded)
    except ValueError as e:
        raise ValueError(f"seed {game_seed}: {e}") from None
    out["obs"] = np.frombuffer(out["obs"], np.float32).reshape(len(rows), -1)
    out["act"] = np.frombuffer(out["act"], np.float32).reshape(-1, len(action_feature_names()))
    out["round"] = [r["round"] for r in rows]
    out["player"] = [r["player_position"] - 1 for r in rows]
    out["outcome"] = [r["outcome"] for r in rows]
    return out


def _ragged(lists: list[list[int]]) -> tuple[np.ndarray, np.ndarray]:
    """Flat values and offsets for a list of variable-length lists."""
    off = np.zeros(len(lists) + 1, dtype=np.int64)
    off[1:] = np.cumsum([len(x) for x in lists])
    return np.fromiter((v for x in lists for v in x), dtype=np.int16, count=int(off[-1])), off


def build(srcs: list[Path], out: Path, workers: int = 7, max_games: int | None = None) -> None:
    """`srcs`: run folders (e.g. the chunks of one cloud run), combined into one dataset."""
    # games.parquet, or the games_NNNN.parquet parts of a rotating run (never the open .tmp)
    files = [f for s in srcs for f in sorted(s.glob("decisions*.parquet"))]
    g = pd.concat(
        pd.read_parquet(f).reindex(columns=["game_id", "player_position", "player_count", "total_score", "scoring"])
        for s in srcs
        for f in sorted(s.glob("games*.parquet"))
    )
    finished = set(g.game_id)  # a rotating run can hold a game's decisions before its result

    # Files are read one at a time (each holds whole games): all decisions as Python objects don't fit
    # in memory. A first, cheap pass sizes the arrays: rows and moves per game, in the order written.
    per_file, game_ids, folders, seeds, n, m = [], [], [], {}, 0, 0
    for f in files:
        t = pq.read_table(f, columns=["game_id", "game_seed", "legal_actions"])
        seeds |= dict(zip(t["game_id"].to_pylist(), t["game_seed"].to_pylist()))
        x = pd.DataFrame({"game_id": t["game_id"].to_numpy(), "moves": pc.list_value_length(t["legal_actions"]).to_numpy()})
        ids = sorted(set(x.game_id) & finished)[: None if max_games is None else max_games - len(game_ids)]
        x = x[x.game_id.isin(ids)]
        per_file.append((f, ids))
        game_ids += ids
        folders += [f.resolve().parent.parent.name] * len(ids)
        n, m = n + len(x), m + int(x.moves.sum())
    if len(set(game_ids)) != len(game_ids):
        raise ValueError("a game's decisions are split across files")
    if g[g.game_id.isin(game_ids)].player_count.nunique() != 1:
        raise ValueError("games with different player counts have different observation sizes")
    n_players = int(g.player_count.iloc[0])
    score = {(r.game_id, r.player_position - 1): r.total_score for r in g.itertuples()}
    scoring = g.groupby("game_id").scoring.first()
    n_obs = n_players * len(player_feature_names()) + len(shared_feature_names())
    out.mkdir(parents=True, exist_ok=True)
    obs = open_memmap(out / "obs.npy", "w+", np.float16, (n, n_obs))
    act = open_memmap(out / "act.npy", "w+", np.float16, (m, len(action_feature_names())))

    def tasks():  # one file's games: a pool queues every task it is given up front
        for f, ids in per_file:
            d = pd.read_parquet(f, columns=DECISION_COLUMNS)
            d = d[d.game_id.isin(ids)].sort_values(["game_id", "decision_idx"])
            yield [(int(x.game_seed.iloc[0]), n_players, x.to_dict("records"), scoring[gid]) for gid, x in d.groupby("game_id")]

    pool = Pool(workers, initializer=init_registries) if workers > 1 else None
    if pool is None:
        init_registries()
    small: dict[str, list] = {}
    i = j = 0
    results = (res for batch in tasks() for res in (pool.imap(encode_game, batch) if pool else map(encode_game, batch)))
    with pool or nullcontext():
        for k, res in enumerate(results):
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
        sources=[str(s) for s in srcs], games=game_ids, seeds=[int(seeds[gid]) for gid in game_ids], folders=folders, n_players=n_players, n_decisions=n, n_moves=m, phases=list(PHASES),
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
