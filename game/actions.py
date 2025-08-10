from typing import List
from .data import GameState
from .utils import can_play_a_bird


def get_actions(state: GameState) -> List[str]:
    """Return list of available actions for current player."""
    match state.action_phase:
        case "main_turn":
            return _get_main_turn_actions(state)
        case "collecting_food":
            return _get_food_collection_actions(state)
        case "extra_food_action":
            return ["trade_bird", "skip_trade"]
        case "select_bird_to_discard":
            return _get_bird_discard_actions(state)
        case _:
            raise NotImplementedError


def _get_main_turn_actions(state: GameState) -> List[str]:
    """Return the 4 main Wingspan actions available during a player's turn."""
    current_player = state.players[state.current_player_index]
    if not current_player.action_cubes:
        return []

    actions = []

    available_egg_capacity = any(
        spot.bird.eggs < spot.bird.egg_limit
        for row in current_player.board
        for spot in row
        if spot.bird is not None
    )

    if available_egg_capacity:
        actions.append("lay_eggs")

    if can_play_a_bird(current_player):
        actions.append("play_bird")

    actions.append("gain_food")
    actions.append("draw_cards")
    return actions


def _get_food_collection_actions(state: GameState) -> List[str]:
    """Return possible foods to collect."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")

    if len(set(tuple(sorted(die_face)) for die_face in state.feeder.values())) == 1:
        actions.append("reroll_all")

    return actions


def _get_bird_discard_actions(state: GameState) -> List[str]:
    """Return birds that can be discarded for extra food."""
    current_player = state.players[state.current_player_index]
    return [f"discard_bird_{bird.id}" for bird in current_player.bird_hand]
