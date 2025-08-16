import copy
from .data import GameState, roll_feeder, Spot
from .utils import find_leftmost_empty_spot
import json


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying the player's choice."""
    new_state = copy.deepcopy(state)

    match new_state.action_phase:
        case "main_turn":
            return _handle_main_turn(new_state, action)
        case "collecting_food":
            return _handle_food_collection(new_state, action)
        case "extra_food_action":
            return _handle_extra_food_action(new_state, action)
        case "select_bird_to_discard":
            return _handle_bird_discard_action(new_state, action)
        case "play_bird":
            return _handle_play_bird(new_state, action)
        case "pay_egg_cost":
            return _handle_pay_egg_cost(new_state, action)
        case "pay_food_cost":
            return _handle_pay_food_cost(new_state, action)
        case _:
            raise NotImplementedError


def _handle_main_turn(state: GameState, action: str) -> GameState:
    """Handle selection of one of the 4 main Wingspan actions."""
    match action:
        case "gain_food":
            return _handle_gain_food(state)
        case "play_bird":
            state.action_phase = "play_bird"
            return state
        case "lay_eggs":
            raise NotImplementedError
        case "draw_cards":
            raise NotImplementedError
        case _:
            raise ValueError(f"Unknown main turn action {action}")


def _handle_gain_food(state: GameState) -> GameState:
    """Handles main turn action gain food."""
    current_player = state.players[state.current_player_index]
    food_spot = find_leftmost_empty_spot(current_player.board[0])

    can_trade = food_spot and food_spot.extra_resource and current_player.bird_hand
    base_amount = food_spot.resource_amount if food_spot else 3

    if can_trade:
        state.action_phase = "extra_food_action"
        state.action_data = {"base_food_amount": base_amount}
    else:
        state.action_phase = "collecting_food"
        state.action_data = {"food_needed": base_amount}
    return state


def _handle_food_collection(state: GameState, action: str) -> GameState:
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


def _handle_play_bird(state: GameState, action: str) -> GameState:
    """Handle playing a specific bird on a specific spot."""
    if action.startswith("play_bird_"):
        parts = action.split("_")
        bird_id = int(parts[2])
        row = int(parts[4])
        col = int(parts[5])
        current_player = state.players[state.current_player_index]

        bird_to_play = None
        for bird in current_player.bird_hand:
            if bird.id == bird_id:
                bird_to_play = bird
                break

        if not bird_to_play:
            raise ValueError(f"Bird {bird_id} not in hand")
        if row < 0 or row >= len(current_player.board):
            raise ValueError(f"Invalid row: {row}")
        if col < 0 or col >= len(current_player.board[row]):
            raise ValueError(f"Invalid col: {col}")

        target_spot: Spot = current_player.board[row][col]

        if target_spot.bird is not None:
            raise ValueError(f"Spot at {row}, {col} is already occupied")

        if target_spot.egg_cost and not state.action_data.get("egg_paid"):
            state.action_data.update(
                {
                    "egg_cost": target_spot.egg_cost,
                    "egg_paid": False,
                    "callback": {"action_phase": state.action_phase, "action": action},
                }
            )
            state.action_phase = "pay_egg_cost"
            return state

        if bird_to_play.cost and not state.action_data.get("food_paid"):
            state.action_data.update(
                {
                    "food_cost": bird_to_play.cost,
                    "food_paid": False,
                    "callback": {"action_phase": state.action_phase, "action": action},
                }
            )
            state.action_phase = "pay_food_cost"
            return state

        target_spot.bird = bird_to_play
        current_player.bird_hand.remove(bird_to_play)
        current_player.action_cubes -= 1

        state.action_phase = "main_turn"
        state.action_data = {}
        return state

    raise ValueError(f"Unknown play bird aciton: {action}")


def _handle_pay_egg_cost(state: GameState, action: str) -> GameState:
    """Handle egg cost payment and continue to next phase."""
    payment = {int(k): v for k, v in json.loads(action).items()}
    current_player = state.players[state.current_player_index]
    relevant_board_birds = [
        spot.bird
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.id in payment.keys()
    ]
    bird_eggs = {bird.id: bird.eggs for bird in relevant_board_birds}

    if payment.keys() != bird_eggs.keys():
        raise ValueError(
            f"Birds from board {bird_eggs.keys()} and payment {payment.keys()} do not match."
        )

    if not all(bird_eggs[k] >= payment[k] for k in payment):
        raise ValueError(f"Not enough eggs in birds to pay egg cost.")

    for bird in relevant_board_birds:
        bird.eggs -= payment[bird.id]

    state.action_data["egg_paid"] = True
    state.action_phase = state.action_data["callback"]["action_phase"]
    return transition_state(state, state.action_data["callback"]["action"])


def _handle_pay_food_cost(state: GameState, action: str) -> GameState:
    """Handle food cost payment and continue to next phase."""
    payment = json.loads(action)
    current_player = state.players[state.current_player_index]

    if not all(food in current_player.food for food in payment.keys()):
        raise ValueError(
            f"Food from player {current_player.food} and payment {payment.keys()} do not match."
        )

    if not all(current_player.food[food] >= amount for food, amount in payment.items()):
        raise ValueError("Not enough food to pay food cost.")

    for food, amount in payment.items():
        current_player.food[food] -= amount

    state.action_data["food_paid"] = True
    state.action_phase = state.action_data["callback"]["action_phase"]
    return transition_state(state, state.action_data["callback"]["action"])
