"""Train the value net on a replay dataset (lab/dataset.py).

    uv run --group train python -m lab.train_value experiments/data/datasets/selfplay
    uv run --group train python -m lab.train_value experiments/data/datasets/selfplay --games 0.25   # learning curve

Targets, from the deciding player's seat: v -> the result (+1 won, 0 tie, -1 lost) and
margin -> (own score - opponent's score) / MARGIN_SCALE. Train and validation are split by
starting deal: positions of one game are near-copies sharing one result, and games that share a
deal share much more, so any finer split lets validation peek at training data.

Reports validation error by round next to two baselines: predicting 0, and a line fitted per round
on the current score difference (`score_now`, me minus opponent). A net that cannot beat the second
has learned nothing beyond the scoreboard.
"""

import argparse
import hashlib
import time
from pathlib import Path

import numpy as np
import torch
from numpy.lib.format import open_memmap

from lab.dataset import load
from wingspan.ai.nets import ValueNet, export_value_net

MARGIN_SCALE = 20  # final score differences have a standard deviation of about 10 points


def split_games(deals: list[int], val_share: float, fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Split by starting deal (game seed), not by game: a tuning study replays the same few deals
    in many games, and a net validated on deals it trained on can score well by recognising the
    deal. `fraction` keeps a share of the training games."""
    deals = np.asarray(deals)
    unique = np.random.default_rng(seed).permutation(np.unique(deals))
    held_out = unique[: max(1, round(len(unique) * val_share))]
    val = np.flatnonzero(np.isin(deals, held_out))
    train = np.random.default_rng(seed).permutation(np.flatnonzero(~np.isin(deals, held_out)))
    return train[: int(len(train) * fraction)], val


def per_game(rows: np.ndarray, game: np.ndarray, rounds: np.ndarray, k: int, seed: int) -> np.ndarray:
    """`k` of the rows per game, at random, spread evenly over the 4 rounds; when k isn't a multiple of 4,
    which rounds get the extra positions is drawn per game (k=1: one position from a random round)."""
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(rows)
    extra = {g: set(rng.permutation([1, 2, 3, 4])[: k % 4]) for g in np.unique(game[rows])}
    keep, taken = [], {}
    for r in shuffled:
        key = (game[r], rounds[r])
        quota = k // 4 + (rounds[r] in extra[game[r]])
        if taken.get(key, 0) < quota:
            taken[key] = taken.get(key, 0) + 1
            keep.append(r)
    return np.sort(np.array(keep))


def score_gap(obs: np.ndarray, n_player: int, i_score: int) -> np.ndarray:
    """Current public score difference, me minus the opponent, in points (score_now is score / 120), for
    every position. Reads just the two columns, so a memory-mapped `obs` is never loaded whole."""
    return 120 * (obs[:, i_score].astype(np.float32) - obs[:, n_player + i_score].astype(np.float32))


def gathered(dataset: Path, obs: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """obs[rows] (rows sorted), written once to dataset/cache/ and memory-mapped. The full array is several
    times the machine's memory: reading scattered rows from it every epoch makes training disk-bound."""
    path = dataset / "cache" / f"obs_{hashlib.sha1(rows.tobytes()).hexdigest()[:12]}.npy"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        tmp = path.with_suffix(".tmp")
        out = open_memmap(tmp, "w+", np.float16, (len(rows), obs.shape[1]))
        for b in range(0, len(rows), 65536):
            out[b : b + 65536] = obs[rows[b : b + 65536]]
        out.flush()
        tmp.rename(path)
    return np.load(path, mmap_mode="r")


def root_q(a: dict) -> np.ndarray:
    """The search's value of each position, in points (me minus the opponent): the visit-weighted mean of
    its moves' Q, which mcts_rs reports in score_delta units (points / 50)."""
    off, visits = a["act_off"][:-1], a["visits"].astype(np.float64)
    q = np.add.reduceat(visits * np.nan_to_num(a["q"].astype(np.float64)), off)
    return 50 * q / np.maximum(np.add.reduceat(visits, off), 1)


def report(name: str, pred: np.ndarray, z: np.ndarray, rounds: np.ndarray) -> str:
    def stats(m):
        decided = m & (z != 0)
        acc = f"{np.mean(np.sign(pred[decided]) == z[decided]):.0%}" if pred.any() else "–"  # no sign to read
        return f"{np.mean((pred[m] - z[m]) ** 2):.3f}/{acc}"

    by_round = "  ".join(f"r{r} {stats(rounds == r)}" for r in (1, 2, 3, 4))
    return f"{name:22} all {stats(np.ones_like(z, bool))}   {by_round}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dataset", type=Path)
    p.add_argument("--games", type=float, default=1.0, help="share of the training games to use")
    p.add_argument("--per-game", type=int, default=16,
                   help="train on this many positions per game, spread over the rounds (0: all). A game's "
                        "positions share one result, so training on all of them mostly teaches the net to recognise games")
    p.add_argument("--q-mix", type=float, default=0.5,
                   help="weight of the search's value in the targets: the result alone is luck-heavy, the search's "
                        "estimate of the position is not (0: result only, 1: search only)")
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--lr", type=float, default=3e-4, help="peak learning rate, decayed to 0 over the run (cosine)")
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--dropout", type=float, default=0.3, help="the net memorizes games without it")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("experiments/data/models/value.pt"))
    args = p.parse_args()

    torch.manual_seed(args.seed)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    a, meta = load(args.dataset)
    obs = a["obs"]
    z = a["outcome"].astype(np.float32)
    margin = (a["score"].astype(np.float32) - a["opp_score"]) / MARGIN_SCALE
    rounds = a["round"]
    train_games, val_games = split_games(meta["seeds"], 0.1, args.games, args.seed)
    train = np.flatnonzero(np.isin(a["game"], train_games))
    val = np.flatnonzero(np.isin(a["game"], val_games))
    if args.per_game:  # validation too: its noise is the number of games, not of positions
        train = per_game(train, a["game"], rounds, args.per_game, args.seed)
        val = per_game(val, a["game"], rounds, args.per_game, args.seed)
    n_deals = lambda games: len({meta["seeds"][g] for g in games})
    print(f"{len(train_games)} training games from {n_deals(train_games)} deals ({len(train):,} positions), "
          f"{len(val_games)} validation games from {n_deals(val_games)} unseen deals ({len(val):,})")

    # From here on positions are indices into x, the observations of the rows used
    rows = np.sort(np.concatenate([train, val]))
    t0 = time.time()
    x = gathered(args.dataset, obs, rows)
    print(f"observations of the used rows: {x.nbytes / 1e9:.1f} GB ({time.time() - t0:.0f}s)")
    train, val = np.searchsorted(rows, train), np.searchsorted(rows, val)
    z, margin, rounds = z[rows], margin[rows], rounds[rows]

    # Baselines, fitted on the training positions
    n_player, i_score = len(meta["player_features"]), meta["player_features"].index("score_now")
    gap = score_gap(x, n_player, i_score)
    gap_train, gap_val = gap[train], gap[val]
    line = np.zeros_like(z[val])
    for r in (1, 2, 3, 4):
        tr, va = rounds[train] == r, rounds[val] == r
        slope, intercept = np.polyfit(gap_train[tr], z[train][tr], 1)
        line[va] = np.clip(slope * gap_val[va] + intercept, -1, 1)
    print("validation MSE / winner accuracy (decided games)")
    print(report("predict 0", np.zeros_like(z[val]), z[val], rounds[val]))
    print(report("line on score gap", line, z[val], rounds[val]))

    # Targets: the result (and final margin), mixed with the search's value of the position. Its points
    # become a result in [-1, 1] by tanh(points / s), s fitted on the training positions.
    v_target, m_target = z, margin
    if args.q_mix:
        q = root_q(a)[rows].astype(np.float32)
        scales = np.arange(1.0, 30.0, 0.5)
        s = scales[np.argmin([np.mean((np.tanh(q[train] / s) - z[train]) ** 2) for s in scales])]
        print(f"search value as a result: tanh(points / {s})")
        v_target = ((1 - args.q_mix) * z + args.q_mix * np.tanh(q / s)).astype(np.float32)
        m_target = ((1 - args.q_mix) * margin + args.q_mix * q / MARGIN_SCALE).astype(np.float32)

    net = ValueNet(x.shape[1], dropout=args.dropout).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    to = lambda x: torch.from_numpy(np.ascontiguousarray(x)).to(device)

    def evaluate(obs):
        net.eval()
        vs, ms = [], []
        with torch.no_grad():
            for b in range(0, len(obs), 4096):
                v, m = net(to(obs[b : b + 4096].astype(np.float32)))
                vs.append(v.cpu().numpy())
                ms.append(m.cpu().numpy())
        return np.concatenate(vs), np.concatenate(ms)

    best, best_state = float("inf"), None
    sample = np.sort(np.random.default_rng(1).choice(train, min(len(train), len(val)), replace=False))
    x_val, x_sample = x[val], x[sample]  # in memory: evaluated every epoch
    # x is read in large blocks, sequentially: with scattered rows, the OS re-reads the file from disk
    # every epoch (it doesn't stay cached in 8 GB). Blocks come in random order, positions shuffled within;
    # a block spans thousands of games, so a batch still mixes many.
    blocks = np.array_split(np.sort(train), max(1, len(train) // 65536))
    steps = args.epochs * sum(-(-len(blk) // args.batch) for blk in blocks)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    for epoch in range(1, args.epochs + 1):
        net.train()
        t0 = time.time()
        rng = np.random.default_rng(args.seed + epoch)
        for blk in rng.permutation(len(blocks)):
            pos = rng.permutation(blocks[blk])
            chunk = np.asarray(x[pos.min() : pos.max() + 1])
            for b in range(0, len(pos), args.batch):
                rows = pos[b : b + args.batch]
                v, m = net(to(chunk[rows - pos.min()].astype(np.float32)))
                loss = ((v - to(v_target[rows])) ** 2).mean() + ((m - to(m_target[rows])) ** 2).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
                sched.step()
        v_val, m_val = evaluate(x_val)
        v_tr, _ = evaluate(x_sample)
        val_mse = float(np.mean((v_val - z[val]) ** 2))
        print(f"epoch {epoch:2}  train MSE {np.mean((v_tr - z[sample]) ** 2):.3f}  val MSE {val_mse:.3f}  "
              f"val margin MSE {np.mean((m_val - margin[val]) ** 2):.3f}  ({time.time() - t0:.0f}s)", flush=True)  # fmt: skip
        if val_mse < best:
            best, best_state = val_mse, {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    net.load_state_dict(best_state)
    print(report("value net (best epoch)", evaluate(x_val)[0], z[val], rounds[val]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state": best_state, "n_obs": x.shape[1], "dropout": args.dropout, "dataset": str(args.dataset),
                "val_mse": best, "args": vars(args) | {"out": str(args.out), "dataset": str(args.dataset)}}, args.out)  # fmt: skip
    export_value_net(net, args.out.with_suffix(".bin"), MARGIN_SCALE)  # for mcts_rs (value_net=...)
    print(f"saved {args.out} and {args.out.with_suffix('.bin')}")


if __name__ == "__main__":
    main()
