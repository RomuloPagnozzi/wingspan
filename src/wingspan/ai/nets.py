"""Neural networks over the encoder's vectors (wingspan.ai.encoding)."""

import torch
from torch import nn


class ValueNet(nn.Module):
    """Observation -> (v, margin): who is winning from the viewer's seat, as a value in [-1, 1]
    trained toward the game result, and by how much, trained toward the final score difference.

    The trunk (a plain MLP) compresses the observation into h; two one-layer heads read it.
    The margin head is an auxiliary target: richer than the result alone, so it helps the trunk
    learn what points are worth.
    """

    def __init__(self, n_obs: int, hidden: tuple[int, ...] = (512, 256), dropout: float = 0.1):
        super().__init__()
        layers, width = [], n_obs
        for h in hidden:
            layers += [nn.Linear(width, h), nn.ReLU(), nn.Dropout(dropout)]
            width = h
        self.trunk = nn.Sequential(*layers)
        self.value = nn.Linear(width, 1)
        self.margin = nn.Linear(width, 1)

    def forward(self, obs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(obs)
        return torch.tanh(self.value(h)).squeeze(-1), self.margin(h).squeeze(-1)


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
