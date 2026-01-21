import copy
from .data import (
    GameState,
    GamePhase,
    Spot,
    PinkTrigger,
    QueuedPower,
    PowerExecution,
    CostPayment,
    roll_feeder,
    update_player_scores,
    update_round_goal_scores,
)
from .utils import (
    find_leftmost_empty_spot,
    get_current_player_index,
    get_triggered_powers,
    get_triggered_pink_powers,
    check_round_end,
    get_action_cubes_for_round,
    rotate_first_player,
    restock_bird_tray,
    refresh_bird_tray,
    get_first_player_index,
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
)
from .power_handlers import get_handler


# =============================================================================
# Flow control helpers
# =============================================================================


def _finish_main_action(
    state: GameState,
    color: str,
    habitat: str | None = None,
    spot: Spot | None = None,
    skip_action_cube: bool = False,
    pink_trigger: PinkTrigger | None = None,
    pink_context: dict | None = None,
) -> GameState:
    """Complete a main action: consume cube, check powers, transition."""
    current_player = state.players[state.current_player_index]
    if not skip_action_cube:
        current_player.action_cubes -= 1

    pink_powers = []
    if pink_trigger is not None:
        pink_powers = get_triggered_pink_powers(
            state, pink_trigger, state.current_player_index, pink_context
        )

    triggered_powers = get_triggered_powers(
        current_player, color, habitat=habitat, spot=spot
    )
    for power in triggered_powers:
        power["player_index"] = state.current_player_index

    all_powers = pink_powers + triggered_powers

    if all_powers:
        state.game_phase = GamePhase.ACTIVATE_POWERS
        state.action_data.powers_queue = [
            QueuedPower(
                power_id=p["power_data"]["data"]["id"],
                bird_id=p["bird_id"],
                spot_row=p["spot"].row,
                spot_col=p["spot"].col,
                player_index=p["player_index"],
                power_data=p["power_data"],
            )
            for p in all_powers
        ]
        state.action_data.current_power_index = 0
        state.action_data.action_player_index = state.current_player_index
        return state

    return _finalize_turn(state)


# =============================================================================
# Power execution (new stack-based approach)
# =============================================================================


def _activate_powers(state: GameState, action: str) -> GameState:
    """Handle power activation using stack-based execution."""
    stack = state.action_data.execution_stack

    # If stack is empty, we're deciding on a queued power
    if not stack:
        if action == "skip_power":
            state.action_data.current_power_index += 1
            return _check_powers_done(state)

        if action == "activate_power":
            # Start executing the current queued power
            queued = state.action_data.get_current_queued_power()
            if not queued:
                raise ValueError("No power to activate")

            # Mark pink power as used if applicable
            if queued.power_data.get("color") == "pink":
                player = state.players[queued.player_index]
                player.used_pink_powers.add(queued.bird_id)

            # Push onto execution stack
            execution = PowerExecution(
                power_id=queued.power_id,
                bird_id=queued.bird_id,
                spot_row=queued.spot_row,
                spot_col=queued.spot_col,
                player_index=queued.player_index,
                phase=None,
                context={"power_data": queued.power_data},
            )
            stack.append(execution)

            # Get and call the initial handler
            handler = get_handler(queued.power_id, None)
            if not handler:
                raise ValueError(f"No handler for power {queued.power_id}")

            state = handler(state, stack, action)

            # Check if power completed immediately
            if not stack:
                state.action_data.current_power_index += 1
                return _check_powers_done(state)

            return state

        raise ValueError(f"Unknown action with empty stack: {action}")

    # Stack is not empty - route to current execution's handler
    current = stack[-1]
    handler = get_handler(current.power_id, current.phase)

    if not handler:
        raise ValueError(
            f"No handler for power {current.power_id} phase {current.phase}"
        )

    state = handler(state, stack, action)

    # Check if power completed
    if not stack:
        state.action_data.current_power_index += 1
        return _check_powers_done(state)

    # Check if a new power was pushed with phase=None (needs initial handler call)
    # This happens when Power 14 pushes a nested power
    while stack and stack[-1].phase is None:
        new_power = stack[-1]
        initial_handler = get_handler(new_power.power_id, None)
        if not initial_handler:
            raise ValueError(f"No handler for power {new_power.power_id}")
        state = initial_handler(state, stack, "")
        # If it completed immediately, check again
        if not stack:
            state.action_data.current_power_index += 1
            return _check_powers_done(state)

    return state


def _check_powers_done(state: GameState) -> GameState:
    """Check if all powers processed, transition to end turn if so."""
    queue = state.action_data.powers_queue
    current_index = state.action_data.current_power_index

    if current_index >= len(queue):
        state.game_phase = GamePhase.END_TURN
        return _handle_end_turn(state, "")

    next_power = queue[current_index]
    state.current_player_index = next_power.player_index

    return state


def _finalize_turn(state: GameState) -> GameState:
    """Finalize turn: check for round end or advance to next player."""
    current_player = state.players[state.current_player_index]
    update_player_scores(current_player)

    if check_round_end(state):
        update_round_goal_scores(state)
        restock_bird_tray(state)
        rotate_first_player(state)

        next_round = state.round + 1
        if next_round > 4:
            state.game_phase = GamePhase.GAME_OVER
            state.action_data.clear()
            return state

        cubes = get_action_cubes_for_round(next_round)
        for player in state.players:
            player.action_cubes = cubes
            player.used_pink_powers.clear()

        state.round = next_round
        state.current_player_index = get_first_player_index(state)
        state.game_phase = GamePhase.MAIN_TURN
        state.action_data.clear()
        return state

    refresh_bird_tray(state)

    state.game_phase = GamePhase.MAIN_TURN
    state.action_data.clear()
    state.current_player_index = get_current_player_index(state)
    state.players[state.current_player_index].used_pink_powers.clear()
    return state


def _handle_end_turn(state: GameState, action: str) -> GameState:
    """Handle end-of-turn deferred effects."""
    effects = state.action_data.end_turn_effects

    if not effects:
        return _finalize_turn(state)

    current_effect = effects[0]

    if current_effect.effect_type == "discard_cards":
        execution = state.action_data.get_current_execution()

        if not execution or execution.phase != "end_turn_discard":
            state.action_data.execution_stack.append(
                PowerExecution(
                    power_id=0,
                    bird_id=0,
                    spot_row=0,
                    spot_col=0,
                    player_index=current_effect.player_index,
                    phase="end_turn_discard",
                    context={"amount": current_effect.amount},
                )
            )
            return state

        card_id = int(action.split("_")[-1])
        player = state.players[current_effect.player_index]

        card_to_discard = next((c for c in player.bird_hand if c.id == card_id), None)
        if card_to_discard:
            player.bird_hand.remove(card_to_discard)
            state.discarded_birds.append(card_to_discard)

        effects.pop(0)
        state.action_data.execution_stack.pop()

        if not effects:
            return _finalize_turn(state)

        return _handle_end_turn(state, "")

    return state


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
        state.action_data.amount_to_discard = bird_amount
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
    state.action_data.clear()
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
                sum(bird.eggs for bird in played_birds) if played_birds else 0
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


def _collect_food(state: GameState, action: str) -> GameState:
    """Handle dice selection."""

    if action.startswith("select_die_"):
        die_index, food_type = parse_select_die_action(action)

        state = select_die_effect(state, die_index, food_type)
        state.action_data.food_needed -= 1

        if food_type == "rodent":
            state.action_data.gained_rodent = True

        if not state.action_data.food_needed:
            pink_trigger = None
            pink_context = None
            if state.action_data.gained_rodent:
                pink_trigger = PinkTrigger.GAIN_FOOD
                pink_context = {"food_type": "rodent"}
            return _finish_main_action(
                state,
                "brown",
                habitat="forest",
                pink_trigger=pink_trigger,
                pink_context=pink_context,
            )

        return state

    elif action == "reroll_all":
        state.feeder = roll_feeder()
        return state

    raise ValueError(f"No known action{action}")


def _lay_eggs(state: GameState, action: str) -> GameState:
    """Handle laying eggs."""
    egg_distribution = parse_lay_eggs_action(action)

    state = lay_eggs_effect(state, egg_distribution)

    return _finish_main_action(
        state,
        "brown",
        habitat="grassland",
        pink_trigger=PinkTrigger.LAY_EGGS,
    )


def _draw_cards(state: GameState, action: str) -> GameState:
    """Handle drawing cards"""
    tray_birds, deck_count = parse_draw_cards_action(action)

    state = draw_cards_effect(state, tray_birds, deck_count)

    return _finish_main_action(state, "brown", habitat="wetland")


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


def _discard_bird_for_food(state: GameState, action: str) -> GameState:
    """Handle discarding a bird for extra food."""
    if action.startswith("discard_bird_"):
        bird_id = int(action.split("_")[2])

        state = discard_bird_from_hand_effect(state, bird_id)

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.COLLECT_FOOD
        state.action_data.food_needed = base_amount + 1

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

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.LAY_EGGS
        state.action_data.eggs_needed = base_amount + 1

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

        base_amount = state.action_data.base_amount
        state.game_phase = GamePhase.DRAW_CARDS
        state.action_data.cards_needed = base_amount + 1

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

    # Check egg cost
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

    bird_to_play = next(
        (bird for bird in current_player.bird_hand if bird.id == bird_id), None
    )
    if not bird_to_play:
        raise ValueError(f"Bird {bird_id} not in hand")

    # Check food cost
    if bird_to_play.cost and not (
        state.action_data.pending_cost
        and state.action_data.pending_cost.cost_type == "food_paid"
    ):
        # Check if we've already paid eggs but not food
        if (
            state.action_data.pending_cost
            and state.action_data.pending_cost.cost_type in ["egg", "egg_paid"]
        ):
            # Eggs were paid (or being paid), now check food
            pass
        else:
            state.action_data.pending_cost = CostPayment(
                cost_type="food",
                amount=bird_to_play.cost,
                callback_phase=state.game_phase,
                callback_action=action,
            )
            state.game_phase = GamePhase.PAY_FOOD_COST
            return state

    state = place_bird_effect(state, bird_id, row, col)

    # Check if this was triggered by Power 12
    execution = state.action_data.get_current_execution()
    if execution and execution.power_id == 12:
        # Pop Power 12 from stack
        state.action_data.execution_stack.pop()
        state.game_phase = GamePhase.ACTIVATE_POWERS
        return _finish_main_action(
            state,
            "white",
            spot=target_spot,
            skip_action_cube=True,
            pink_trigger=PinkTrigger.BIRD_PLAYED,
            pink_context={"habitat": target_spot.habitat},
        )

    state.action_data.pending_cost = None
    return _finish_main_action(
        state,
        "white",
        spot=target_spot,
        pink_trigger=PinkTrigger.BIRD_PLAYED,
        pink_context={"habitat": target_spot.habitat},
    )


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
        handler = _ACTION_HANDLERS.get(callback_phase)
        if not handler:
            raise NotImplementedError(f"No handler for: {callback_phase}")
        return handler(state, callback_action)

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
        handler = _ACTION_HANDLERS.get(callback_phase)
        if not handler:
            raise NotImplementedError(f"No handler for: {callback_phase}")
        return handler(state, callback_action)

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
