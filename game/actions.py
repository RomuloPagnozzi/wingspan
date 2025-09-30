from typing import List
from .data import GameState
from .utils import (
    can_play_a_bird,
    generate_playable_bird_spots,
    get_egg_payment_combinations,
    generate_food_payments,
    get_egg_distribution_combinations,
    get_card_draw_combinations,
    get_initial_card_combinations,
    get_food_discard_combinations,
)
from .powers import can_execute_power, get_power_choices
import json


def get_actions(state: GameState) -> List[str]:
    """Return list of available actions for current player."""
    generator = _ACTION_GENERATORS.get(state.action_phase)
    if not generator:
        raise NotImplementedError(f"No action generator for: {state.action_phase}")
    return generator(state)


def _get_game_setup_actions(state: GameState) -> List[str]:
    """Return setup actions."""
    current_player = state.players[state.current_player_index]

    if current_player.action_cubes == 9:
        return ["start_setup"]

    return ["end_setup"]


def _get_selecting_initial_cards_actions(state: GameState) -> List[str]:
    """Return all valid bird and bonus card combinations for setup."""
    current_player = state.players[state.current_player_index]
    combinations = get_initial_card_combinations(
        [bird.id for bird in current_player.bird_hand],
        [bonus.id for bonus in current_player.bonus_hand],
    )
    return [json.dumps(comb) for comb in combinations]


def _get_discarding_food_actions(state: GameState) -> List[str]:
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


def _get_food_collection_actions(state: GameState) -> List[str]:
    """Return possible foods to collect."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")

    if len(set(tuple(sorted(die_face)) for die_face in state.feeder.values())) == 1:
        actions.append("reroll_all")

    return actions


def _get_egg_laying_actions(state: GameState) -> List[str]:
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


def _get_card_draw_actions(state: GameState) -> List[str]:
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
    return [
        f"play_bird_{bird.id}_at_{spot.row}_{spot.col}"
        for bird, spot in generate_playable_bird_spots(current_player)
    ]


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


def _get_power_activation_actions(state: GameState) -> List[str]:
    """Return power activation options."""
    powers_queue = state.action_data.get("powers_queue")
    current_power_index = state.action_data.get("current_power_index")

    if not powers_queue or current_power_index is None:
        raise ValueError("No power queue or index found in action_data")

    if current_power_index >= len(powers_queue):
        raise ValueError("Power index out of range")

    current_power = powers_queue[current_power_index]
    actions = []

    if not state.action_data.get("choice_powers"):
        actions.append("skip_power")

    if can_execute_power(state, current_power["power_data"]):
        choices = get_power_choices(state, current_power["power_data"])

        if choices:
            actions.extend([f"activate_{choice}" for choice in choices])
        else:
            actions.append("activate_power")

    return actions


_ACTION_GENERATORS = {
    "game_setup": _get_game_setup_actions,
    "selecting_initial_cards": _get_selecting_initial_cards_actions,
    "discarding_food": _get_discarding_food_actions,
    "main_turn": _get_main_turn_actions,
    "collecting_food": _get_food_collection_actions,
    "laying_eggs": _get_egg_laying_actions,
    "drawing_cards": _get_card_draw_actions,
    "select_bird_to_discard": _get_bird_discard_actions,
    "select_food_to_discard": _get_food_discard_actions,
    "select_egg_to_discard": _get_egg_discard_actions,
    "play_bird": _get_play_bird_actions,
    "pay_egg_cost": _get_pay_egg_cost_actions,
    "pay_food_cost": _get_pay_food_cost_actions,
    "activating_powers": _get_power_activation_actions,
    "extra_food_action": lambda state: ["trade_bird", "skip_trade"],
    "extra_lay_eggs_action": lambda state: ["trade_food", "skip_trade"],
    "extra_card_draw_action": lambda state: ["trade_egg", "skip_trade"],
}
