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


def to_json(s: GameState) -> dict:
    ad = s.action_data
    assert not (ad.powers_queue or ad.execution_stack or ad.end_turn_effects or ad.pending_callback)
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
