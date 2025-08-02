from typing import List
import copy
from .data import GameState, Spot, roll_feeder


def _find_leftmost_empty_spot(board_row: List[Spot]) -> Spot | None:
    """Find the leftmost empty spot in a board row."""
    for spot in board_row:
        if spot.bird is None:
            return spot
    return None


def get_actions(state: GameState) -> List[str]:
    """Return list of actions available to current player at the moment."""
    match state.decision_phase:
        case "main_turn":
            return _get_main_turn_actions(state)
        case "collecting_food":
            return _get_food_collection_actions(state)
        case "extra_food_decision":
            return ["trade_bird", "skip_trade"]
        case "select_bird_to_discard":
            return _get_bird_discard_actions(state)
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
        case "extra_food_decision":
            return _handle_extra_food_decision(new_state, action)
        case "select_bird_to_discard":
            return _handle_bird_discard(new_state, action)
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
            current_player = state.players[state.current_player_index]
            food_spot = _find_leftmost_empty_spot(current_player.board[0])

            can_trade = (
                food_spot and food_spot.extra_resource and current_player.bird_hand
            )
            base_amount = food_spot.resource_amount if food_spot else 3

            if can_trade:
                state.decision_phase = "extra_food_decision"
                state.decision_data = {"base_food_amount": base_amount}
            else:
                state.decision_phase = "collecting_food"
                state.decision_data = {"food_needed": base_amount}
            return state
        case _:
            raise NotImplementedError


def _get_food_collection_actions(state: GameState) -> List[str]:
    """Return possible foods to collect."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")

    if len(set(tuple(sorted(die_face)) for die_face in state.feeder.values())) == 1:
        actions.append("reroll_all")

    return actions


def _handle_food_collection_action(state: GameState, action: str) -> GameState:
    """Handle dice selection during food collection."""
    if action.startswith("select_die_"):
        parts = action.split("_")
        die_index = int(parts[2])
        food_type = parts[3]

        if die_index not in state.feeder:
            raise ValueError(f"Die {die_index} not in feeder")
        if food_type not in state.feeder[die_index]:
            raise ValueError(f"Die {die_index} doesn't have {food_type}")

        current_player = state.players[state.current_player_index]
        current_player.food[food_type] += 1

        del state.feeder[die_index]

        if not state.feeder:
            state.feeder = roll_feeder()

        state.decision_data["food_needed"] -= 1

        if not state.decision_data["food_needed"]:
            state.decision_phase = "main_turn"
            state.decision_data = {}
        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    raise NotImplementedError(
        f"Current state {state.decision_phase, state.decision_data, action}"
    )


def _handle_extra_food_decision(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading bird for extra food"""
    base_amount = state.decision_data["base_food_amount"]

    match action:
        case "trade_bird":
            state.decision_phase = "select_bird_to_discard"
            return state
        case "skip_trade":
            state.decision_phase = "collecting_food"
            state.decision_data = {"food_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra food action: {action}")


def _get_bird_discard_actions(state: GameState) -> List[str]:
    """Return birds that can be discarded for extra food."""
    current_player = state.players[state.current_player_index]
    return [f"discard_bird_{bird.id}" for bird in current_player.bird_hand]


def _handle_bird_discard(state: GameState, action: str) -> GameState:
    """Handle discarding a bird for extra food."""
    if action.startswith("discard_bird_"):
        bird_id = int(action.split("_")[2])
        current_player = state.players[state.current_player_index]

        bird_to_discard = None
        for bird in current_player.bird_hand:
            if bird.id == bird_id:
                bird_to_discard = bird
                break

        if not bird_to_discard:
            raise ValueError(f"Bird {bird_id} not in hand")

        current_player.bird_hand.remove(bird_to_discard)
        state.discarded_birds.append(bird_to_discard)

        base_amount = state.decision_data["base_food_amount"]
        state.decision_phase = "collecting_food"
        state.decision_data = {"food_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown bird discard action: {action}")
