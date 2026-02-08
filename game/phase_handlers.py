import json
from typing import Callable

from .core import (
    GameState,
    GamePhase,
    PinkTrigger,
    CostPayment,
    roll_feeder,
    get_bird_card,
)
from .utils import (
    find_leftmost_empty_spot,
    get_current_player_index,
)
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
)
from .engine import finish_main_action, activate_powers, handle_end_turn

PhaseHandler = Callable[[GameState, str], GameState]
_PHASE_HANDLERS: dict[GamePhase, PhaseHandler] = {}


def phase_handler(phase: GamePhase):
    """Decorator to register a phase handler."""

    def decorator(func: PhaseHandler) -> PhaseHandler:
        _PHASE_HANDLERS[phase] = func
        return func

    return decorator


def get_phase_handler(phase: GamePhase) -> PhaseHandler | None:
    """Get the handler for a specific game phase."""
    return _PHASE_HANDLERS.get(phase)


_PHASE_HANDLERS[GamePhase.ACTIVATE_POWERS] = activate_powers
_PHASE_HANDLERS[GamePhase.END_TURN] = handle_end_turn


@phase_handler(GamePhase.GAME_SETUP)
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


@phase_handler(GamePhase.SELECT_INITIAL_CARDS)
def _select_initial_cards(state: GameState, action: str) -> GameState:
    """Handle initial card selection during setup."""
    selection = json.loads(action)

    current_player = state.players[state.current_player_index]
    current_player.bird_hand = [
        bird_id
        for bird_id in current_player.bird_hand
        if bird_id in selection["kept_birds"]
    ]
    current_player.bonus_hand = [
        bonus_id
        for bonus_id in current_player.bonus_hand
        if bonus_id == selection["kept_bonus"]
    ]

    bird_amount = len(selection["kept_birds"])
    if bird_amount:
        state.action_data.amount_to_discard = bird_amount
        state.game_phase = GamePhase.DISCARD_FOOD
    else:
        current_player.action_cubes = 8
        state.game_phase = GamePhase.GAME_SETUP
        state.current_player_index = get_current_player_index(state)
    return state


@phase_handler(GamePhase.DISCARD_FOOD)
def _discard_food(state: GameState, action: str) -> GameState:
    """Handle food discarding during setup."""
    discard = json.loads(action)

    current_player = state.players[state.current_player_index]
    for food_type, amount in discard.items():
        if current_player.food.get(food_type, 0) < amount:
            raise ValueError(f"""Not enough {food_type} to discard {amount}
                (there's {current_player.food.get(food_type, 0)})""")

    pay_food_effect(state, discard)

    current_player.action_cubes = 8
    state.action_data.clear()
    state.game_phase = GamePhase.GAME_SETUP
    state.current_player_index = get_current_player_index(state)
    return state


@phase_handler(GamePhase.MAIN_TURN)
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
                state.action_data.base_amount = base_amount
            else:
                state.game_phase = GamePhase.COLLECT_FOOD
                state.action_data.food_needed = base_amount
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
                state.action_data.base_amount = base_amount
            else:
                state.game_phase = GamePhase.LAY_EGGS
                state.action_data.eggs_needed = base_amount
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
                sum(bird.state.eggs for bird in played_birds) if played_birds else 0
            )
            can_trade = available_eggs and (
                not wetland_spot or wetland_spot.extra_resource
            )

            if can_trade:
                state.game_phase = GamePhase.EXTRA_CARD_DRAW_ACTION
                state.action_data.base_amount = base_amount
            else:
                state.game_phase = GamePhase.DRAW_CARDS
                state.action_data.cards_needed = base_amount
            return state

        case _:
            raise ValueError(f"Invalid action: {action}")


@phase_handler(GamePhase.COLLECT_FOOD)
def _collect_food(state: GameState, action: str) -> GameState:
    """Handle dice selection."""

    if action.startswith("select_die_"):
        die_index, food_type = parse_select_die_action(action)

        select_die_effect(state, die_index, food_type)
        state.action_data.food_needed -= 1

        if food_type == "rodent":
            state.action_data.gained_rodent = True

        if not state.action_data.food_needed:
            pink_trigger = None
            pink_context = None
            if state.action_data.gained_rodent:
                pink_trigger = PinkTrigger.GAIN_FOOD
                pink_context = {"food_type": "rodent"}
            return finish_main_action(
                state,
                "brown",
                habitat="forest",
                pink_trigger=pink_trigger,
                pink_context=pink_context,
            )

        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder(state.rng)
        return state

    raise ValueError(f"No known action{action}")


@phase_handler(GamePhase.LAY_EGGS)
def _lay_eggs(state: GameState, action: str) -> GameState:
    """Handle laying eggs."""
    egg_distribution = parse_lay_eggs_action(action)

    lay_eggs_effect(state, egg_distribution)

    return finish_main_action(
        state,
        "brown",
        habitat="grassland",
        pink_trigger=PinkTrigger.LAY_EGGS,
    )


@phase_handler(GamePhase.DRAW_CARDS)
def _draw_cards(state: GameState, action: str) -> GameState:
    """Handle drawing cards"""
    tray_birds, deck_count = parse_draw_cards_action(action)

    draw_cards_effect(state, tray_birds, deck_count)

    return finish_main_action(state, "brown", habitat="wetland")


@phase_handler(GamePhase.EXTRA_FOOD_ACTION)
def _route_extra_food_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading bird for extra food"""
    base_amount = state.action_data.base_amount

    match action:
        case "trade_bird":
            state.game_phase = GamePhase.SELECT_BIRD_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.COLLECT_FOOD
            state.action_data.food_needed = base_amount
            return state
        case _:
            raise ValueError(f"Unknown extra food action: {action}")


@phase_handler(GamePhase.EXTRA_LAY_EGGS_ACTION)
def _route_extra_lay_eggs_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading food token for extra egg."""
    base_amount = state.action_data.base_amount

    match action:
        case "trade_food":
            state.game_phase = GamePhase.SELECT_FOOD_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.LAY_EGGS
            state.action_data.eggs_needed = base_amount
            return state
        case _:
            raise ValueError(f"Unknown extra lay eggs action: {action}")


@phase_handler(GamePhase.EXTRA_CARD_DRAW_ACTION)
def _route_extra_card_action(state: GameState, action: str) -> GameState:
    """Handle player's choice about trading egg for extra card."""
    base_amount = state.action_data.base_amount

    match action:
        case "trade_egg":
            state.game_phase = GamePhase.SELECT_EGG_TO_DISCARD
            return state
        case "skip_trade":
            state.game_phase = GamePhase.DRAW_CARDS
            state.action_data.cards_needed = base_amount
            return state
        case _:
            raise ValueError(f"Unknown extra card action: {action}")


@phase_handler(GamePhase.SELECT_BIRD_TO_DISCARD)
def _discard_bird_for_food(state: GameState, action: str) -> GameState:
    """Handle discarding a bird for extra food."""
    if action.startswith("discard_bird_"):
        bird_id = int(action.split("_")[2])

        discard_bird_from_hand_effect(state, bird_id)

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.COLLECT_FOOD
        state.action_data.food_needed = base_amount + 1

        return state

    raise ValueError(f"Unknown bird discard action: {action}")


@phase_handler(GamePhase.SELECT_FOOD_TO_DISCARD)
def _discard_food_for_egg(state: GameState, action: str) -> GameState:
    """Handle discarding a food token for extra eggs."""
    if action.startswith("discard_food_"):
        food_key = action.split("_")[2]
        current_player = state.players[state.current_player_index]

        if current_player.food.get(food_key, 0) <= 0:
            raise ValueError(
                f"Food {food_key} not in player's food stash {current_player.food}"
            )

        pay_food_effect(state, {food_key: 1})

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.LAY_EGGS
        state.action_data.eggs_needed = base_amount + 1

        return state

    raise ValueError(f"Unknown food discard action: {action}")


@phase_handler(GamePhase.SELECT_EGG_TO_DISCARD)
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
                    and spot.bird.state.eggs > 0
                ):
                    bird_with_egg = spot.bird
                    break
            if bird_with_egg:
                break

        if not bird_with_egg:
            raise ValueError(f"Bird {bird_id} not found on board or has no eggs")

        pay_eggs_effect(state, {bird_id: 1})

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.DRAW_CARDS
        state.action_data.cards_needed = base_amount + 1

        return state

    raise ValueError(f"Unknown egg discard action: {action}")


@phase_handler(GamePhase.PLAY_BIRD)
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

    if target_spot.egg_cost and not (
        state.action_data.pending_cost
        and state.action_data.pending_cost.cost_type == "egg_paid"
    ):
        state.action_data.pending_cost = CostPayment(
            cost_type="egg",
            amount=target_spot.egg_cost,
            callback_phase=state.game_phase,
            callback_action=action,
        )
        state.game_phase = GamePhase.PAY_EGG_COST
        return state

    if bird_id not in current_player.bird_hand:
        raise ValueError(f"Bird {bird_id} not in hand")

    bird_card = get_bird_card(bird_id)
    if bird_card is None:
        raise ValueError(f"Bird card {bird_id} not found in registry")

    bird_cost = [dict(option) for option in bird_card.cost] if bird_card.cost else []

    if bird_cost and not (
        state.action_data.pending_cost
        and state.action_data.pending_cost.cost_type == "food_paid"
    ):
        if (
            state.action_data.pending_cost
            and state.action_data.pending_cost.cost_type in ["egg", "egg_paid"]
        ):
            pass
        else:
            state.action_data.pending_cost = CostPayment(
                cost_type="food",
                amount=bird_cost,
                callback_phase=state.game_phase,
                callback_action=action,
            )
            state.game_phase = GamePhase.PAY_FOOD_COST
            return state

    place_bird_effect(state, bird_id, row, col)

    execution = state.action_data.get_current_execution()
    if execution and execution.power_id == 12:
        state.action_data.execution_stack.pop()
        state.game_phase = GamePhase.ACTIVATE_POWERS
        return finish_main_action(
            state,
            "white",
            spot=target_spot,
            skip_action_cube=True,
            pink_trigger=PinkTrigger.BIRD_PLAYED,
            pink_context={"habitat": target_spot.habitat},
        )

    state.action_data.pending_cost = None
    return finish_main_action(
        state,
        "white",
        spot=target_spot,
        pink_trigger=PinkTrigger.BIRD_PLAYED,
        pink_context={"habitat": target_spot.habitat},
    )


@phase_handler(GamePhase.PAY_EGG_COST)
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
    bird_eggs = {bird.id: bird.state.eggs for bird in relevant_board_birds}

    if payment.keys() != bird_eggs.keys():
        raise ValueError(
            f"Birds from board {bird_eggs.keys()} and payment {payment.keys()} do not match."
        )

    if not all(bird_eggs[k] >= payment[k] for k in payment):
        raise ValueError("Not enough eggs in birds to pay egg cost.")

    pay_eggs_effect(state, payment)

    pending = state.action_data.pending_cost
    if pending:
        callback_phase = pending.callback_phase
        callback_action = pending.callback_action
        state.action_data.pending_cost = CostPayment(
            cost_type="egg_paid",
            amount=0,
            callback_phase=callback_phase,
            callback_action=callback_action,
        )
        state.game_phase = callback_phase
        state.action_data.pending_callback = (callback_phase, callback_action)

    return state


@phase_handler(GamePhase.PAY_FOOD_COST)
def _pay_food_cost(state: GameState, action: str) -> GameState:
    """Handle food cost payment and continue to next phase."""
    payment = parse_pay_food_action(action)
    current_player = state.players[state.current_player_index]

    if not all(
        current_player.food.get(food, 0) >= amount for food, amount in payment.items()
    ):
        raise ValueError("Not enough food to pay food cost.")

    pay_food_effect(state, payment)

    pending = state.action_data.pending_cost
    if pending:
        callback_phase = pending.callback_phase
        callback_action = pending.callback_action
        state.action_data.pending_cost = CostPayment(
            cost_type="food_paid",
            amount=0,
            callback_phase=callback_phase,
            callback_action=callback_action,
        )
        state.game_phase = callback_phase
        state.action_data.pending_callback = (callback_phase, callback_action)

    return state
