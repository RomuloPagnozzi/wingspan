from .base import Strategy, ValueFunction, create_strategy, register_strategy
from .random import RandomStrategy
from .mcts import MCTSStrategy, MCTSConfig
from .flat_mc import FlatMCStrategy, FlatMCConfig

__all__ = [
    "Strategy",
    "ValueFunction",
    "create_strategy",
    "register_strategy",
    "RandomStrategy",
    "MCTSStrategy",
    "MCTSConfig",
    "FlatMCStrategy",
    "FlatMCConfig",
]

# Optional: `flat_mc_rs` (flat_mc with its playouts in the Rust engine, rust/) when the extension is built.
try:
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.append(str(_Path(__file__).parents[3] / "rust" / "py"))
    import flat_mc_rs as _flat_mc_rs  # noqa: F401  (registers the strategy)
except ImportError:
    pass
