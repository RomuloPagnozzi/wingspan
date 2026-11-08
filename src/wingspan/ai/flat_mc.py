"""Flat Monte Carlo: random playouts for each legal move, then the best average. No tree.

The champion MCTS spreads its visits almost evenly over the root moves (its UCB bonus dwarfs the
value gaps), so it already behaves much like this. Flat Monte Carlo makes that explicit and adds
one option, `paired` (common random numbers): each re-dealt world, and each playout seed, is used
for every legal move instead of one move each. The luck those playouts share (hidden cards, dice,
the random continuation) then cancels when moves are compared, while every move is still averaged
over the same number of different worlds. See EXP-011 in docs/EXPERIMENTS.md.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from wingspan.engine.actions import get_actions
from wingspan.engine.core import Action, GamePhase, GameState, redeterminize
from wingspan.engine.engine import transition_state, transition_state_inplace

from .base import Strategy, ValueFunction, register_strategy
from .mcts import _compute_values


@dataclass(frozen=True, slots=True)
class FlatMCConfig:
    playouts: int = 1500  # per decision, split evenly across the legal moves
    paired: bool = True
    value_function: ValueFunction = ValueFunction.ABSOLUTE_SCORE
    # Per-phase budgets, e.g. {"lay_eggs": 300}: game phase name -> playouts per decision.
    # Phases not listed use `playouts`. Set in the experiment's YAML (`phase_playouts:`).
    phase_playouts: dict[str, int] | None = None

    def __post_init__(self):
        unknown = set(self.phase_playouts or ()) - {p.value for p in GamePhase}
        if unknown:  # a misspelt phase would silently fall back to the default budget
            raise ValueError(f"unknown game phases in phase_playouts: {sorted(unknown)}")

    def budget(self, phase: GamePhase) -> int:
        return (self.phase_playouts or {}).get(phase.value, self.playouts)


@register_strategy
class FlatMCStrategy(Strategy):
    name = "flat_mc"

    def __init__(self, *, params: FlatMCConfig | None = None, seed: int | None = None, **kwargs):
        if params is None:
            kwargs = {k: v for k, v in kwargs.items() if k in FlatMCConfig.__dataclass_fields__}
            if isinstance(kwargs.get("value_function"), str):
                kwargs["value_function"] = ValueFunction(kwargs["value_function"])
            params = FlatMCConfig(**kwargs)
        self.params = params
        self.seed: int = seed if seed is not None else random.randint(0, 2**31)
        self._rng = random.Random(self.seed)
        self._last_action_values: dict[Action, float] | None = None
        self._last_visit_counts: dict[Action, int] | None = None

    def _playout(self, world: GameState, action: Action, me: int, seed: int) -> float | None:
        try:
            state = transition_state(world, action)  # a copy: the world is reused when paired
        except Exception:
            return None  # not legal in this re-dealt world
        rng = random.Random(seed)
        while actions := get_actions(state):
            state = transition_state_inplace(state, rng.choice(actions))
        return _compute_values(state, self.params.value_function)[me]

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            return legal_actions[0]
        p = self.params
        budget = p.budget(state.game_phase)
        me = state.current_player_index
        totals = [0.0] * len(legal_actions)
        counts = [0] * len(legal_actions)
        for _ in range(max(1, budget // len(legal_actions))):
            if p.paired:  # one world and seed, shared by every move
                world, seed = redeterminize(state, me, self._rng), self._rng.getrandbits(32)
            for i, action in enumerate(legal_actions):
                if not p.paired:  # a fresh world and seed for every move
                    world, seed = redeterminize(state, me, self._rng), self._rng.getrandbits(32)
                value = self._playout(world, action, me, seed)
                if value is not None:
                    totals[i] += value
                    counts[i] += 1
        means = [t / c if c else float("-inf") for t, c in zip(totals, counts)]
        self._last_action_values = {a: m for a, m in zip(legal_actions, means) if m > float("-inf")}
        self._last_visit_counts = dict(zip(legal_actions, counts))
        return legal_actions[max(range(len(legal_actions)), key=means.__getitem__)]

    def get_last_visit_counts(self) -> dict[Action, int] | None:
        return self._last_visit_counts

    def get_last_action_values(self) -> dict[Action, float] | None:
        return self._last_action_values

    def __str__(self) -> str:
        return f"FlatMC(n={self.params.playouts}, {'paired' if self.params.paired else 'independent'})"
