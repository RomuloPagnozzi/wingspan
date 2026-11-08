"""The Rust-backed strategies (`wingspan.ai.rust`); skipped when the extension isn't built."""

import pytest

pytest.importorskip("wingspan_rs")

from wingspan.ai import create_strategy  # noqa: E402
from wingspan.engine.actions import get_actions  # noqa: E402
from wingspan.engine.core import initiate_state  # noqa: E402
from wingspan.engine.engine import transition_state  # noqa: E402


def _main_turn_state():
    s = initiate_state(2, seed=3)
    while s.game_phase.value != "main_turn":
        s = transition_state(s, get_actions(s)[0])
    return s


@pytest.mark.parametrize(
    "name, params",
    [
        ("flat_mc_rs", {"playouts": 60}),
        ("mcts_rs", {"simulations": 60, "determinize": True, "value_function": "absolute_score"}),
    ],
)
def test_picks_a_legal_move_and_reports_its_search(name, params):
    s = _main_turn_state()
    legal = get_actions(s)
    strategy = create_strategy(name, seed=1, **params)
    assert strategy.select_action(s, legal) in legal
    visits = strategy.get_last_visit_counts()
    assert set(visits) <= set(legal) and sum(visits.values()) > 0
    assert set(strategy.get_last_action_values()) <= set(legal)


def test_mcts_rs_spends_its_phase_budget():
    s = _main_turn_state()
    strategy = create_strategy("mcts_rs", seed=1, simulations=500, determinize=True, phase_simulations={"main_turn": 40})
    strategy.select_action(s, get_actions(s))
    assert sum(strategy.get_last_visit_counts().values()) == 40
    assert strategy.config["phase_simulations"] == {"main_turn": 40}
    with pytest.raises(ValueError, match="main_trun"):
        create_strategy("mcts_rs", phase_simulations={"main_trun": 40})
