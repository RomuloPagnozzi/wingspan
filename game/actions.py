from typing import List, Dict
from .data import GameState, GamePhase
from .utils import (
    can_play_a_bird,
    generate_playable_bird_spots,
    get_egg_payment_combinations,
    generate_food_payments,
    get_egg_distribution_combinations,
    get_card_draw_combinations,
    get_initial_card_combinations,
    get_food_discard_combinations,
    get_valid_birds_for_eggs,
    get_food_gain_combinations,
)
from .powers import can_execute_power
import json


def get_actions(state: GameState) -> List[str]:
    """Return list of available actions for current player."""
    generator = _ACTION_GENERATORS.get(state.game_phase)
    if not generator:
        raise NotImplementedError(f"No action generator for: {state.game_phase}")
    return generator(state)


def _get_game_setup_actions(state: GameState) -> List[str]:
    """Return setup actions."""
    current_player = state.players[state.current_player_index]

    if current_player.action_cubes == 9:
        return ["start_setup"]

    return ["end_setup"]


def _get_select_initial_cards_actions(state: GameState) -> List[str]:
    """Return all valid bird and bonus card combinations for setup."""
    current_player = state.players[state.current_player_index]
    combinations = get_initial_card_combinations(
        [bird.id for bird in current_player.bird_hand],
        [bonus.id for bonus in current_player.bonus_hand],
    )
    return [json.dumps(comb) for comb in combinations]


def _get_discard_food_actions(state: GameState) -> List[str]:
    """Return all valid food discard combinations."""
    amount_to_discard = state.action_data.get("amount_to_discard")
    if not amount_to_discard:
        raise ValueError(f"No food to discard")

    current_player = state.players[state.current_player_index]
    combinations = get_food_discard_combinations(current_player.food, amount_to_discard)
    return [json.dumps(comb) for comb in combinations]


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


def _get_end_turn_actions(state: GameState) -> List[str]:
    """Get actions for end-of-turn phase."""
    effects = state.action_data.get("end_turn_effects", [])
    if not effects:
        return []

    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "end_turn_discard_card":
        current_effect = effects[0]
        player_index = current_effect["player_index"]
        player = state.players[player_index]
        return [f"discard_card_{card.id}" for card in player.bird_hand]

    return []


def _get_collect_food_actions(state: GameState) -> List[str]:
    """Return possible foods to collect."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")

    if len(set(tuple(sorted(die_face)) for die_face in state.feeder.values())) == 1:
        actions.append("reroll_all")

    return actions


def _get_lay_eggs_actions(state: GameState) -> List[str]:
    """Return possible lay egg actions."""
    eggs_needed = state.action_data.get("eggs_needed")
    if not eggs_needed:
        raise ValueError(f"No eggs needed found in {state.action_data}.")

    current_player = state.players[state.current_player_index]
    birds_capacity = {
        spot.bird.id: spot.bird.egg_limit - spot.bird.eggs
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.eggs < spot.bird.egg_limit
    }
    combinations = get_egg_distribution_combinations(birds_capacity, eggs_needed)
    return [json.dumps(comb) for comb in combinations]


def _get_draw_cards_actions(state: GameState) -> List[str]:
    """Return possible card draw actions."""
    cards_needed = state.action_data.get("cards_needed")
    if not cards_needed:
        raise ValueError(f"No cards needed found in {state.action_data}.")

    available_tray_bird_ids = [bird.id for bird in state.bird_tray]
    combinations = get_card_draw_combinations(cards_needed, available_tray_bird_ids)
    return [json.dumps(comb) for comb in combinations]


def _get_bird_discard_actions(state: GameState) -> List[str]:
    """Return birds that can be discarded for extra food."""
    current_player = state.players[state.current_player_index]
    return [f"discard_bird_{bird.id}" for bird in current_player.bird_hand]


def _get_food_discard_actions(state: GameState) -> List[str]:
    """Return foods that can be discarded for extra egg."""
    current_player = state.players[state.current_player_index]
    return [f"discard_food_{food}" for food in current_player.food]


def _get_egg_discard_actions(state: GameState) -> List[str]:
    """Return eggs that can be discarded for extra card."""
    current_player = state.players[state.current_player_index]
    actions = []

    for row in current_player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.eggs > 0:
                actions.append(f"discard_egg_{spot.bird.id}")

    return actions


def _get_play_bird_actions(state: GameState) -> List[str]:
    """Return birds that can be played with their target spots."""
    current_player = state.players[state.current_player_index]

    target_habitat = state.action_data.get("power_12_target_habitat")

    actions = []
    for bird, spot in generate_playable_bird_spots(current_player):
        if target_habitat:
            if spot.habitat == target_habitat:
                actions.append(f"play_bird_{bird.id}_at_{spot.row}_{spot.col}")
        else:
            actions.append(f"play_bird_{bird.id}_at_{spot.row}_{spot.col}")

    return actions


def _get_pay_egg_cost_actions(state: GameState) -> List[str]:
    """Return egg payment combinations."""
    egg_cost = state.action_data.get("egg_cost")
    if not egg_cost:
        raise ValueError(f"No egg cost found in {state.action_data}.")

    current_player = state.players[state.current_player_index]
    birds_with_eggs = {
        spot.bird.id: spot.bird.eggs
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.eggs > 0
    }
    combinations = get_egg_payment_combinations(birds_with_eggs, egg_cost)
    return [json.dumps(comb) for comb in combinations]


def _get_pay_food_cost_actions(state: GameState) -> List[str]:
    """Return food payment combinations."""
    food_cost = state.action_data.get("food_cost")
    if not food_cost:
        raise ValueError(f"No food cost found in {state.action_data}.")

    current_player = state.players[state.current_player_index]
    combinations = generate_food_payments(food_cost, current_player.food)
    return [json.dumps(comb) for comb in combinations]


def _get_activate_powers_actions(state: GameState) -> List[str]:
    """Return power activation options."""
    powers_queue = state.action_data.get("powers_queue")
    current_power_index = state.action_data.get("current_power_index")

    if not powers_queue or current_power_index is None:
        raise ValueError("No power queue or index found in action_data")

    if current_power_index >= len(powers_queue):
        raise ValueError("Power index out of range")

    current_power = powers_queue[current_power_index]
    power_data = current_power["power_data"]

    if state.action_data.get("sub_phase"):
        return _get_power_choices(state, power_data)

    actions = ["skip_power"]

    if can_execute_power(state, current_power):
        actions.append("activate_power")

    return actions


def _get_power_choices(state: GameState, power_data: Dict) -> List[str]:
    """Get available choices for a power that requires player selection."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        raise ValueError("Corrupted power data")

    power_id = power_data["data"]["id"]
    choice_generator = POWER_CHOICE_GENERATORS.get(power_id)

    if not choice_generator:
        raise NotImplementedError

    return choice_generator(state)


def _get_power_2_choices(state: GameState) -> List[str]:
    """Generate egg distribution choices for power 2."""
    nest_type = state.action_data["nest_type"]
    activator = state.action_data["activator"]
    player = state.players[state.current_player_index]
    amount = 2 if state.current_player_index == activator else 1

    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    birds_capacity = {b.id: b.egg_limit - b.eggs for b in valid_birds}
    combos = get_egg_distribution_combinations(birds_capacity, amount)
    return [f"activate_{json.dumps(c)}" for c in combos]


def _get_power_4_choices(state: GameState) -> List[str]:
    """Route to appropriate Power 4 choice generator based on sub-phase."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_4_select_discard":
        return _get_power_4_discard_choices(state)
    elif sub_phase == "power_4_select_gain":
        return _get_power_4_gain_choices(state)

    return []


def _get_power_4_discard_choices(state: GameState) -> List[str]:
    """Generate discard choices for power 4."""
    discard_type = state.action_data["power_4_discard_type"]
    gain_type = state.action_data["power_4_gain_type"]
    activating_bird_id = state.action_data.get("power_4_activating_bird_id")
    current_player = state.players[state.current_player_index]

    if discard_type == "egg":
        actions = []
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.eggs > 0:
                    if gain_type == "wild" and spot.bird.id == activating_bird_id:
                        continue
                    actions.append(f"discard_egg_from_{spot.bird.id}")
        return actions
    else:
        return [f"discard_food_{discard_type}"]


def _get_power_4_gain_choices(state: GameState) -> List[str]:
    """Generate resource gain choices for power 4 (wild resource)."""
    gain_qty = state.action_data["power_4_gain_qty"]
    combos = get_food_gain_combinations(gain_qty)
    return [f"gain_{json.dumps(combo)}" for combo in combos]


def _get_power_5_choices(state: GameState) -> List[str]:
    """Get choices for power 5 (currently for bonus card selection)."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_5_select_bonus":
        drawn_cards = state.action_data.get("power_5_bonus_options", [])
        return [f"power_5_bonus_{card.id}" for card in drawn_cards]

    return []


def _get_power_6_choices(state: GameState) -> List[str]:
    """Generate card selection choices for power 6."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_6_select_card":
        available_cards = state.action_data.get("power_6_available_cards", [])
        return [f"select_card_{card.id}" for card in available_cards]

    return []


def _get_power_7_choices(state: GameState) -> List[str]:
    """Route to appropriate Power 7 choice generator based on sub-phase."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_7_choose_starting_player":
        return _get_power_7_starting_player_choices(state)
    elif sub_phase == "power_7_select_die":
        return _get_collect_food_actions(state)

    return []


def _get_power_7_starting_player_choices(state: GameState) -> List[str]:
    """Generate player selection actions for Power 7."""
    num_players = len(state.players)
    return [f"choose_player_{i}" for i in range(num_players)]


def _get_power_8_choices(state: GameState) -> List[str]:
    """Route to appropriate Power 8 choice generator based on sub-phase."""
    sub_phase = state.action_data.get("sub_phase")

    if sub_phase == "power_8_select_food_type":
        return _get_power_8_food_type_choices(state)
    elif sub_phase == "power_8_select_die":
        return _get_power_8_die_choices(state)
    elif sub_phase == "power_8_choose_cache":
        return ["cache_food", "supply_food"]

    return []


def _get_power_8_food_type_choices(state: GameState) -> List[str]:
    """Generate food type choices from available feeder foods."""
    available_foods = state.action_data.get("power_8_food_types", [])
    return [f"select_food_type_{food}" for food in available_foods]


def _get_power_8_die_choices(state: GameState) -> List[str]:
    """Generate die choices for selected food type."""
    food_type = state.action_data["power_8_food_type"]
    all_actions = _get_collect_food_actions(state)

    filtered_actions = []
    for action in all_actions:
        if action == "reroll_all":
            filtered_actions.append(action)
        elif action.endswith(f"_{food_type}"):
            filtered_actions.append(action)

    return filtered_actions


def _get_power_9_choices(state: GameState) -> List[str]:
    """Generate habitat selection actions for Power 9."""
    valid_habitats = state.action_data.get("power_9_valid_habitats", [])
    return [f"select_habitat_{habitat}" for habitat in valid_habitats]


def _get_power_10_choices(state: GameState) -> List[str]:
    """Generate bird selection actions for Power 10 (type: 'any')."""
    valid_bird_ids = state.action_data.get("power_10_valid_bird_ids", [])
    return [f"select_bird_{bird_id}" for bird_id in valid_bird_ids]


def _get_power_13_choices(state: GameState) -> List[str]:
    """Generate die selection actions for Power 13."""
    return _get_collect_food_actions(state)


def _get_power_14_choices(state: GameState) -> List[str]:
    """Generate bird selection actions for Power 14 (repeat power)."""
    eligible_birds = state.action_data.get("power_14_eligible_birds", [])
    return [f"select_bird_{bird['bird_id']}" for bird in eligible_birds]


def _get_power_16_choices(state: GameState) -> List[str]:
    """Generate trade actions for Power 16 (trade food for another type)."""
    all_food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    current_player = state.players[state.current_player_index]
    player_food_types = list(current_player.food.keys())
    actions = []
    for from_type in player_food_types:
        for to_type in all_food_types:
            if to_type != from_type:
                actions.append(f"trade_{from_type}_for_{to_type}")
    return actions


def _get_power_17_choices(state: GameState) -> List[str]:
    """Generate choices for Power 17 (tuck card for bonus)."""
    sub_phase = state.action_data.get("sub_phase")
    current_player = state.players[state.current_player_index]

    if sub_phase == "power_17_select_card":
        return [f"tuck_card_{card.id}" for card in current_player.bird_hand]
    elif sub_phase == "power_17_select_food":
        food_types = state.action_data.get("power_17_food_types", [])
        return [f"select_food_{food}" for food in food_types]

    return []


POWER_CHOICE_GENERATORS = {
    2: _get_power_2_choices,
    4: _get_power_4_choices,
    5: _get_power_5_choices,
    6: _get_power_6_choices,
    7: _get_power_7_choices,
    8: _get_power_8_choices,
    9: _get_power_9_choices,
    10: _get_power_10_choices,
    13: _get_power_13_choices,
    14: _get_power_14_choices,
    16: _get_power_16_choices,
    17: _get_power_17_choices,
}


_ACTION_GENERATORS = {
    GamePhase.GAME_SETUP: _get_game_setup_actions,
    GamePhase.MAIN_TURN: _get_main_turn_actions,
    GamePhase.EXTRA_FOOD_ACTION: lambda state: ["trade_bird", "skip_trade"],
    GamePhase.EXTRA_LAY_EGGS_ACTION: lambda state: ["trade_food", "skip_trade"],
    GamePhase.EXTRA_CARD_DRAW_ACTION: lambda state: ["trade_egg", "skip_trade"],
    GamePhase.SELECT_INITIAL_CARDS: _get_select_initial_cards_actions,
    GamePhase.DISCARD_FOOD: _get_discard_food_actions,
    GamePhase.COLLECT_FOOD: _get_collect_food_actions,
    GamePhase.LAY_EGGS: _get_lay_eggs_actions,
    GamePhase.DRAW_CARDS: _get_draw_cards_actions,
    GamePhase.PLAY_BIRD: _get_play_bird_actions,
    GamePhase.SELECT_BIRD_TO_DISCARD: _get_bird_discard_actions,
    GamePhase.SELECT_FOOD_TO_DISCARD: _get_food_discard_actions,
    GamePhase.SELECT_EGG_TO_DISCARD: _get_egg_discard_actions,
    GamePhase.PAY_EGG_COST: _get_pay_egg_cost_actions,
    GamePhase.PAY_FOOD_COST: _get_pay_food_cost_actions,
    GamePhase.ACTIVATE_POWERS: _get_activate_powers_actions,
    GamePhase.END_TURN: _get_end_turn_actions,
}
