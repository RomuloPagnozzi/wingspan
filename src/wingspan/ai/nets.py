"""Neural networks over the encoder's vectors (wingspan.ai.encoding)."""

import torch
from torch import nn


def mlp(width: int, hidden: tuple[int, ...], dropout: float) -> tuple[nn.Sequential, int]:
    """Linear + ReLU + dropout per hidden width; returns the stack and its output width."""
    layers = []
    for h in hidden:
        layers += [nn.Linear(width, h), nn.ReLU(), nn.Dropout(dropout)]
        width = h
    return nn.Sequential(*layers), width


class ValueNet(nn.Module):
    """Observation -> (v, margin): who is winning from the viewer's seat, as a value in [-1, 1]
    trained toward the game result, and by how much, trained toward the final score difference.

    The trunk (a plain MLP) compresses the observation into h; two one-layer heads read it.
    The margin head is an auxiliary target: richer than the result alone, so it helps the trunk
    learn what points are worth.
    """

    def __init__(self, n_obs: int, hidden: tuple[int, ...] = (512, 256), dropout: float = 0.1):
        super().__init__()
        self.trunk, width = mlp(n_obs, hidden, dropout)
        self.value = nn.Linear(width, 1)
        self.margin = nn.Linear(width, 1)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(obs)
        return torch.tanh(self.value(h)).squeeze(-1), self.margin(h).squeeze(-1)


class PolicyNet(nn.Module):
    """(observation, legal moves) -> one logit per move, trained toward the search's visit shares.

    The trunk summarizes the position into h, a small net g summarizes each move's encoding, and a move's
    logit is h · g(move): the position decides which properties of a move matter now, the same g reads
    every move, so one net handles a decision of any size (3 main-turn moves or 400 egg placements).
    """

    def __init__(self, n_obs: int, n_act: int, hidden: tuple[int, ...] = (512, 256), dim: int = 128,
                 dropout: float = 0.1):  # fmt: skip
        super().__init__()
        self.trunk, width = mlp(n_obs, hidden, dropout)
        self.h = nn.Linear(width, dim)
        self.g = nn.Sequential(nn.Linear(n_act, dim), nn.ReLU(), nn.Linear(dim, dim))

    def forward(self, obs: torch.Tensor, act: torch.Tensor, seg: torch.Tensor) -> torch.Tensor:
        """obs [B, n_obs]; act [M, n_act], every decision's legal moves one after another; seg [M], the
        decision (0..B-1) each move belongs to. Returns the M logits."""
        return (self.h(self.trunk(obs))[seg] * self.g(act)).sum(-1)


def log_softmax_by(logits: torch.Tensor, seg: torch.Tensor, n: int) -> torch.Tensor:
    """Log-softmax within each decision's moves (seg as in PolicyNet.forward)."""
    top = torch.full((n,), -torch.inf, device=logits.device).scatter_reduce(0, seg, logits.detach(), "amax")
    shifted = logits - top[seg]
    total = torch.zeros(n, device=logits.device).index_add(0, seg, shifted.exp())
    return shifted - total.log()[seg]


def export_value_net(net: ValueNet, path, margin_scale: float) -> None:
    """Write the weights for the Rust search (rust/src/net.rs reads this layout): f32 margin scale, u32 number
    of linear layers (trunk, value head, margin head), then per layer u32 out, u32 in, f32 weights, f32 bias."""
    import struct

    layers = [m for m in net.trunk if isinstance(m, nn.Linear)] + [net.value, net.margin]
    with open(path, "wb") as f:
        f.write(struct.pack("<fI", margin_scale, len(layers)))
        for layer in layers:
            w = layer.weight.detach().cpu().float().contiguous()
            f.write(struct.pack("<II", *w.shape))
            f.write(w.numpy().astype("<f4").tobytes())
            f.write(layer.bias.detach().cpu().float().numpy().astype("<f4").tobytes())
