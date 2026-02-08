from typing import Callable
import json

from .core import GameState, GamePhase
from .utils import (
    can_play_a_bird,
    generate_playable_bird_spots,
    get_egg_payment_combinations,
    generate_food_payments,
    get_egg_distribution_combinations,
    get_card_draw_combinations,
    get_initial_card_combinations,
    get_food_discard_combinations,
    get_available_bird_cards,
    get_collect_food_actions,
)
from .power import can_execute_power, get_power_choice_generator

_ACTION_GENERATORS: dict[GamePhase, Callable] = {}


def action_generator(phase: GamePhase):
    """Decorator to register an action generator."""

    def decorator(func):
        _ACTION_GENERATORS[phase] = func
        return func

    return decorator


_ACTION_GENERATORS[GamePhase.EXTRA_FOOD_ACTION] = lambda state: [
    "trade_bird",
    "skip_trade",
]
_ACTION_GENERATORS[GamePhase.EXTRA_LAY_EGGS_ACTION] = lambda state: [
    "trade_food",
    "skip_trade",
]
_ACTION_GENERATORS[GamePhase.EXTRA_CARD_DRAW_ACTION] = lambda state: [
    "trade_egg",
    "skip_trade",
]
_ACTION_GENERATORS[GamePhase.COLLECT_FOOD] = get_collect_food_actions
_ACTION_GENERATORS[GamePhase.GAME_OVER] = lambda state: []


def get_actions(state: GameState) -> list[str]:
    """Return list of available actions for current player."""
    generator = _ACTION_GENERATORS.get(state.game_phase)
    if not generator:
        raise NotImplementedError(f"No action generator for: {state.game_phase}")
    return generator(state)


@action_generator(GamePhase.GAME_SETUP)
def _get_game_setup_actions(state: GameState) -> list[str]:
    """Return setup actions."""
    current_player = state.players[state.current_player_index]

    if current_player.action_cubes == 9:
        return ["start_setup"]

    return ["end_setup"]


@action_generator(GamePhase.SELECT_INITIAL_CARDS)
def _get_select_initial_cards_actions(state: GameState) -> list[str]:
    """Return all valid bird and bonus card combinations for setup."""
    current_player = state.players[state.current_player_index]
    combinations = get_initial_card_combinations(
        list(current_player.bird_hand),
        list(current_player.bonus_hand),
    )
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.DISCARD_FOOD)
def _get_discard_food_actions(state: GameState) -> list[str]:
    """Return all valid food discard combinations."""
    amount_to_discard = state.action_data.amount_to_discard
    if not amount_to_discard:
        raise ValueError("No food to discard")

    current_player = state.players[state.current_player_index]
    combinations = get_food_discard_combinations(current_player.food, amount_to_discard)
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.MAIN_TURN)
def _get_main_turn_actions(state: GameState) -> list[str]:
    """Return the 4 main Wingspan actions available during a player's turn."""
    current_player = state.players[state.current_player_index]
    if not current_player.action_cubes:
        return []

    actions = []

    available_egg_capacity = any(
        spot.bird.state.eggs < spot.bird.card.egg_limit
        for row in current_player.board
        for spot in row
        if spot.bird is not None
    )

    if available_egg_capacity:
        actions.append("lay_eggs")

    if can_play_a_bird(current_player):
        actions.append("play_bird")

    actions.append("gain_food")

    total_available = get_available_bird_cards(state) + len(state.bird_tray)
    if total_available > 0:
        actions.append("draw_cards")

    return actions


@action_generator(GamePhase.END_TURN)
def _get_end_turn_actions(state: GameState) -> list[str]:
    """Get actions for end-of-turn phase."""
    execution = state.action_data.get_current_execution()

    if execution and execution.phase == "end_turn_discard":
        player_index = execution.player_index
        player = state.players[player_index]
        return [f"discard_card_{bird_id}" for bird_id in player.bird_hand]

    return []


@action_generator(GamePhase.LAY_EGGS)
def _get_lay_eggs_actions(state: GameState) -> list[str]:
    """Return possible lay egg actions."""
    eggs_needed = state.action_data.eggs_needed
    if not eggs_needed:
        raise ValueError("No eggs needed found.")

    current_player = state.players[state.current_player_index]
    birds_capacity = {
        spot.bird.id: spot.bird.card.egg_limit - spot.bird.state.eggs
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.state.eggs < spot.bird.card.egg_limit
    }
    combinations = get_egg_distribution_combinations(birds_capacity, eggs_needed)
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.DRAW_CARDS)
def _get_draw_cards_actions(state: GameState) -> list[str]:
    """Return possible card draw actions."""
    cards_needed = state.action_data.cards_needed
    if not cards_needed:
        raise ValueError("No cards needed found.")

    available_tray_bird_ids = list(state.bird_tray)
    deck_available = get_available_bird_cards(state)
    combinations = get_card_draw_combinations(
        cards_needed, available_tray_bird_ids, max_deck_cards=deck_available
    )
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.SELECT_BIRD_TO_DISCARD)
def _get_bird_discard_actions(state: GameState) -> list[str]:
    """Return birds that can be discarded for extra food."""
    current_player = state.players[state.current_player_index]
    return [f"discard_bird_{bird_id}" for bird_id in current_player.bird_hand]


@action_generator(GamePhase.SELECT_FOOD_TO_DISCARD)
def _get_food_discard_actions(state: GameState) -> list[str]:
    """Return foods that can be discarded for extra egg."""
    current_player = state.players[state.current_player_index]
    return [f"discard_food_{food}" for food in current_player.food]


@action_generator(GamePhase.SELECT_EGG_TO_DISCARD)
def _get_egg_discard_actions(state: GameState) -> list[str]:
    """Return eggs that can be discarded for extra card."""
    current_player = state.players[state.current_player_index]
    actions = []

    for row in current_player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.state.eggs > 0:
                actions.append(f"discard_egg_{spot.bird.id}")

    return actions


@action_generator(GamePhase.PLAY_BIRD)
def _get_play_bird_actions(state: GameState) -> list[str]:
    """Return birds that can be played with their target spots."""
    current_player = state.players[state.current_player_index]

    execution = state.action_data.get_current_execution()
    target_habitat = None
    if execution and execution.power_id == 12:
        target_habitat = execution.context.get("target_habitat")

    actions = []
    for bird_id, spot in generate_playable_bird_spots(current_player):
        if target_habitat:
            if spot.habitat == target_habitat:
                actions.append(f"play_bird_{bird_id}_at_{spot.row}_{spot.col}")
        else:
            actions.append(f"play_bird_{bird_id}_at_{spot.row}_{spot.col}")

    return actions


@action_generator(GamePhase.PAY_EGG_COST)
def _get_pay_egg_cost_actions(state: GameState) -> list[str]:
    """Return egg payment combinations."""
    pending = state.action_data.pending_cost
    if not pending or pending.cost_type != "egg":
        raise ValueError("No egg cost pending.")

    if not isinstance(pending.amount, int):
        raise ValueError(f"Egg cost must be int, got {type(pending.amount)}")

    egg_cost = pending.amount

    current_player = state.players[state.current_player_index]
    birds_with_eggs = {
        spot.bird.id: spot.bird.state.eggs
        for row in current_player.board
        for spot in row
        if spot.bird is not None and spot.bird.state.eggs > 0
    }
    combinations = get_egg_payment_combinations(birds_with_eggs, egg_cost)
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.PAY_FOOD_COST)
def _get_pay_food_cost_actions(state: GameState) -> list[str]:
    """Return food payment combinations."""
    pending = state.action_data.pending_cost
    if not pending or pending.cost_type != "food":
        raise ValueError("No food cost pending.")

    if not isinstance(pending.amount, list):
        raise ValueError(f"Food cost must be list, got {type(pending.amount)}")

    food_cost = pending.amount

    current_player = state.players[state.current_player_index]
    combinations = generate_food_payments(food_cost, current_player.food)
    return [json.dumps(comb) for comb in combinations]


@action_generator(GamePhase.ACTIVATE_POWERS)
def _get_activate_powers_actions(state: GameState) -> list[str]:
    """Return power activation options."""
    stack = state.action_data.execution_stack

    if not stack:
        queued = state.action_data.get_current_queued_power()
        if not queued:
            raise ValueError("No power in queue")

        actions = ["skip_power"]

        player = state.players[queued.player_index]
        spot = player.board[queued.spot_row][queued.spot_col]
        power_entry = {
            "power_data": queued.power_data,
            "spot": spot,
            "bird_id": queued.bird_id,
            "player_index": queued.player_index,
        }

        if can_execute_power(state, power_entry):
            actions.append("activate_power")

        return actions

    current = stack[-1]
    if current.phase is None:
        raise ValueError(
            f"Power {current.power_id} execution has no phase set. "
            "Power handler must set a phase before requesting user choices."
        )

    choice_generator = get_power_choice_generator(current.power_id, current.phase)

    if choice_generator:
        return choice_generator(state, current)

    raise ValueError(
        f"No choice generator for power {current.power_id} phase {current.phase}"
    )
