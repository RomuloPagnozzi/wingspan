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


try:
    import wingspan_rs  # noqa: F401  (the Rust engine, built from rust/; see rust/README.md)
except ModuleNotFoundError:
    pass
else:
    from . import rust  # noqa: F401  (registers flat_mc_rs and mcts_rs)
