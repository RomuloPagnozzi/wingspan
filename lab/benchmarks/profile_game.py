"""Play one full MCTS game for profiling.

Usage:
    pyinstrument -r html -o profile.html -m lab.benchmarks.profile_game

Set DETERMINIZE=True to profile IS-MCTS. MCTS itself is single-threaded;
experiment-level (game-level) parallelism lives in the harness.
"""

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import MCTSStrategy, MCTSConfig

# ── Parameters ──────────────────────────────────────────────
N_PLAYERS = 2
SIMULATIONS = 100
EXPLORATION_CONSTANT = 1.41
DETERMINIZE = True
GAME_SEED = 42
MCTS_SEED = 123
# ────────────────────────────────────────────────────────────


def play_game():
    config = MCTSConfig(
        simulations=SIMULATIONS,
        exploration_constant=EXPLORATION_CONSTANT,
        determinize=DETERMINIZE,
    )
    state = initiate_state(N_PLAYERS, seed=GAME_SEED)

    with MCTSStrategy(params=config, seed=MCTS_SEED) as strategy:
        move_count = 0

        while actions := get_actions(state):
            action = strategy.select_action(state, actions)
            state = transition_state(state, action)
            move_count += 1

        scores = [p.score.total for p in state.players]

    print(f"Game over after {move_count} moves")
    for i, score in enumerate(scores):
        print(f"  Player {i + 1}: {score}")


if __name__ == "__main__":
    play_game()
