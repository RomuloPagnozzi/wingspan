"""`flat_mc_rs`: the flat_mc strategy with its playouts run by the Rust engine. Same config (FlatMCConfig),
same decision rule; only where the playouts run changes. Importing this module registers the strategy.

The game itself is still played by the Python engine, so recorded games replay in Python as before.
"""

import json

import wingspan_rs
from pystate import to_json

from wingspan.ai.base import register_strategy
from wingspan.ai.flat_mc import FlatMCStrategy
from wingspan.engine.core import Action, GameState


@register_strategy
class FlatMCRsStrategy(FlatMCStrategy):
    name = "flat_mc_rs"

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            return legal_actions[0]
        p = self.params
        strs, totals, counts = wingspan_rs.flat_mc(
            json.dumps(to_json(state)),
            p.budget(state.game_phase),
            p.paired,
            p.value_function.value,
            self._rng.getrandbits(64),
        )
        assert strs == [str(a) for a in legal_actions], "Rust and Python disagree on the legal moves"
        means = [t / c if c else float("-inf") for t, c in zip(totals, counts)]
        self._last_action_values = {a: m for a, m in zip(legal_actions, means) if m > float("-inf")}
        self._last_visit_counts = dict(zip(legal_actions, counts))
        return legal_actions[max(range(len(legal_actions)), key=means.__getitem__)]

    def __str__(self) -> str:
        return "Rust" + super().__str__()
