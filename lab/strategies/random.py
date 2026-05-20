from __future__ import annotations

import random

from game.core import GameState, Action

from .base import Strategy, register_strategy


@register_strategy
class RandomStrategy(Strategy):
    """Selects actions uniformly at random."""

    name = "random"

    def __init__(self, *, seed: int | None = None):
        self.seed: int = seed if seed is not None else random.randint(0, 2**31)
        self._rng = random.Random(self.seed)

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        return self._rng.choice(legal_actions)

    def __str__(self) -> str:
        return "Random"
