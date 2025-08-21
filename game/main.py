from .data import GameState
from itertools import cycle, islice


def get_player_index(s: GameState) -> int:
    """Legacy function to determine current player - use state.current_player_index instead."""
    players = s.players
    first_player_index = next(
        i for i, player in enumerate(players) if player.first_player
    )
    all_same_cubes = all(
        player.action_cubes == players[0].action_cubes for player in players
    )

    if all_same_cubes:
        return first_player_index

    first_player_actions = players[first_player_index].action_cubes
    cycle_iterator = islice(cycle(enumerate(players)), first_player_index, None, 1)
    index, player = next(islice(cycle_iterator, None, None))
    while player.action_cubes == first_player_actions:
        index, player = next(islice(cycle_iterator, None, None))
    return index


# Player chooses to keep up to 5 birds, discarding 1 food token for each
# Player chooses to keep 1 bonus card


# S0
# Player - return which player to move in state s DONE
# Action - return legal moves in state s
# Result - return state after action a taken in state s
# Terminal - checks if state s is a terminal state
# Utility - final numerical value for terminal state s
