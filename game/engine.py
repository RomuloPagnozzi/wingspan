from .core import (
    GameState,
    GamePhase,
    Spot,
    PinkTrigger,
    QueuedPower,
    PowerExecution,
)
from .scoring import update_player_scores, update_round_goal_scores
from .utils import (
    get_triggered_powers,
    get_triggered_pink_powers,
    check_round_end,
    get_action_cubes_for_round,
    rotate_first_player,
    restock_bird_tray,
    refresh_bird_tray,
    get_first_player_index,
)
from .power import get_power_handler
from .core.custom_copy import copy_state


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying an action."""
    from .phase_handlers import get_phase_handler

    new_state = copy_state(state)

    handler = get_phase_handler(new_state.game_phase)
    if not handler:
        raise NotImplementedError(f"No handler for: {new_state.game_phase}")
    new_state = handler(new_state, action)

    while new_state.action_data.pending_callback:
        callback_phase, callback_action = new_state.action_data.pending_callback
        new_state.action_data.pending_callback = None
        handler = get_phase_handler(callback_phase)
        if not handler:
            raise NotImplementedError(f"No handler for callback: {callback_phase}")
        new_state = handler(new_state, callback_action)

    return new_state


def finish_main_action(
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


def activate_powers(state: GameState, action: str) -> GameState:
    """Handle power activation using stack-based execution.

    Paths:
    - Empty stack + skip_power: advance to next queued power
    - Empty stack + activate_power: push onto stack, call handler
    - Non-empty stack: route to current execution's phase handler
    """
    stack = state.action_data.execution_stack

    if not stack:
        if action == "skip_power":
            state.action_data.current_power_index += 1
            return _check_powers_done(state)

        if action == "activate_power":
            queued = state.action_data.get_current_queued_power()
            if not queued:
                raise ValueError("No power to activate")

            if queued.power_data.get("color") == "pink":
                player = state.players[queued.player_index]
                player.used_pink_powers.add(queued.bird_id)

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

            handler = get_power_handler(queued.power_id, None)
            if not handler:
                raise ValueError(f"No handler for power {queued.power_id}")

            state = handler(state, stack, action)

            if not stack:
                state.action_data.current_power_index += 1
                return _check_powers_done(state)

            return state

        raise ValueError(f"Unknown action with empty stack: {action}")

    current = stack[-1]
    handler = get_power_handler(current.power_id, current.phase)

    if not handler:
        raise ValueError(
            f"No handler for power {current.power_id} phase {current.phase}"
        )

    state = handler(state, stack, action)

    if not stack:
        state.action_data.current_power_index += 1
        return _check_powers_done(state)

    # Handle nested powers (e.g. Power 14 pushing another power)
    while stack and stack[-1].phase is None:
        new_power = stack[-1]
        initial_handler = get_power_handler(new_power.power_id, None)
        if not initial_handler:
            raise ValueError(f"No handler for power {new_power.power_id}")
        state = initial_handler(state, stack, "")
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
        return handle_end_turn(state, "")

    next_power = queue[current_index]
    state.current_player_index = next_power.player_index

    return state


def _finalize_turn(state: GameState) -> GameState:
    """Finalize turn: check for round end or advance to next player."""
    from .utils import get_current_player_index

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


def handle_end_turn(state: GameState, action: str) -> GameState:
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

        if card_id in player.bird_hand:
            player.bird_hand.remove(card_id)
            state.discarded_birds.append(card_id)

        effects.pop(0)
        state.action_data.execution_stack.pop()

        if not effects:
            return _finalize_turn(state)

        return handle_end_turn(state, "")

    return state
