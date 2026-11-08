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
import time
from pathlib import Path

import numpy as np
import torch

from lab.dataset import load
from wingspan.ai.nets import ValueNet

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


def score_gap(obs: np.ndarray, n_player: int, i_score: int) -> np.ndarray:
    """Current public score difference, me minus the opponent, in points (score_now is score / 120)."""
    return 120 * (obs[:, i_score].astype(np.float32) - obs[:, n_player + i_score].astype(np.float32))


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
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--dropout", type=float, default=0.1)
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
    n_deals = lambda games: len({meta["seeds"][g] for g in games})
    print(f"{len(train_games)} training games from {n_deals(train_games)} deals ({len(train):,} positions), "
          f"{len(val_games)} validation games from {n_deals(val_games)} unseen deals ({len(val):,})")

    # Baselines, fitted on the training positions
    n_player, i_score = len(meta["player_features"]), meta["player_features"].index("score_now")
    gap_train = score_gap(obs[train], n_player, i_score)
    gap_val = score_gap(obs[val], n_player, i_score)
    line = np.zeros_like(z[val])
    for r in (1, 2, 3, 4):
        tr, va = rounds[train] == r, rounds[val] == r
        slope, intercept = np.polyfit(gap_train[tr], z[train][tr], 1)
        line[va] = np.clip(slope * gap_val[va] + intercept, -1, 1)
    print("validation MSE / winner accuracy (decided games)")
    print(report("predict 0", np.zeros_like(z[val]), z[val], rounds[val]))
    print(report("line on score gap", line, z[val], rounds[val]))

    net = ValueNet(obs.shape[1], dropout=args.dropout).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    to = lambda x: torch.from_numpy(np.ascontiguousarray(x)).to(device)

    def evaluate(rows):
        net.eval()
        vs, ms = [], []
        with torch.no_grad():
            for b in range(0, len(rows), 4096):
                v, m = net(to(obs[rows[b : b + 4096]].astype(np.float32)))
                vs.append(v.cpu().numpy())
                ms.append(m.cpu().numpy())
        return np.concatenate(vs), np.concatenate(ms)

    best, best_state = float("inf"), None
    sample = np.random.default_rng(1).choice(train, min(len(train), len(val)), replace=False)
    for epoch in range(1, args.epochs + 1):
        net.train()
        t0 = time.time()
        shuffled = np.random.default_rng(args.seed + epoch).permutation(train)
        for b in range(0, len(train), args.batch):
            rows = np.sort(shuffled[b : b + args.batch])  # sorted: faster reads from disk
            v, m = net(to(obs[rows].astype(np.float32)))
            loss = ((v - to(z[rows])) ** 2).mean() + ((m - to(margin[rows])) ** 2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        v_val, m_val = evaluate(val)
        v_tr, _ = evaluate(sample)
        val_mse = float(np.mean((v_val - z[val]) ** 2))
        print(f"epoch {epoch:2}  train MSE {np.mean((v_tr - z[sample]) ** 2):.3f}  val MSE {val_mse:.3f}  "
              f"val margin MSE {np.mean((m_val - margin[val]) ** 2):.3f}  ({time.time() - t0:.0f}s)", flush=True)  # fmt: skip
        if val_mse < best:
            best, best_state = val_mse, {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    net.load_state_dict(best_state)
    print(report("value net (best epoch)", evaluate(val)[0], z[val], rounds[val]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state": best_state, "n_obs": obs.shape[1], "dropout": args.dropout, "dataset": str(args.dataset),
                "val_mse": best, "args": vars(args) | {"out": str(args.out), "dataset": str(args.dataset)}}, args.out)  # fmt: skip
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
