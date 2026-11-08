"""Python GameState -> the canonical JSON dict the Rust engine reads and writes (rust/src/state.rs)."""

import random

from wingspan.engine.core import GameState


class RecordingRandom(random.Random):
    """A Random that logs the outcomes the rules drew, for the Rust engine to replay: ("die", [face index])
    for each die rolled, ("shuffle", deck after) for each shuffle."""

    FACES = [["fish"], ["fruit"], ["rodent"], ["invertebrate"], ["seed"], ["invertebrate", "seed"]]

    def __init__(self, state):
        super().__init__()
        self.setstate(state)
        self.log = []

    def choice(self, seq):
        x = super().choice(seq)
        if seq == self.FACES:
            self.log.append(("die", [self.FACES.index(x)]))
        return x

    def shuffle(self, x):
        super().shuffle(x)
        self.log.append(("shuffle", list(x)))


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
