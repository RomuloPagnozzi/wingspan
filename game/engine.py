import copy
from .data import GameState, roll_feeder
from .utils import find_leftmost_empty_spot


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying the player's choice."""
    new_state = copy.deepcopy(state)

    match new_state.action_phase:
        case "main_turn":
            return _handle_main_turn_phase(new_state, action)
        case "collecting_food":
            return _handle_food_collection_action(new_state, action)
        case "extra_food_action":
            return _handle_extra_food_action(new_state, action)
        case "select_bird_to_discard":
            return _handle_bird_discard_action(new_state, action)
        case _:
            raise NotImplementedError


def _handle_main_turn_phase(state: GameState, action: str) -> GameState:
    """Handle selection of one of the 4 main Wingspan actions."""
    match action:
        case "gain_food":
            current_player = state.players[state.current_player_index]
            food_spot = find_leftmost_empty_spot(current_player.board[0])

            can_trade = (
                food_spot and food_spot.extra_resource and current_player.bird_hand
            )
            base_amount = food_spot.resource_amount if food_spot else 3

            if can_trade:
                state.action_phase = "extra_food_action"
                state.action_data = {"base_food_amount": base_amount}
            else:
                state.action_phase = "collecting_food"
                state.action_data = {"food_needed": base_amount}
            return state
        case _:
            raise NotImplementedError


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

        state.action_data["food_needed"] -= 1

        if not state.action_data["food_needed"]:
            state.action_phase = "main_turn"
            state.action_data = {}
        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    raise NotImplementedError(
        f"Current state {state.action_phase, state.action_data, action}"
    )


def _handle_extra_food_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading bird for extra food"""
    base_amount = state.action_data["base_food_amount"]

    match action:
        case "trade_bird":
            state.action_phase = "select_bird_to_discard"
            return state
        case "skip_trade":
            state.action_phase = "collecting_food"
            state.action_data = {"food_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra food action: {action}")


def _handle_bird_discard_action(state: GameState, action: str) -> GameState:
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

        base_amount = state.action_data["base_food_amount"]
        state.action_phase = "collecting_food"
        state.action_data = {"food_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown bird discard action: {action}")
