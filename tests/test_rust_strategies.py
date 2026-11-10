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


def test_picks_a_legal_move_and_reports_its_search():
    s = _main_turn_state()
    legal = get_actions(s)
    strategy = create_strategy("mcts_rs", seed=1, simulations=60)
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


def test_mcts_rs_defaults_to_the_tuned_tree():
    from wingspan.ai.rust import TUNED_TREE

    config = create_strategy("mcts_rs", seed=1).config
    assert {k: config[k] for k in TUNED_TREE} == TUNED_TREE
    assert create_strategy("mcts_rs", simulations=10_000).config["simulations"] == 10_000


def test_playout_cap_randomization_mixes_fast_and_full_searches():
    s = _main_turn_state()
    legal = get_actions(s)
    totals = set()
    bot = create_strategy("mcts_rs", seed=4, simulations=200, fast_simulations=40, full_fraction=0.5)
    for _ in range(30):
        bot.select_action(s, legal)
        totals.add(sum(bot.get_last_visit_counts().values()))
    assert totals == {40, 200}  # both budgets used
    assert create_strategy("mcts_rs", fast_simulations=40, full_fraction=0.25).config["full_fraction"] == 0.25
    with pytest.raises(ValueError):
        create_strategy("mcts_rs", fast_simulations=40, full_fraction=1.5)
