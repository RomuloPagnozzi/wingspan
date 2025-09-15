import copy
from .data import GameState, roll_feeder, Spot
from .utils import find_leftmost_empty_spot, get_current_player_index
import json


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying the player's choice."""
    new_state = copy.deepcopy(state)
    handler = _ACTION_HANDLERS.get(new_state.action_phase)
    if not handler:
        raise NotImplementedError(f"No handler for: {new_state.action_phase}")
    return handler(new_state, action)


def _handle_game_setup(state: GameState, action: str) -> GameState:
    """Handle game setup phase transitions."""
    match action:
        case "start_setup":
            state.action_phase = "selecting_initial_cards"
            return state
        case "end_setup":
            state.action_phase = "main_turn"
            state.round = 1
            return state
        case _:
            raise ValueError(f"Invalid setup action: {action}")


def _handle_selecting_initial_cards(state: GameState, action: str) -> GameState:
    """Handle initial card selection during setup."""
    selection = json.loads(action)

    current_player = state.players[state.current_player_index]
    current_player.bird_hand = [
        bird for bird in current_player.bird_hand if bird.id in selection["kept_birds"]
    ]
    current_player.bonus_hand = [
        bonus
        for bonus in current_player.bonus_hand
        if bonus.id == selection["kept_bonus"]
    ]

    bird_amount = len(selection["kept_birds"])
    if bird_amount:
        state.action_data = {"amount_to_discard": bird_amount}
        state.action_phase = "discarding_food"
    else:
        current_player.action_cubes = 8
        state.action_phase = "game_setup"
        state.current_player_index = get_current_player_index(state)

    return state


def _handle_discarding_food(state: GameState, action: str) -> GameState:
    """Handle food discarding during setup."""
    discard = json.loads(action)
    current_player = state.players[state.current_player_index]

    for food_type, amount in discard.items():
        if current_player.food.get(food_type, 0) < amount:
            raise ValueError(
                f"Not enough {food_type} to discard {amount} (have {current_player.food.get(food_type, 0)})"
            )

        current_player.food[food_type] -= amount
        if current_player.food[food_type] == 0:
            del current_player.food[food_type]

    current_player.action_cubes = 8
    state.action_data = {}
    state.action_phase = "game_setup"
    state.current_player_index = get_current_player_index(state)

    return state


def _handle_main_turn(state: GameState, action: str) -> GameState:
    """Handle selection of one of the 4 main Wingspan actions."""
    match action:
        case "gain_food":
            return _handle_gain_food(state)
        case "play_bird":
            state.action_phase = "play_bird"
            return state
        case "lay_eggs":
            return _handle_lay_eggs(state)
        case "draw_cards":
            return _handle_draw_cards(state)
        case _:
            raise ValueError(f"Unknown main turn action {action}")


def _handle_gain_food(state: GameState) -> GameState:
    """Handles main turn action gain food."""
    current_player = state.players[state.current_player_index]
    forest_spot = find_leftmost_empty_spot(current_player.board[0])

    can_trade = current_player.bird_hand and (
        not forest_spot or (forest_spot and forest_spot.extra_resource)
    )
    base_amount = forest_spot.resource_amount if forest_spot else 3

    if can_trade:
        state.action_phase = "extra_food_action"
        state.action_data = {"base_food_amount": base_amount}
    else:
        state.action_phase = "collecting_food"
        state.action_data = {"food_needed": base_amount}
    return state


def _handle_lay_eggs(state: GameState) -> GameState:
    """Handles main turn action lay eggs."""
    current_player = state.players[state.current_player_index]
    grassland_spot = find_leftmost_empty_spot(current_player.board[1])

    can_trade = current_player.food and (
        not grassland_spot or (grassland_spot and grassland_spot.extra_resource)
    )
    base_amount = grassland_spot.resource_amount if grassland_spot else 4

    if can_trade:
        state.action_phase = "extra_lay_eggs_action"
        state.action_data = {"base_eggs_amount": base_amount}
    else:
        state.action_phase = "laying_eggs"
        state.action_data = {"eggs_needed": base_amount}
    return state


def _handle_draw_cards(state: GameState) -> GameState:
    """Handles main turn action draw cards."""
    current_player = state.players[state.current_player_index]
    wetland_spot = find_leftmost_empty_spot(current_player.board[2])

    played_birds = [
        spot.bird
        for row in current_player.board
        for spot in row
        if spot.bird is not None
    ]
    available_eggs = sum(bird.eggs for bird in played_birds) if played_birds else 0
    can_trade = available_eggs and (
        not wetland_spot or (wetland_spot and wetland_spot.extra_resource)
    )
    base_amount = wetland_spot.resource_amount if wetland_spot else 3

    if can_trade:
        state.action_phase = "extra_card_draw_action"
        state.action_data = {"base_cards_amount": base_amount}
    else:
        state.action_phase = "drawing_cards"
        state.action_data = {"cards_needed": base_amount}
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
        if food_type in current_player.food:
            current_player.food[food_type] += 1
        else:
            current_player.food[food_type] = 1

        del state.feeder[die_index]

        if not state.feeder:
            state.feeder = roll_feeder()

        state.action_data["food_needed"] -= 1

        if not state.action_data["food_needed"]:
            current_player.action_cubes -= 1
            state.action_phase = "main_turn"
            state.action_data = {}
            state.current_player_index = get_current_player_index(state)
        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    raise NotImplementedError(
        f"Current state {state.action_phase, state.action_data, action}"
    )


def _handle_egg_laying(state: GameState, action: str) -> GameState:
    """Handle laying eggs in birds."""
    eggs_to_lay = {int(k): v for k, v in json.loads(action).items()}
    current_player = state.players[state.current_player_index]
    relevant_board_birds = [
        spot.bird
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.id in eggs_to_lay.keys()
    ]
    bird_capacity = {
        bird.id: bird.egg_limit - bird.eggs for bird in relevant_board_birds
    }

    if eggs_to_lay.keys() != bird_capacity.keys():
        raise ValueError(
            f"Birds from board {bird_capacity.keys()} and eggs_to_lay {eggs_to_lay.keys()} do not match."
        )

    if not all(bird_capacity[k] >= eggs_to_lay[k] for k in eggs_to_lay):
        raise ValueError(f"Not enough capacity in birds to lay eggs.")

    for bird in relevant_board_birds:
        bird.eggs += eggs_to_lay[bird.id]

    current_player.action_cubes -= 1
    state.action_phase = "main_turn"
    state.action_data = {}
    state.current_player_index = get_current_player_index(state)
    return state


def _handle_card_draw(state: GameState, action: str) -> GameState:
    """Handle drawing cards."""
    card_selection = json.loads(action)
    current_player = state.players[state.current_player_index]

    for bird_id in card_selection["tray_birds"]:
        for bird in state.bird_tray:
            if bird.id == bird_id:
                current_player.bird_hand.append(bird)
                state.bird_tray.remove(bird)
                break

    for _ in range(card_selection["deck_cards"]):
        if state.bird_deck:
            current_player.bird_hand.append(state.bird_deck.pop())

    while len(state.bird_tray) < 3 and state.bird_deck:
        state.bird_tray.append(state.bird_deck.pop())

    current_player.action_cubes -= 1
    state.action_phase = "main_turn"
    state.action_data = {}
    state.current_player_index = get_current_player_index(state)
    return state


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


def _handle_extra_lay_eggs_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading food token for extra egg."""
    base_amount = state.action_data["base_eggs_amount"]

    match action:
        case "trade_food":
            state.action_phase = "select_food_to_discard"
            return state
        case "skip_trade":
            state.action_phase = "laying_eggs"
            state.action_data = {"eggs_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra lay eggs action: {action}")


def _handle_extra_card_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading egg for extra card."""
    base_amount = state.action_data["base_cards_amount"]

    match action:
        case "trade_egg":
            state.action_phase = "select_egg_to_discard"
            return state
        case "skip_trade":
            state.action_phase = "drawing_cards"
            state.action_data = {"cards_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra card action: {action}")


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


def _handle_food_discard_action(state: GameState, action: str) -> GameState:
    """Handle discarding a food token for extra eggs."""
    if action.startswith("discard_food_"):
        food_key = action.split("_")[2]
        current_player = state.players[state.current_player_index]

        if current_player.food.get(food_key, 0) <= 0:
            raise ValueError(
                f"Food {food_key} not in player's food stash {current_player.food}"
            )

        current_player.food[food_key] -= 1
        if current_player.food[food_key] == 0:
            del current_player.food[food_key]

        base_amount = state.action_data["base_eggs_amount"]
        state.action_phase = "laying_eggs"
        state.action_data = {"eggs_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown food discard action: {action}")


def _handle_select_egg_discard_action(state: GameState, action: str) -> GameState:
    """Handle discarding an egg for extra card."""
    if action.startswith("discard_egg_"):
        parts = action.split("_")
        bird_id = int(parts[2])
        current_player = state.players[state.current_player_index]

        bird_with_egg = None
        for row in current_player.board:
            for spot in row:
                if (
                    spot.bird is not None
                    and spot.bird.id == bird_id
                    and spot.bird.eggs > 0
                ):
                    bird_with_egg = spot.bird
                    break
            if bird_with_egg:
                break

        if not bird_with_egg:
            raise ValueError(f"Bird {bird_id} not found on board or has no eggs")

        bird_with_egg.eggs -= 1

        base_amount = state.action_data["base_cards_amount"]
        state.action_phase = "drawing_cards"
        state.action_data = {"cards_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown egg discard action: {action}")


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
        state.current_player_index = get_current_player_index(state)
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

    if not all(
        current_player.food.get(food, 0) >= amount for food, amount in payment.items()
    ):
        raise ValueError("Not enough food to pay food cost.")

    for food, amount in payment.items():
        current_player.food[food] -= amount
        if current_player.food[food] == 0:
            del current_player.food[food]

    state.action_data["food_paid"] = True
    state.action_phase = state.action_data["callback"]["action_phase"]
    return transition_state(state, state.action_data["callback"]["action"])


_ACTION_HANDLERS = {
    "game_setup": _handle_game_setup,
    "selecting_initial_cards": _handle_selecting_initial_cards,
    "discarding_food": _handle_discarding_food,
    "main_turn": _handle_main_turn,
    "collecting_food": _handle_food_collection,
    "laying_eggs": _handle_egg_laying,
    "drawing_cards": _handle_card_draw,
    "extra_food_action": _handle_extra_food_action,
    "extra_lay_eggs_action": _handle_extra_lay_eggs_action,
    "extra_card_draw_action": _handle_extra_card_action,
    "select_bird_to_discard": _handle_bird_discard_action,
    "select_food_to_discard": _handle_food_discard_action,
    "select_egg_to_discard": _handle_select_egg_discard_action,
    "play_bird": _handle_play_bird,
    "pay_egg_cost": _handle_pay_egg_cost,
    "pay_food_cost": _handle_pay_food_cost,
}
