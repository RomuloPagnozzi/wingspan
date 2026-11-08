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
        ("flat_mc", {"playouts": 60}),
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


def test_flat_mc_same_seed_same_legal_pick():
    s = _main_turn_state()
    legal = get_actions(s)
    picks = {str(create_strategy("flat_mc", seed=3, playouts=60).select_action(s, legal)) for _ in range(2)}
    assert len(picks) == 1 and picks <= {str(a) for a in legal}


def test_flat_mc_spends_its_phase_budget():
    s = _main_turn_state()
    legal = get_actions(s)
    bot = create_strategy("flat_mc", seed=0, playouts=10_000, phase_playouts={"main_turn": 10 * len(legal)})
    bot.select_action(s, legal)
    assert max(bot.get_last_visit_counts().values()) <= 10
    with pytest.raises(ValueError, match="main_trun"):
        create_strategy("flat_mc", phase_playouts={"main_trun": 300})


def test_mcts_rs_defaults_to_the_tuned_tree():
    from wingspan.ai.rust import TUNED_TREE

    config = create_strategy("mcts_rs", seed=1).config
    assert {k: config[k] for k in TUNED_TREE} == TUNED_TREE
    assert create_strategy("mcts_rs", simulations=10_000).config["simulations"] == 10_000
