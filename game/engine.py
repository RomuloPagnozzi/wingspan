import copy
from .data import GameState, roll_feeder, GamePhase, Spot
from .utils import (
    find_leftmost_empty_spot,
    get_current_player_index,
    get_triggered_powers,
    get_valid_birds_for_eggs,
)
import json
from .effects import (
    draw_cards_effect,
    parse_draw_cards_action,
    parse_lay_eggs_action,
    lay_eggs_effect,
    select_die_effect,
    parse_select_die_action,
    place_bird_effect,
    parse_play_bird_action,
    pay_eggs_effect,
    parse_pay_eggs_action,
    pay_food_effect,
    parse_pay_food_action,
    discard_bird_from_hand_effect,
    gain_food_effect,
    tuck_cards_effect,
)


# =============================================================================
# Flow control helpers
# =============================================================================


def _finish_main_action(
    state: GameState, color: str, habitat: str | None = None, spot: Spot | None = None
) -> GameState:
    """Complete a main action: consume cube, check powers, transition."""
    current_player = state.players[state.current_player_index]
    current_player.action_cubes -= 1

    triggered_powers = get_triggered_powers(
        current_player, color, habitat=habitat, spot=spot
    )
    if triggered_powers:
        state.game_phase = GamePhase.ACTIVATE_POWERS
        state.action_data = {
            "powers_queue": triggered_powers,
            "current_power_index": 0,
        }
        return state

    state.game_phase = GamePhase.MAIN_TURN
    state.action_data = {}
    state.current_player_index = get_current_player_index(state)
    return state


# =============================================================================
# Power execution
# =============================================================================


def _activate_powers(state: GameState, action: str) -> GameState:
    """Handle power activation choices."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_2_choices":
        return _handle_power_2_choice(state, action)
    if sub_phase == "power_4_select_discard":
        return _handle_power_4_select_discard(state, action)
    if sub_phase == "power_4_select_gain":
        return _handle_power_4_select_gain(state, action)
    if sub_phase == "power_5_select_bonus":
        return _handle_power_5_select_bonus(state, action)
    if sub_phase == "power_6_select_card":
        return _handle_power_6_select_card(state, action)
    if sub_phase == "power_7_choose_starting_player":
        return _handle_power_7_choose_starting_player(state, action)
    if sub_phase == "power_7_select_die":
        return _handle_power_7_select_die(state, action)
    if sub_phase == "power_8_select_food_type":
        return _handle_power_8_select_food_type(state, action)
    if sub_phase == "power_8_select_die":
        return _handle_power_8_select_die(state, action)
    if sub_phase == "power_8_choose_cache":
        return _handle_power_8_choose_cache(state, action)
    if sub_phase == "power_9_select_habitat":
        return _handle_power_9_select_habitat(state, action)
    if sub_phase == "power_10_select_bird":
        return _handle_power_10_select_bird(state, action)

    powers_queue = state.action_data["powers_queue"]
    current_power_index = state.action_data["current_power_index"]

    if current_power_index >= len(powers_queue):
        raise ValueError("No more powers in queue to activate")

    current_power = powers_queue[current_power_index]
    power_data = current_power["power_data"]
    power_type = power_data["data"]["id"]

    if action == "skip_power":
        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)

    if action == "activate_power":
        executor = POWER_EXECUTORS.get(power_type)
        if executor:
            state = executor(state, current_power)

        if state.action_data.get("sub_phase") is None:
            state.action_data["current_power_index"] += 1
            return _check_powers_done(state)

        return state

    raise ValueError(f"Unknown power activation action: {action}")


def _check_powers_done(state: GameState) -> GameState:
    """Check if all powers processed, transition to end turn if so."""
    powers_queue = state.action_data.get("powers_queue", [])
    current_index = state.action_data.get("current_power_index", 0)

    if current_index >= len(powers_queue):
        state.game_phase = GamePhase.END_TURN
        return _handle_end_turn(state, "")

    return state


def _execute_power_1(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 1: All players gain 1 resource."""
    power_data = power_entry["power_data"]
    resource_type = power_data["data"]["details"].get("type")

    if resource_type == "card":
        for i in range(len(state.players)):
            state = draw_cards_effect(
                state, tray_bird_ids=[], deck_count=1, player_index=i
            )
    else:
        for i in range(len(state.players)):
            state = gain_food_effect(state, resource_type, amount=1, player_index=i)

    return state


def _execute_power_2(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 2: All players lay eggs on nest type. Sets up multi-player choices."""
    power_data = power_entry["power_data"]
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")
    activator = state.current_player_index

    player_order = [activator] + [
        i for i in range(len(state.players)) if i != activator
    ]
    awaiting = [
        i for i in player_order if get_valid_birds_for_eggs(state.players[i], nest_type)
    ]

    if awaiting:
        state.action_data["sub_phase"] = "power_2_choices"
        state.action_data["activator"] = activator
        state.action_data["awaiting_players"] = awaiting
        state.action_data["nest_type"] = nest_type
        state.current_player_index = awaiting[0]

    return state


def _handle_power_2_choice(state: GameState, action: str) -> GameState:
    """Handle a player's egg distribution choice for power 2."""
    choice_data = action.replace("activate_", "")
    egg_distribution = {int(k): v for k, v in json.loads(choice_data).items()}
    state = lay_eggs_effect(
        state, egg_distribution, player_index=state.current_player_index
    )

    awaiting = state.action_data["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        state.action_data["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    state.current_player_index = state.action_data.pop("activator")
    del state.action_data["sub_phase"]
    del state.action_data["awaiting_players"]
    del state.action_data["nest_type"]
    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_3(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 3: Cache seed on bird."""
    spot = power_entry["spot"]
    bird = spot.bird
    bird.stashed_food += 1
    return state


def _execute_power_4(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 4: Discard egg/food to gain food/wild/cards."""
    power_data = power_entry["power_data"]
    details = power_data["data"]["details"]

    state.action_data["sub_phase"] = "power_4_select_discard"
    state.action_data["power_4_discard_type"] = details.get("discard")
    state.action_data["power_4_gain_type"] = details.get("gain")
    state.action_data["power_4_gain_qty"] = details.get("gain_qty", 1)
    state.action_data["power_4_action"] = details.get("action")
    state.action_data["power_4_activating_bird_id"] = power_entry.get("bird_id")

    return state


def _handle_power_4_select_discard(state: GameState, action: str) -> GameState:
    """Handle discard selection for power 4."""
    discard_type = state.action_data["power_4_discard_type"]
    gain_type = state.action_data["power_4_gain_type"]
    gain_qty = state.action_data["power_4_gain_qty"]
    action_type = state.action_data["power_4_action"]
    activating_bird_id = state.action_data["power_4_activating_bird_id"]

    if discard_type == "egg":
        bird_id = int(action.split("_")[-1])
        state = pay_eggs_effect(state, {bird_id: 1})
    else:
        food_type = action.split("_")[-1]
        state = pay_food_effect(state, {food_type: 1})

    if gain_type == "card":
        if action_type == "draw":
            state = draw_cards_effect(state, tray_bird_ids=[], deck_count=gain_qty)
        elif action_type == "tuck":
            state = tuck_cards_effect(state, activating_bird_id, gain_qty)

        del state.action_data["sub_phase"]
        del state.action_data["power_4_discard_type"]
        del state.action_data["power_4_gain_type"]
        del state.action_data["power_4_gain_qty"]
        del state.action_data["power_4_action"]
        del state.action_data["power_4_activating_bird_id"]

        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)

    elif gain_type == "wild":
        state.action_data["sub_phase"] = "power_4_select_gain"
        return state
    else:
        state = gain_food_effect(state, gain_type, amount=gain_qty)

        del state.action_data["sub_phase"]
        del state.action_data["power_4_discard_type"]
        del state.action_data["power_4_gain_type"]
        del state.action_data["power_4_gain_qty"]
        del state.action_data["power_4_action"]
        del state.action_data["power_4_activating_bird_id"]

        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)


def _handle_power_4_select_gain(state: GameState, action: str) -> GameState:
    """Handle resource gain selection for power 4 (wild resource)."""
    food_gain_str = action.replace("gain_", "")
    food_distribution = json.loads(food_gain_str)

    for food_type, amount in food_distribution.items():
        state = gain_food_effect(state, food_type, amount=amount)

    del state.action_data["sub_phase"]
    del state.action_data["power_4_discard_type"]
    del state.action_data["power_4_gain_type"]
    del state.action_data["power_4_gain_qty"]
    del state.action_data["power_4_action"]
    del state.action_data["power_4_activating_bird_id"]

    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_5(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 5: Draw cards or bonus."""
    power_data = power_entry["power_data"]
    details = power_data["data"].get("details", {})
    amount = details.get("amount")
    discard = details.get("discard")
    bonus = details.get("bonus")

    if not bonus:
        state = draw_cards_effect(state, [], amount)
        if discard:
            state.action_data.setdefault("end_turn_effects", []).append(
                {
                    "type": "discard_cards",
                    "player_index": state.current_player_index,
                    "amount": 1,
                }
            )
        return state

    if bonus:
        drawn_cards = [state.bonus_deck.pop() for _ in range(amount)]
        state.action_data["power_5_bonus_options"] = drawn_cards
        state.action_data["sub_phase"] = "power_5_select_bonus"
        return state

    return state


def _handle_power_5_select_bonus(state: GameState, action: str) -> GameState:
    """Handle selecting which bonus card to keep from the 2 drawn."""
    bonus_id = int(action.split("_")[-1])
    drawn_cards = state.action_data.get("power_5_bonus_options", [])

    selected_card = next((card for card in drawn_cards if card.id == bonus_id), None)
    if not selected_card:
        raise ValueError("Invalid bonus selection")

    state.players[state.current_player_index].bonus_hand.append(selected_card)

    for card in drawn_cards:
        if card.id != bonus_id:
            state.discarded_bonuses.append(card)

    del state.action_data["power_5_bonus_options"]
    del state.action_data["sub_phase"]

    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_6(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 6: Draw N+1 cards, all players select one clockwise."""
    activator = state.current_player_index
    num_players = len(state.players)
    cards_to_draw = num_players + 1

    drawn_cards = [state.bird_deck.pop() for _ in range(cards_to_draw)]

    player_order = [activator]
    for i in range(1, num_players):
        player_order.append((activator + i) % num_players)
    player_order.append(activator)

    state.action_data["sub_phase"] = "power_6_select_card"
    state.action_data["activator"] = activator
    state.action_data["awaiting_players"] = player_order.copy()
    state.action_data["power_6_available_cards"] = drawn_cards
    state.current_player_index = player_order[0]

    return state


def _handle_power_6_select_card(state: GameState, action: str) -> GameState:
    """Handle player's card selection for power 6."""
    card_id = int(action.split("_")[-1])
    available_cards = state.action_data["power_6_available_cards"]

    selected_card = next((c for c in available_cards if c.id == card_id), None)
    if not selected_card:
        raise ValueError(f"Card {card_id} not in available cards")

    current_player = state.players[state.current_player_index]
    current_player.bird_hand.append(selected_card)

    available_cards.remove(selected_card)
    state.action_data["power_6_available_cards"] = available_cards

    awaiting = state.action_data["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        state.action_data["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    if len(available_cards) != 0:
        raise ValueError(f"Expected 0 remaining cards, got {len(available_cards)}")

    activator_index = state.action_data["activator"]
    state.current_player_index = activator_index
    del state.action_data["sub_phase"]
    del state.action_data["awaiting_players"]
    del state.action_data["power_6_available_cards"]
    del state.action_data["activator"]

    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_7(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 7: Each player gains 1 die from birdfeeder"""
    activator = state.current_player_index

    state.action_data["sub_phase"] = "power_7_choose_starting_player"
    state.action_data["activator"] = activator

    return state


def _handle_power_7_choose_starting_player(state: GameState, action: str) -> GameState:
    """Handle activator's choice of which player starts die selection."""
    starting_player_index = int(action.split("_")[-1])

    if starting_player_index < 0 or starting_player_index >= len(state.players):
        raise ValueError(f"Invalid player index: {starting_player_index}")

    num_players = len(state.players)
    player_order = []
    for i in range(num_players):
        player_order.append((starting_player_index + i) % num_players)

    state.action_data["sub_phase"] = "power_7_select_die"
    state.action_data["awaiting_players"] = player_order
    state.current_player_index = player_order[0]

    return state


def _handle_power_7_select_die(state: GameState, action: str) -> GameState:
    """Handle player's die selection from birdfeeder."""
    die_index, food_type = parse_select_die_action(action)
    state = select_die_effect(
        state, die_index, food_type, player_index=state.current_player_index
    )

    awaiting = state.action_data["awaiting_players"]
    awaiting.remove(state.current_player_index)

    if awaiting:
        state.action_data["awaiting_players"] = awaiting
        state.current_player_index = awaiting[0]
        return state

    activator_index = state.action_data.pop("activator")
    state.current_player_index = activator_index
    del state.action_data["sub_phase"]
    del state.action_data["awaiting_players"]

    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_8(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 8: Gain food with optional caching and source selection."""
    power_data = power_entry["power_data"]
    details = power_data["data"].get("details", {})
    can_cache = details["can_cache"]
    source = details["source"]
    quantity = details["quantity"]
    food_types = details["food_types"]

    if can_cache and quantity != 1:
        raise ValueError(
            f"Invalid power 8: can_cache=True requires quantity=1, got {quantity}"
        )

    available_foods = {
        food for food in food_types for face in state.feeder.values() if food in face
    }

    if not can_cache and len(food_types) == 1 and source == "supply":
        food_type = food_types[0]
        gain_food_effect(state, food_type, quantity, state.current_player_index)
        return state

    if (
        not can_cache
        and len(food_types) == 1
        and source == "birdfeeder"
        and quantity == "all"
    ):
        food_type = food_types[0]
        indices = [
            die_idx for die_idx, face in state.feeder.items() if food_type in face
        ]
        for die_idx in indices:
            select_die_effect(state, die_idx, food_type, state.current_player_index)
        return state

    if source == "supply" and can_cache:
        food_type = food_types[0]

        gain_food_effect(state, food_type, 1, state.current_player_index)

        state.action_data["sub_phase"] = "power_8_choose_cache"
        state.action_data["power_8_food_type"] = food_type
        state.action_data["power_8_activating_bird_id"] = power_entry.get("bird_id")
        return state

    if source == "birdfeeder":

        if len(food_types) > 1 and len(available_foods) > 1:
            state.action_data["sub_phase"] = "power_8_select_food_type"
            state.action_data["power_8_food_types"] = list(available_foods)
            state.action_data["power_8_can_cache"] = can_cache
            state.action_data["power_8_quantity"] = quantity
            if can_cache:
                state.action_data["power_8_activating_bird_id"] = power_entry.get(
                    "bird_id"
                )
            return state

        food_type = food_types[0] if len(food_types) == 1 else list(available_foods)[0]

        matching_dice = [
            die_idx for die_idx, face in state.feeder.items() if food_type in face
        ]

        if quantity == 1 and len(matching_dice) == 1 and not can_cache:
            select_die_effect(
                state, matching_dice[0], food_type, state.current_player_index
            )
            return state

        if quantity == 1:
            state.action_data["sub_phase"] = "power_8_select_die"
            state.action_data["power_8_food_type"] = food_type
            state.action_data["power_8_can_cache"] = can_cache
            if can_cache:
                state.action_data["power_8_activating_bird_id"] = power_entry.get(
                    "bird_id"
                )
            return state

        state.action_data["sub_phase"] = "power_8_select_die"
        state.action_data["power_8_food_type"] = food_type
        state.action_data["power_8_remaining_quantity"] = quantity
        return state

    return state


def _power_8_cleanup(state: GameState) -> None:
    """Remove all power_8_* keys from action_data."""
    keys_to_remove = [k for k in state.action_data if k.startswith("power_8_")]
    for key in keys_to_remove:
        del state.action_data[key]


def _handle_power_8_select_food_type(state: GameState, action: str) -> GameState:
    """Handle food type selection for Power 8."""
    food_type = action.replace("select_food_type_", "")
    state.action_data["power_8_food_type"] = food_type

    quantity = state.action_data["power_8_quantity"]
    can_cache = state.action_data["power_8_can_cache"]

    matching_dice = [
        die_idx for die_idx, foods in state.feeder.items() if food_type in foods
    ]

    if quantity == "all":

        for die_idx in matching_dice:
            select_die_effect(state, die_idx, food_type, state.current_player_index)

        del state.action_data["sub_phase"]
        _power_8_cleanup(state)
        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)

    if quantity == 1 and len(matching_dice) == 1 and not can_cache:

        select_die_effect(
            state, matching_dice[0], food_type, state.current_player_index
        )
        del state.action_data["sub_phase"]
        _power_8_cleanup(state)
        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)

    state.action_data["sub_phase"] = "power_8_select_die"
    if quantity > 1:
        state.action_data["power_8_remaining_quantity"] = quantity
    return state


def _handle_power_8_select_die(state: GameState, action: str) -> GameState:
    """Handle die selection for Power 8."""
    parts = action.split("_")
    die_index = int(parts[2])
    food_type = state.action_data["power_8_food_type"]

    state = select_die_effect(state, die_index, food_type, state.current_player_index)

    if "power_8_remaining_quantity" in state.action_data:
        state.action_data["power_8_remaining_quantity"] -= 1
        remaining = state.action_data["power_8_remaining_quantity"]

        if remaining > 0:
            return state

    if state.action_data.get("power_8_can_cache"):

        state.action_data["sub_phase"] = "power_8_choose_cache"
        return state
    else:

        del state.action_data["sub_phase"]
        _power_8_cleanup(state)
        state.action_data["current_power_index"] += 1
        return _check_powers_done(state)


def _handle_power_8_choose_cache(state: GameState, action: str) -> GameState:
    """Handle cache vs supply decision for quantity=1 food."""
    food_type = state.action_data["power_8_food_type"]
    activating_bird_id = state.action_data["power_8_activating_bird_id"]
    current_player = state.players[state.current_player_index]

    if action == "cache_food":

        current_player.food[food_type] -= 1
        if current_player.food[food_type] == 0:
            del current_player.food[food_type]

        for row in current_player.board:
            for spot in row:
                if spot.bird and spot.bird.id == activating_bird_id:
                    spot.bird.stashed_food += 1
                    break

    del state.action_data["sub_phase"]
    _power_8_cleanup(state)
    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_9(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 9: Move bird to another habitat if rightmost."""
    spot = power_entry["spot"]
    bird = spot.bird
    current_habitat = spot.habitat

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_player = state.players[state.current_player_index]
    valid_habitats = []

    for habitat in bird.habitats:
        if habitat != current_habitat:
            target_row = current_player.board[habitat_map[habitat]]
            if find_leftmost_empty_spot(target_row) is not None:
                valid_habitats.append(habitat)

    if len(valid_habitats) == 1:
        target_habitat = valid_habitats[0]
        target_row = current_player.board[habitat_map[target_habitat]]
        new_spot = find_leftmost_empty_spot(target_row)
        if not new_spot:
            raise ValueError("target spot not available")

        spot.bird = None
        new_spot.bird = bird

        return state

    state.action_data["sub_phase"] = "power_9_select_habitat"
    state.action_data["power_9_valid_habitats"] = valid_habitats
    state.action_data["power_9_bird_id"] = bird.id
    state.action_data["power_9_current_habitat"] = current_habitat
    return state


def _handle_power_9_select_habitat(state: GameState, action: str) -> GameState:
    """Handle habitat selection for Power 9."""
    habitat = action.split("_")[2]

    bird_id = state.action_data["power_9_bird_id"]
    current_habitat = state.action_data["power_9_current_habitat"]

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_player = state.players[state.current_player_index]

    old_habitat_row = current_player.board[habitat_map[current_habitat]]
    old_spot = None
    bird = None
    for spot in old_habitat_row:
        if spot.bird and spot.bird.id == bird_id:
            old_spot = spot
            bird = spot.bird
            break

    if not old_spot or not bird:
        raise ValueError(f"Bird {bird_id} not found in {current_habitat}")

    target_row = current_player.board[habitat_map[habitat]]
    new_spot = find_leftmost_empty_spot(target_row)
    if not new_spot:
        raise ValueError("target spot not available")

    old_spot.bird = None
    new_spot.bird = bird

    del state.action_data["sub_phase"]
    del state.action_data["power_9_valid_habitats"]
    del state.action_data["power_9_bird_id"]
    del state.action_data["power_9_current_habitat"]
    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_10(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 10: Lay eggs on birds."""
    power_data = power_entry["power_data"]
    details = power_data["data"].get("details", {})
    is_this = details.get("this", False)
    nest_type = details.get("type", "")

    current_player = state.players[state.current_player_index]

    if is_this:
        spot = power_entry.get("spot")
        if spot and spot.bird:
            egg_distribution = {spot.bird.id: 1}
            state = lay_eggs_effect(state, egg_distribution)
        return state

    if nest_type != "any":
        valid_birds = get_valid_birds_for_eggs(current_player, nest_type)
        if valid_birds:
            egg_distribution = {bird.id: 1 for bird in valid_birds}
            state = lay_eggs_effect(state, egg_distribution)
        return state

    valid_birds = []
    for row in current_player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.eggs < spot.bird.egg_limit:
                valid_birds.append(spot.bird)

    if len(valid_birds) == 1:
        egg_distribution = {valid_birds[0].id: 1}
        state = lay_eggs_effect(state, egg_distribution)
        return state

    state.action_data["sub_phase"] = "power_10_select_bird"
    state.action_data["power_10_valid_bird_ids"] = [bird.id for bird in valid_birds]
    return state


def _handle_power_10_select_bird(state: GameState, action: str) -> GameState:
    """Handle bird selection for Power 10 (type: 'any')."""
    bird_id = int(action.split("_")[-1])

    egg_distribution = {bird_id: 1}
    state = lay_eggs_effect(state, egg_distribution)

    del state.action_data["sub_phase"]
    del state.action_data["power_10_valid_bird_ids"]
    state.action_data["current_power_index"] += 1
    return _check_powers_done(state)


def _execute_power_11(state: GameState, power_entry: dict) -> GameState:
    """Execute Power ID 11: Draw card and tuck if wingspan < threshold."""
    power_data = power_entry["power_data"]
    details = power_data["data"].get("details", {})
    wingspan_threshold = details["wingspan"]

    spot = power_entry.get("spot")
    if not spot or not spot.bird:
        raise ValueError("Power 11 requires activating bird")

    activating_bird = spot.bird
    drawn_bird = state.bird_deck.pop()

    if drawn_bird.wingspan < wingspan_threshold:
        activating_bird.tucked_cards += 1
    else:
        state.discarded_birds.append(drawn_bird)

    return state


def _handle_end_turn(state: GameState, action: str) -> GameState:
    """Handle end-of-turn deferred effects."""
    effects = state.action_data.get("end_turn_effects", [])

    if not effects:
        state.game_phase = GamePhase.MAIN_TURN
        state.action_data = {}
        state.current_player_index = get_current_player_index(state)
        return state

    current_effect = effects[0]
    effect_type = current_effect["type"]

    if effect_type == "discard_cards":
        sub_phase = state.action_data.get("sub_phase")

        if not sub_phase:
            state.action_data["sub_phase"] = "end_turn_discard_card"
            state.action_data["discard_amount"] = current_effect["amount"]
            return state

        if sub_phase == "end_turn_discard_card":
            card_id = int(action.split("_")[-1])
            player = state.players[current_effect["player_index"]]

            card_to_discard = next(
                (c for c in player.bird_hand if c.id == card_id), None
            )
            if card_to_discard:
                player.bird_hand.remove(card_to_discard)
                state.discarded_birds.append(card_to_discard)

            effects.pop(0)
            state.action_data.pop("sub_phase", None)
            state.action_data.pop("discard_amount", None)

            if not effects:
                state.action_data.pop("end_turn_effects", None)
                state.game_phase = GamePhase.MAIN_TURN
                state.action_data = {}
                state.current_player_index = get_current_player_index(state)

            return state

    return state


POWER_EXECUTORS = {
    1: _execute_power_1,
    2: _execute_power_2,
    3: _execute_power_3,
    4: _execute_power_4,
    5: _execute_power_5,
    6: _execute_power_6,
    7: _execute_power_7,
    8: _execute_power_8,
    9: _execute_power_9,
    10: _execute_power_10,
    11: _execute_power_11,
}


# =============================================================================
# Main actions
# =============================================================================


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying an action."""
    new_state = copy.deepcopy(state)
    handler = _ACTION_HANDLERS.get(new_state.game_phase)
    if not handler:
        raise NotImplementedError(f"No handler for: {new_state.game_phase}")
    return handler(new_state, action)


def _route_game_setup(state: GameState, action: str) -> GameState:
    """Handle game setup phase transitions."""
    match action:
        case "start_setup":
            state.game_phase = GamePhase.SELECT_INITIAL_CARDS
            return state
        case "end_setup":
            state.game_phase = GamePhase.MAIN_TURN
            state.round = 1
            return state
        case _:
            raise ValueError(f"Invalid action: {action}")


def _select_initial_cards(state: GameState, action: str) -> GameState:
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
        state.game_phase = GamePhase.DISCARD_FOOD
    else:
        current_player.action_cubes = 8
        state.game_phase = GamePhase.GAME_SETUP
        state.current_player_index = get_current_player_index(state)
    return state


def _discard_food(state: GameState, action: str) -> GameState:
    """Handle food discarding during setup."""
    discard = json.loads(action)

    current_player = state.players[state.current_player_index]
    for food_type, amount in discard.items():
        if current_player.food.get(food_type, 0) < amount:
            raise ValueError(
                f"""Not enough {food_type} to discard {amount}
                (there's {current_player.food.get(food_type, 0)})"""
            )

    state = pay_food_effect(state, discard)

    current_player.action_cubes = 8
    state.action_data = {}
    state.game_phase = GamePhase.GAME_SETUP
    state.current_player_index = get_current_player_index(state)
    return state


def _route_main_turn(state: GameState, action: str) -> GameState:
    """Handle selection of one of the 4 main Wingspan actions."""
    current_player = state.players[state.current_player_index]

    match action:
        case "gain_food":
            forest_spot = find_leftmost_empty_spot(current_player.board[0])
            base_amount = forest_spot.resource_amount if forest_spot else 3
            can_trade = current_player.bird_hand and (
                not forest_spot or forest_spot.extra_resource
            )

            if can_trade:
                state.game_phase = GamePhase.EXTRA_FOOD_ACTION
                state.action_data = {"base_food_amount": base_amount}
            else:
                state.game_phase = GamePhase.COLLECT_FOOD
                state.action_data = {"food_needed": base_amount}
            return state

        case "play_bird":
            state.game_phase = GamePhase.PLAY_BIRD
            return state

        case "lay_eggs":
            grassland_spot = find_leftmost_empty_spot(current_player.board[1])
            base_amount = grassland_spot.resource_amount if grassland_spot else 4
            can_trade = current_player.food and (
                not grassland_spot or grassland_spot.extra_resource
            )

            if can_trade:
                state.game_phase = GamePhase.EXTRA_LAY_EGGS_ACTION
                state.action_data = {"base_eggs_amount": base_amount}
            else:
                state.game_phase = GamePhase.LAY_EGGS
                state.action_data = {"eggs_needed": base_amount}
            return state

        case "draw_cards":
            wetland_spot = find_leftmost_empty_spot(current_player.board[2])
            base_amount = wetland_spot.resource_amount if wetland_spot else 3

            played_birds = [
                spot.bird
                for row in current_player.board
                for spot in row
                if spot.bird is not None
            ]
            available_eggs = (
                sum(bird.eggs for bird in played_birds) if played_birds else 0
            )
            can_trade = available_eggs and (
                not wetland_spot or wetland_spot.extra_resource
            )

            if can_trade:
                state.game_phase = GamePhase.EXTRA_CARD_DRAW_ACTION
                state.action_data = {"base_cards_amount": base_amount}
            else:
                state.game_phase = GamePhase.DRAW_CARDS
                state.action_data = {"cards_needed": base_amount}
            return state

        case _:
            raise ValueError(f"Invalid action: {action}")


def _collect_food(state: GameState, action: str) -> GameState:
    """Handle dice selection."""

    if action.startswith("select_die_"):
        die_index, food_type = parse_select_die_action(action)

        state = select_die_effect(state, die_index, food_type)
        state.action_data["food_needed"] -= 1

        if not state.action_data["food_needed"]:
            return _finish_main_action(state, "brown", habitat="forest")

        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    raise ValueError(f"No known action{action}")


def _lay_eggs(state: GameState, action: str) -> GameState:
    """Handle laying eggs."""
    egg_distribution = parse_lay_eggs_action(action)

    state = lay_eggs_effect(state, egg_distribution)

    return _finish_main_action(state, "brown", habitat="grassland")


def _draw_cards(state: GameState, action: str) -> GameState:
    """Handle drawing cards"""
    tray_birds, deck_count = parse_draw_cards_action(action)

    state = draw_cards_effect(state, tray_birds, deck_count)

    return _finish_main_action(state, "brown", habitat="wetland")


def _route_extra_food_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading bird for extra food"""
    base_amount = state.action_data["base_food_amount"]

    match action:
        case "trade_bird":
            state.game_phase = GamePhase.SELECT_BIRD_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.COLLECT_FOOD
            state.action_data = {"food_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra food action: {action}")


def _route_extra_lay_eggs_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading food token for extra egg."""
    base_amount = state.action_data["base_eggs_amount"]

    match action:
        case "trade_food":
            state.game_phase = GamePhase.SELECT_FOOD_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.LAY_EGGS
            state.action_data = {"eggs_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra lay eggs action: {action}")


def _route_extra_card_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading egg for extra card."""
    base_amount = state.action_data["base_cards_amount"]

    match action:
        case "trade_egg":
            state.game_phase = GamePhase.SELECT_EGG_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.DRAW_CARDS
            state.action_data = {"cards_needed": base_amount}
            return state
        case _:
            raise ValueError(f"Unknown extra card action: {action}")


def _discard_bird_for_food(state: GameState, action: str) -> GameState:
    """Handle discarding a bird for extra food."""
    if action.startswith("discard_bird_"):
        bird_id = int(action.split("_")[2])

        state = discard_bird_from_hand_effect(state, bird_id)

        base_amount = state.action_data["base_food_amount"]
        state.game_phase = GamePhase.COLLECT_FOOD
        state.action_data = {"food_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown bird discard action: {action}")


def _discard_food_for_egg(state: GameState, action: str) -> GameState:
    """Handle discarding a food token for extra eggs."""
    if action.startswith("discard_food_"):
        food_key = action.split("_")[2]
        current_player = state.players[state.current_player_index]

        if current_player.food.get(food_key, 0) <= 0:
            raise ValueError(
                f"Food {food_key} not in player's food stash {current_player.food}"
            )

        state = pay_food_effect(state, {food_key: 1})

        base_amount = state.action_data["base_eggs_amount"]
        state.game_phase = GamePhase.LAY_EGGS
        state.action_data = {"eggs_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown food discard action: {action}")


def _discard_egg_for_card(state: GameState, action: str) -> GameState:
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

        state = pay_eggs_effect(state, {bird_id: 1})

        base_amount = state.action_data["base_cards_amount"]
        state.game_phase = GamePhase.DRAW_CARDS
        state.action_data = {"cards_needed": base_amount + 1}

        return state

    raise ValueError(f"Unknown egg discard action: {action}")


def _play_bird(state: GameState, action: str) -> GameState:
    """Handle playing a specific bird on a specific spot."""
    if not action.startswith("play_bird_"):
        raise ValueError(f"Unknown play bird action: {action}")

    bird_id, row, col = parse_play_bird_action(action)
    current_player = state.players[state.current_player_index]

    if row < 0 or row >= len(current_player.board):
        raise ValueError(f"Invalid row: {row}")
    if col < 0 or col >= len(current_player.board[row]):
        raise ValueError(f"Invalid col: {col}")

    target_spot = current_player.board[row][col]

    if target_spot.egg_cost and not state.action_data.get("egg_paid"):
        state.action_data.update(
            {
                "egg_cost": target_spot.egg_cost,
                "egg_paid": False,
                "callback": {"game_phase": state.game_phase, "action": action},
            }
        )
        state.game_phase = GamePhase.PAY_EGG_COST
        return state

    bird_to_play = next(
        (bird for bird in current_player.bird_hand if bird.id == bird_id), None
    )
    if not bird_to_play:
        raise ValueError(f"Bird {bird_id} not in hand")

    if bird_to_play.cost and not state.action_data.get("food_paid"):
        state.action_data.update(
            {
                "food_cost": bird_to_play.cost,
                "food_paid": False,
                "callback": {"game_phase": state.game_phase, "action": action},
            }
        )
        state.game_phase = GamePhase.PAY_FOOD_COST
        return state

    state = place_bird_effect(state, bird_id, row, col)

    state.action_data = {}

    return _finish_main_action(state, "white", spot=target_spot)


def _pay_egg_cost(state: GameState, action: str) -> GameState:
    """Handle egg cost payment and continue to next phase."""
    payment = parse_pay_eggs_action(action)
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

    state = pay_eggs_effect(state, payment)
    state.action_data["egg_paid"] = True

    if "callback" in state.action_data:
        callback = state.action_data["callback"]
        state.game_phase = callback["game_phase"]
        return transition_state(state, callback["action"])
    return state


def _pay_food_cost(state: GameState, action: str) -> GameState:
    """Handle food cost payment and continue to next phase."""
    payment = parse_pay_food_action(action)
    current_player = state.players[state.current_player_index]

    if not all(
        current_player.food.get(food, 0) >= amount for food, amount in payment.items()
    ):
        raise ValueError("Not enough food to pay food cost.")

    state = pay_food_effect(state, payment)
    state.action_data["food_paid"] = True

    if "callback" in state.action_data:
        callback = state.action_data["callback"]
        state.game_phase = callback["game_phase"]
        return transition_state(state, callback["action"])
    return state


_ACTION_HANDLERS = {
    GamePhase.GAME_SETUP: _route_game_setup,
    GamePhase.MAIN_TURN: _route_main_turn,
    GamePhase.EXTRA_FOOD_ACTION: _route_extra_food_action,
    GamePhase.EXTRA_LAY_EGGS_ACTION: _route_extra_lay_eggs_action,
    GamePhase.EXTRA_CARD_DRAW_ACTION: _route_extra_card_action,
    GamePhase.SELECT_INITIAL_CARDS: _select_initial_cards,
    GamePhase.DISCARD_FOOD: _discard_food,
    GamePhase.COLLECT_FOOD: _collect_food,
    GamePhase.LAY_EGGS: _lay_eggs,
    GamePhase.DRAW_CARDS: _draw_cards,
    GamePhase.PLAY_BIRD: _play_bird,
    GamePhase.SELECT_BIRD_TO_DISCARD: _discard_bird_for_food,
    GamePhase.SELECT_FOOD_TO_DISCARD: _discard_food_for_egg,
    GamePhase.SELECT_EGG_TO_DISCARD: _discard_egg_for_card,
    GamePhase.PAY_EGG_COST: _pay_egg_cost,
    GamePhase.PAY_FOOD_COST: _pay_food_cost,
    GamePhase.ACTIVATE_POWERS: _activate_powers,
    GamePhase.END_TURN: _handle_end_turn,
}
