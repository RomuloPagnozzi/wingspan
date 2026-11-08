"""Strategies whose search runs in the Rust engine (`rust/`, Python module `wingspan_rs`), and the
state export they use. Importing this module needs the extension built (see rust/README.md);
`wingspan.ai` imports it when it is, which registers the strategies:

- `flat_mc_rs`: `flat_mc` with its playouts in Rust. Same config (FlatMCConfig) and decision rule.
- `mcts_rs`: `mcts` IS-MCTS (determinize=True) with its search in Rust. Same config (MCTSConfig) and
  decision rule (most visited root child legal in the real state), plus `phase_simulations`: per-phase
  budgets like flat_mc's `phase_playouts`. The peek (determinize=False) mode is not ported.

The game itself stays in the Python engine: Rust only searches. `state_json` is the canonical state
the two engines exchange (`rust/src/state.rs`); `rust/py/parity.py` checks them against each other.
"""

import json

import wingspan_rs

from wingspan.engine.core import Action, GamePhase, GameState

from .base import register_strategy
from .flat_mc import FlatMCStrategy
from .mcts import MCTSStrategy


def state_json(state: GameState) -> str:
    """The state as the JSON the Rust engine reads."""
    return json.dumps(to_json(state))


# PowerExecution.context keys that change during play. The others are copies of the card's power details
# (looked up from the bird in Rust), so they are left out of the comparison.
DYNAMIC = {
    "activator", "awaiting_players", "draw_amount", "bonus_options", "available_cards", "food_type",
    "available_foods", "remaining_quantity", "valid_habitats", "valid_bird_ids", "target_habitat",
    "eligible_birds", "amount",
}
STATIC = {
    "power_data", "nest_type", "discard_type", "gain_type", "gain_qty", "action_type", "can_cache", "source",
    "quantity", "food_types", "types", "repeat_type", "current_habitat",
}


def _context(ctx: dict) -> dict:
    assert set(ctx) <= DYNAMIC | STATIC, f"unknown context keys {set(ctx) - DYNAMIC - STATIC}"
    out = {k: v for k, v in ctx.items() if k in DYNAMIC}
    if "eligible_birds" in out:
        out["eligible_birds"] = [[b["bird_id"], b["spot_row"], b["spot_col"]] for b in out["eligible_birds"]]
    return out


def to_json(s: GameState) -> dict:
    """Python GameState -> the canonical state dict of the Rust engine (rust/src/state.rs)."""
    ad = s.action_data
    assert not ad.pending_callback
    cost = ad.pending_cost
    return {
        "players": [
            {
                "id": p.id,
                "bird_hand": list(p.bird_hand),
                "bonus_hand": list(p.bonus_hand),
                "food": [[f, n] for f, n in p.food.items()],
                "board": [
                    [
                        None
                        if sp.bird is None
                        else {
                            "id": sp.bird.id,
                            "eggs": sp.bird.state.eggs,
                            "food": sp.bird.state.stashed_food,
                            "tucked": sp.bird.state.tucked_cards,
                        }
                        for sp in row
                    ]
                    for row in p.board
                ],
                "action_cubes": p.action_cubes,
                "first_player": p.first_player,
                "used_pink_powers": sorted(p.used_pink_powers),
                "score": {
                    "bird_points": p.score.bird_points,
                    "egg_points": p.score.egg_points,
                    "cached_food": p.score.cached_food,
                    "tucked_cards": p.score.tucked_cards,
                    "round_goals": list(p.score.round_goals),
                    "bonus_scores": sorted([k, v] for k, v in p.score.bonus_scores.items()),
                },
            }
            for p in s.players
        ],
        "bird_deck": list(s.bird_deck),
        "discarded_birds": list(s.discarded_birds),
        "bonus_deck": list(s.bonus_deck),
        "discarded_bonuses": list(s.discarded_bonuses),
        "bird_tray": list(s.bird_tray),
        "feeder": [[i, list(face)] for i, face in s.feeder.items()],
        "round": s.round,
        "current_player_index": s.current_player_index,
        "game_phase": s.game_phase.value,
        "action_data": {
            "powers_queue": [
                {
                    "power_id": q.power_id,
                    "bird_id": q.bird_id,
                    "spot_row": q.spot_row,
                    "spot_col": q.spot_col,
                    "player_index": q.player_index,
                }
                for q in ad.powers_queue
            ],
            "execution_stack": [
                {
                    "power_id": e.power_id,
                    "bird_id": e.bird_id,
                    "spot_row": e.spot_row,
                    "spot_col": e.spot_col,
                    "player_index": e.player_index,
                    "phase": e.phase,
                    "context": _context(e.context),
                }
                for e in ad.execution_stack
            ],
            "end_turn_effects": [
                {"effect_type": x.effect_type, "player_index": x.player_index, "amount": x.amount}
                for x in ad.end_turn_effects
            ],
            "current_power_index": ad.current_power_index,
            "action_player_index": ad.action_player_index,
            "food_needed": ad.food_needed,
            "eggs_needed": ad.eggs_needed,
            "cards_needed": ad.cards_needed,
            "base_amount": ad.base_amount,
            "gained_rodent": ad.gained_rodent,
            "amount_to_discard": ad.amount_to_discard,
            "pending_cost": None
            if cost is None
            else {
                "cost_type": cost.cost_type,
                "amount": cost.amount if isinstance(cost.amount, int) else None,
                "callback_phase": cost.callback_phase.value,
                "callback_action": str(cost.callback_action),
            },
        },
        "scoring_mode": s.round_goal_config.scoring_mode.value,
        "selected_goals": list(s.round_goal_config.selected_goals),
    }


@register_strategy
class FlatMCRsStrategy(FlatMCStrategy):
    name = "flat_mc_rs"

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            return legal_actions[0]
        p = self.params
        strs, totals, counts = wingspan_rs.flat_mc(
            state_json(state),
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


@register_strategy
class MCTSRsStrategy(MCTSStrategy):
    name = "mcts_rs"

    def __init__(self, *, phase_simulations: dict[str, int] | None = None, **kwargs):
        super().__init__(**kwargs)
        unknown = set(phase_simulations or ()) - {p.value for p in GamePhase}
        if unknown:  # a misspelt phase would silently fall back to the default budget
            raise ValueError(f"unknown game phases in phase_simulations: {sorted(unknown)}")
        self.phase_simulations = phase_simulations or {}

    @property
    def config(self) -> dict:
        return {**super().config, **({"phase_simulations": self.phase_simulations} if self.phase_simulations else {})}

    def select_action(self, state: GameState, legal_actions: list[Action]) -> Action:
        if len(legal_actions) == 1:
            self._last_visit_counts = {legal_actions[0]: 1}
            self._last_root_value = self._last_action_values = None
            return legal_actions[0]
        p = self.params
        assert p.determinize, "mcts_rs implements IS-MCTS only (determinize=True)"
        assert p.rollout_depth is None, "mcts_rs has no rollout_depth"
        strs, visits, values, root_value = wingspan_rs.ismcts(
            state_json(state),
            self.phase_simulations.get(state.game_phase.value, p.simulations),
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
