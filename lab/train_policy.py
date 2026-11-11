"""Train the policy net on a replay dataset (lab/dataset.py): the search's visit shares as targets.

    uv run --group train python -m lab.train_policy experiments/data/datasets/selfplay

Only the decisions searched with the full budget (10k simulations, a random quarter of them: playout cap
randomization) are targets; the others' visits are too noisy. The loss is the cross-entropy between the
visit shares π and the net's softmax over the legal moves. Same split by deal as lab/train_value.py.

Reports per phase, on validation: how often the net's top move is the search's most visited one, and
KL(π ‖ net), next to two baselines: uniform over the legal moves, and a prior on the move's kind alone
(per phase, the average visit share of that kind of move, e.g. main turn: lay eggs vs draw cards).
"""

import argparse
import time
from pathlib import Path

import numpy as np
import torch

from lab.dataset import load
from lab.train_value import gathered, per_game, split_games
from wingspan.ai.encoding import ACTION_KINDS
from wingspan.ai.nets import PolicyNet, export_policy_net, log_softmax_by

FULL_BUDGET = 10_000


def moves_of(off: np.ndarray, pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For decisions `pos` (their moves are off[p]:off[p + 1]): each move's decision within pos (0..len-1),
    and the move indices, concatenated in pos order."""
    n = off[pos + 1] - off[pos]
    seg = np.repeat(np.arange(len(pos)), n)
    starts = np.cumsum(n) - n
    return seg, np.repeat(off[pos], n) + np.arange(n.sum()) - np.repeat(starts, n)


def top1(logp: np.ndarray, best: np.ndarray, off: np.ndarray) -> np.ndarray:
    """Per decision, whether the highest-scored move is `best` (move indices); ties count as a fair draw
    among the tied moves (uniform scores give 1/n)."""
    top = np.maximum.reduceat(logp, off[:-1])
    is_top = logp >= np.repeat(top, np.diff(off)) - 1e-6
    return is_top[best] / np.add.reduceat(is_top, off[:-1])


def first_argmax(x: np.ndarray, off: np.ndarray) -> np.ndarray:
    """Index of each decision's largest value (the first of ties)."""
    seg = np.repeat(np.arange(len(off) - 1), np.diff(off))
    return np.lexsort((-x, seg))[off[:-1]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dataset", type=Path)
    p.add_argument("--games", type=float, default=1.0, help="share of the training games to use")
    p.add_argument("--per-game", type=int, default=0,
                   help="full-budget decisions per game, spread over the rounds (0: all; 16 loses 2-4 points of top-move agreement)")
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--lr", type=float, default=3e-4, help="peak learning rate, decayed to 0 over the run (cosine)")
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("experiments/data/models/policy.pt"))
    args = p.parse_args()

    torch.manual_seed(args.seed)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    a, meta = load(args.dataset)
    act_off = np.asarray(a["act_off"])
    visits = np.asarray(a["visits"])
    full = np.add.reduceat(visits.astype(np.int64), act_off[:-1]) >= FULL_BUDGET
    train_games, val_games = split_games(meta["seeds"], 0.1, args.games, args.seed)
    train = np.flatnonzero(full & np.isin(a["game"], train_games))
    val = np.flatnonzero(full & np.isin(a["game"], val_games))
    if args.per_game:
        train = per_game(train, a["game"], a["round"], args.per_game, args.seed)
        val = per_game(val, a["game"], a["round"], args.per_game, args.seed)

    # From here on decisions are indices into the used rows, and moves into their moves
    rows = np.sort(np.concatenate([train, val]))
    _, act_rows = moves_of(act_off, rows)
    off = np.concatenate([[0], np.cumsum(act_off[rows + 1] - act_off[rows])])
    t0 = time.time()
    x, acts = gathered(args.dataset, "obs", a["obs"], rows), gathered(args.dataset, "act", a["act"], act_rows)
    print(f"{len(train):,} training and {len(val):,} validation decisions ({len(act_rows):,} moves): "
          f"{(x.nbytes + acts.nbytes) / 1e9:.1f} GB ({time.time() - t0:.0f}s)")  # fmt: skip
    train, val = np.searchsorted(rows, train), np.searchsorted(rows, val)
    phase = np.asarray(a["phase"])[rows]
    v = visits[act_rows].astype(np.float32)
    pi = v / np.repeat(np.add.reduceat(v, off[:-1]), np.diff(off))
    kind = np.concatenate([acts[b : b + (1 << 20), : len(ACTION_KINDS)].argmax(1) for b in range(0, len(acts), 1 << 20)])

    # Kind prior: per phase, the average visit share of each kind of move, from the training decisions
    move_phase = np.repeat(phase, np.diff(off))
    _, train_moves = moves_of(off, train)
    share, count = np.zeros((len(meta["phases"]), len(ACTION_KINDS))), np.zeros((len(meta["phases"]), len(ACTION_KINDS)))
    np.add.at(share, (move_phase[train_moves], kind[train_moves]), pi[train_moves])
    np.add.at(count, (move_phase[train_moves], kind[train_moves]), 1)
    prior = share / np.maximum(count, 1)

    net = PolicyNet(x.shape[1], acts.shape[1], dropout=args.dropout).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    to = lambda x: torch.from_numpy(np.ascontiguousarray(x)).to(device)

    def logits(obs, act, seg):
        out = net(to(obs.astype(np.float32)), to(act.astype(np.float32)), to(seg))
        return log_softmax_by(out, to(seg), int(seg.max()) + 1)

    def evaluate(pos):
        """Log-probabilities of the moves of decisions `pos`, concatenated in pos order."""
        net.eval()
        out = []
        with torch.no_grad():
            for b in range(0, len(pos), 4096):
                seg, m = moves_of(off, pos[b : b + 4096])
                out.append(logits(x[pos[b : b + 4096]], acts[m], seg).cpu().numpy())
        return np.concatenate(out)

    def cross_entropy(pos, logp):
        _, m = moves_of(off, pos)
        return -np.sum(pi[m] * logp) / len(pos)

    sample = np.sort(np.random.default_rng(1).choice(train, min(len(train), len(val)), replace=False))
    blocks = np.array_split(np.sort(train), max(1, len(train) // 65536))
    steps = args.epochs * sum(-(-len(blk) // args.batch) for blk in blocks)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    best, best_state = float("inf"), None
    for epoch in range(1, args.epochs + 1):
        net.train()
        t0 = time.time()
        rng = np.random.default_rng(args.seed + epoch)
        for blk in rng.permutation(len(blocks)):
            pos = rng.permutation(blocks[blk])
            lo, hi = pos.min(), pos.max() + 1  # read sequentially: the arrays don't stay cached in memory
            x_chunk, a_chunk = np.asarray(x[lo:hi]), np.asarray(acts[off[lo] : off[hi]])
            for b in range(0, len(pos), args.batch):
                d = pos[b : b + args.batch]
                seg, m = moves_of(off, d)
                logp = logits(x_chunk[d - lo], a_chunk[m - off[lo]], seg)
                loss = -(to(pi[m]) * logp).sum() / len(d)
                opt.zero_grad()
                loss.backward()
                opt.step()
                sched.step()
        val_ce = cross_entropy(val, evaluate(val))
        print(f"epoch {epoch:2}  train CE {cross_entropy(sample, evaluate(sample)):.3f}  val CE {val_ce:.3f}  "
              f"({time.time() - t0:.0f}s)", flush=True)  # fmt: skip
        if val_ce < best:
            best, best_state = val_ce, {k: t.detach().cpu().clone() for k, t in net.state_dict().items()}

    # Per phase, on validation: top-move agreement and KL(π ‖ p) for the net and the two baselines
    net.load_state_dict(best_state)
    seg, m = moves_of(off, val)
    off_val = np.concatenate([[0], np.cumsum(np.diff(off)[val])])
    n_moves = np.diff(off_val)
    candidates = {
        "net": evaluate(val),
        "kind": np.log(np.maximum(prior[move_phase[m], kind[m]], 1e-9)),
        "uniform": -np.log(np.repeat(n_moves, n_moves)).astype(np.float64),
    }
    candidates["kind"] -= np.log(np.repeat(np.add.reduceat(np.exp(candidates["kind"]), off_val[:-1]), n_moves))
    best_move = first_argmax(pi[m], off_val)
    plogp = np.where(pi[m] > 0, pi[m] * np.log(np.maximum(pi[m], 1e-12)), 0)
    hits = {k: top1(lp, best_move, off_val) for k, lp in candidates.items()}
    kls = {k: np.add.reduceat(plogp - pi[m] * lp, off_val[:-1]) for k, lp in candidates.items()}
    print("\nvalidation, per phase: top move = the search's most visited (net / kind prior / uniform), "
          "KL(visits ‖ policy) (same order)")  # fmt: skip
    print(f"{'phase':24} {'decisions':>9} {'moves':>6}   {'top move':^22}   {'KL':^22}")
    for i, name in [(-1, "all")] + list(enumerate(meta["phases"])):
        sel = np.ones(len(val), bool) if i < 0 else phase[val] == i
        if sel.any():
            top = " / ".join(f"{hits[k][sel].mean():5.0%}" for k in candidates)
            kl = " / ".join(f"{kls[k][sel].mean():5.2f}" for k in candidates)
            print(f"{name:24} {sel.sum():9,} {n_moves[sel].mean():6.1f}   {top}   {kl}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state": best_state, "n_obs": x.shape[1], "n_act": acts.shape[1], "dropout": args.dropout, "val_ce": best,
                "args": vars(args) | {"out": str(args.out), "dataset": str(args.dataset)}}, args.out)  # fmt: skip
    export_policy_net(net, args.out.with_suffix(".bin"))  # for the Rust search
    print(f"saved {args.out} and {args.out.with_suffix('.bin')}")


if __name__ == "__main__":
    main()
