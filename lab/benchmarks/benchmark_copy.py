"""Benchmark: custom copy_state vs deepcopy over complete games."""

import copy
from timeit import timeit
import random

from game.core import initiate_state, GameState, Action
from game.actions import get_actions
from game.engine import transition_state
from game.phase_handlers import get_phase_handler

GAMES = 100
PLAYERS = 5


def transition_state_deepcopy(state: GameState, action: Action) -> GameState:
    """Same as transition_state but using deepcopy."""
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


def run_games_custom():
    for _ in range(GAMES):
        s = initiate_state(PLAYERS)
        while actions := get_actions(s):
            s = transition_state(s, random.choice(actions))


def run_games_deepcopy():
    for _ in range(GAMES):
        s = initiate_state(PLAYERS)
        while actions := get_actions(s):
            s = transition_state_deepcopy(s, random.choice(actions))


if __name__ == "__main__":
    random.seed(42)
    print(f"Benchmarking {GAMES} complete games with {PLAYERS} players each...\n")

    random.seed(42)
    custom_time = timeit(run_games_custom, number=1)

    random.seed(42)
    deepcopy_time = timeit(run_games_deepcopy, number=1)

    print(f"custom copy_state: {custom_time:.2f}s")
    print(f"deepcopy:          {deepcopy_time:.2f}s")
    print(f"\nRatio: deepcopy is {deepcopy_time/custom_time:.2f}x slower")
