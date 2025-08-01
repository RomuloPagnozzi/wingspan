from typing import List
import copy
from .data import GameState


def get_actions(state: GameState) -> List[str]:
    """Return list of actions available to current player at the moment."""
    match state.decision_phase:
        case "main_turn":
            return _get_main_turn_actions(state)
        case "collecting_food":
            return _get_food_collection_actions(state)
        case _:
            raise NotImplementedError


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying the action."""
    new_state = copy.deepcopy(state)

    match new_state.decision_phase:
        case "main_turn":
            return _handle_main_turn_action(new_state, action)
        case "collecting_food":
            return _handle_food_collection_action(new_state, action)
        case _:
            raise NotImplementedError


def _get_main_turn_actions(state: GameState) -> List[str]:
    """Return actions on main turn game phase"""
    current_player = state.players[state.current_player_index]
    if not current_player.action_cubes:
        return []

    actions = []

    available_egg_capacity = any(
        [
            spot.bird.eggs < spot.bird.egg_limit
            for row in current_player.board
            for spot in row
            if spot.bird is not None
        ]
    )

    if available_egg_capacity:
        actions.append("lay_eggs")

    if current_player.bird_hand:
        # TODO Add proper validation
        actions.append("play_bird")

    actions.append("gain_food")
    actions.append("draw_cards")
    return actions


def _handle_main_turn_action(state: GameState, action: str) -> GameState:
    """Handle main turn action selection."""
    match action:
        case "gain_food":
            state.decision_phase = "collecting_food"
            # TODO: Calculate how much food player should get
            state.decision_data = {"food_needed": 1}  # Simplified for now
            return state
        case _:
            raise NotImplementedError


def _get_food_collection_actions(state: GameState) -> List[str]:
    """Return possible foods to collect."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")
        # TODO: Add reroll action when appropriate
    return actions


def _handle_food_collection_action(state: GameState, action: str) -> GameState:
    """Handle dice selection during food collection."""
    if action.startswith("select_die_"):
        parts = action.split("_")
        die_index = int(parts[2])
        food_type = parts[3]

        current_player = state.players[state.current_player_index]
        current_player.food[food_type] += 1

        del state.feeder[die_index]

        state.decision_data["food_needed"] -= 1

        if not state.decision_data["food_needed"]:
            state.decision_phase = "main_turn"
            state.decision_data = {}
            # TODO handle brown powers, extra food etc

        return state

    raise NotImplementedError
