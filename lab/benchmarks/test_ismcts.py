"""Smoke tests for IS-MCTS (MCTSConfig.determinize=True).

Verifies the new code path runs end-to-end without error, that determinize=True
and determinize=False produce different move streams, and that the determinize=True
path is itself deterministic across runs with matched seeds.
"""

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import MCTSStrategy, MCTSConfig, ValueFunction


def _play(
    determinize: bool,
    *,
    n_players: int,
    game_seed: int,
    mcts_seed: int,
    simulations: int = 30,
) -> list:
    """Play a full game and return the move sequence."""
    params = MCTSConfig(
        simulations=simulations,
        exploration_constant=1.41,
        value_function=ValueFunction.SCORE_DELTA,
        num_workers=1,
        determinize=determinize,
    )
    strategy = MCTSStrategy(params=params, seed=mcts_seed)
    state = initiate_state(n_players, seed=game_seed)
    moves: list = []
    with strategy:
        while actions := get_actions(state):
            action = strategy.select_action(state, actions)
            moves.append(action)
            state = transition_state(state, action)
    return moves


def test_ismcts_runs_2p():
    moves = _play(determinize=True, n_players=2, game_seed=1, mcts_seed=11)
    assert len(moves) > 0


def test_ismcts_runs_3p():
    moves = _play(determinize=True, n_players=3, game_seed=2, mcts_seed=22)
    assert len(moves) > 0


def test_ismcts_is_deterministic_same_seeds():
    a = _play(determinize=True, n_players=2, game_seed=7, mcts_seed=42)
    b = _play(determinize=True, n_players=2, game_seed=7, mcts_seed=42)
    assert a == b


def test_ismcts_differs_from_peek_at_same_seeds():
    """Honest vs peek should disagree on at least one move (different info sets
    → different tree statistics → different action picks)."""
    peek = _play(determinize=False, n_players=2, game_seed=3, mcts_seed=99)
    ismcts = _play(determinize=True, n_players=2, game_seed=3, mcts_seed=99)
    assert peek != ismcts


def test_ismcts_action_values_populated():
    """After a search, the strategy exposes per-action visit counts and values."""
    params = MCTSConfig(simulations=30, determinize=True)
    strategy = MCTSStrategy(params=params, seed=5)
    state = initiate_state(2, seed=5)
    actions = get_actions(state)
    # Need a multi-action decision to make the search non-trivial.
    while len(actions) <= 1:
        state = transition_state(state, actions[0])
        actions = get_actions(state)
    with strategy:
        strategy.select_action(state, actions)
    visits = strategy.get_last_visit_counts()
    values = strategy.get_last_action_values()
    assert visits is not None and sum(visits.values()) > 0
    assert values is not None and len(values) > 0
