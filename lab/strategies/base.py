from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, unique
from typing import Any, ClassVar, TypeVar

from game.core import GameState, Action


@unique
class ValueFunction(str, Enum):
    """How to compute value from terminal game state."""

    SCORE_DELTA = "score_delta"
    ABSOLUTE_SCORE = "absolute_score"
    WIN_LOSS = "win_loss"


class Strategy(ABC):
    """Abstract base for all game-playing strategies."""

    name: ClassVar[str]

    @abstractmethod
    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        """Select an action given game state and legal moves."""
        pass

    @property
    def config_for_storage(self) -> dict[str, Any]:
        """Return config dict for parquet storage."""
        return {}

    def get_last_visit_counts(self) -> dict[Action, int] | None:
        """Return visit counts from the last select_action call, if available."""
        return None

    def get_last_root_value(self) -> float | None:
        """Return MCTS root value from the last select_action call, if available."""
        return None

    def get_last_action_values(self) -> dict[Action, float] | None:
        """Return MCTS per-action Q-values from the last select_action call, if available."""
        return None


# Strategy registry
_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


_S = TypeVar("_S", bound=Strategy)


def register_strategy(cls: type[_S]) -> type[_S]:
    """Decorator to register a strategy class."""
    _STRATEGY_REGISTRY[cls.name] = cls
    return cls


def create_strategy(name: str, **kwargs) -> Strategy:
    """Create a strategy by name with optional kwargs."""
    if name not in _STRATEGY_REGISTRY:
        available = list(_STRATEGY_REGISTRY.keys())
        raise ValueError(f"Unknown strategy: {name}. Available: {available}")
    return _STRATEGY_REGISTRY[name](**kwargs)
