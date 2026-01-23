import copy
from .data import GameState
from .phase_handlers import get_phase_handler


def transition_state(state: GameState, action: str) -> GameState:
    """Return new state after applying an action."""
    new_state = copy.deepcopy(state)
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
