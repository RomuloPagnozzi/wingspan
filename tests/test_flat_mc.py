import random

import pytest

from wingspan.ai.flat_mc import FlatMCStrategy
from wingspan.engine.actions import get_actions
from wingspan.engine.core import GamePhase, initiate_state
from wingspan.engine.engine import transition_state


def first_state(want, max_games=50):
    """The first state of some random games where `want(state, actions)` holds."""
    for seed in range(max_games):
        rng = random.Random(seed)
        state = initiate_state(2, seed=seed)
        while actions := get_actions(state):
            if want(state, actions):
                return state, actions
            state = transition_state(state, rng.choice(actions))
    raise AssertionError("no such state")


def test_paired_re_deals_once_per_world_independent_once_per_move(monkeypatch):
    import wingspan.ai.flat_mc as flat_mc

    state, actions = first_state(lambda s, a: len(a) == 3)
    deals = []
    real = flat_mc.redeterminize
    monkeypatch.setattr(flat_mc, "redeterminize", lambda *a: deals.append(1) or real(*a))
    for paired, expected in ((True, 20), (False, 60)):
        deals.clear()
        FlatMCStrategy(seed=0, playouts=60, paired=paired).select_action(state, actions)
        assert len(deals) == expected  # 20 worlds; shared by the 3 moves, or one per move


def test_a_playout_depends_only_on_its_world_and_seed():
    state, actions = first_state(lambda s, a: len(a) > 1)
    bot = FlatMCStrategy(seed=0)
    me = state.current_player_index
    assert bot._playout(state, actions[0], me, seed=10) == bot._playout(state, actions[0], me, seed=10)


def test_same_seed_same_pick_and_the_pick_is_legal():
    state, actions = first_state(lambda s, a: len(a) > 2)
    picks = {str(FlatMCStrategy(seed=3, playouts=60).select_action(state, actions)) for _ in range(2)}
    assert len(picks) == 1 and picks <= {str(a) for a in actions}


def test_a_phase_uses_its_own_budget():
    state, actions = first_state(lambda s, a: s.game_phase == GamePhase.LAY_EGGS and len(a) > 1)
    bot = FlatMCStrategy(seed=0, playouts=10_000, phase_playouts={"lay_eggs": 10 * len(actions)})
    bot.select_action(state, actions)
    assert max(bot.get_last_visit_counts().values()) <= 10


def test_a_misspelt_phase_is_an_error():
    with pytest.raises(ValueError, match="lay_egs"):
        FlatMCStrategy(phase_playouts={"lay_egs": 300})
