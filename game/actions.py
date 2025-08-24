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
import json


def get_actions(state: GameState) -> List[str]:
    """Return list of available actions for current player."""
    match state.action_phase:
        case "game_setup":
            return _get_game_setup_actions(state)
        case "selecting_initial_cards":
            return _get_selecting_initial_cards_actions(state)
        case "discarding_food":
            return _get_discarding_food_actions(state)
        case "main_turn":
            return _get_main_turn_actions(state)
        case "collecting_food":
            return _get_food_collection_actions(state)
        case "laying_eggs":
            return _get_egg_laying_actions(state)
        case "drawing_cards":
            return _get_card_draw_actions(state)
        case "select_bird_to_discard":
            return _get_bird_discard_actions(state)
        case "select_food_to_discard":
            return _get_food_discard_actions(state)
        case "select_egg_to_discard":
            return _get_egg_discard_actions(state)
        case "play_bird":
            return _get_play_bird_actions(state)
        case "pay_egg_cost":
            return _get_pay_egg_cost_actions(state)
        case "pay_food_cost":
            return _get_pay_food_cost_actions(state)
        case "extra_food_action":
            return ["trade_bird", "skip_trade"]
        case "extra_lay_eggs_action":
            return ["trade_food", "skip_trade"]
        case "extra_card_draw_action":
            return ["trade_egg", "skip_trade"]
        case _:
            raise NotImplementedError


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
