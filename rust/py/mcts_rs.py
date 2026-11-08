"""`mcts_rs`: the mcts strategy (IS-MCTS, determinize=True) with its search run by the Rust engine. Same
config (MCTSConfig) and decision rule (most visited root child legal in the real state). Importing this
module registers the strategy. The peek (determinize=False) mode is not ported.
"""

import json

import wingspan_rs
from pystate import to_json

from wingspan.ai.base import register_strategy
from wingspan.ai.mcts import MCTSStrategy
from wingspan.engine.core import Action, GameState


@register_strategy
class MCTSRsStrategy(MCTSStrategy):
    name = "mcts_rs"

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            self._last_visit_counts = {legal_actions[0]: 1}
            self._last_root_value = self._last_action_values = None
            return legal_actions[0]
        p = self.params
        assert p.determinize, "mcts_rs implements IS-MCTS only (determinize=True)"
        assert p.rollout_depth is None, "mcts_rs has no rollout_depth"
        strs, visits, values, root_value = wingspan_rs.ismcts(
            json.dumps(to_json(state)),
            p.simulations,
            p.exploration_constant,
            p.value_function.value,
            p.widening_k,
            p.widening_alpha,
            self._rng.getrandbits(64),
        )
        by_str = {str(a): a for a in legal_actions}
        # Root children legal only in some re-dealt world are dropped, as Python filters them out
        kids = [(by_str[s], n, v) for s, n, v in zip(strs, visits, values) if s in by_str]
        self._last_visit_counts = {a: n for a, n, _ in kids}
        self._last_root_value = root_value
        self._last_action_values = {a: v for a, n, v in kids if n > 0}
        if kids:
            return max(kids, key=lambda k: k[1])[0]
        return self._rng.choice(legal_actions)

    def __str__(self) -> str:
        return "Rust" + super().__str__()
