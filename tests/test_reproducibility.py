"""Tests for game reproducibility with seeded RNG."""

import random

from game.core import initiate_state, copy_state
from game.actions import get_actions
from game.engine import transition_state


def test_same_seed_produces_identical_initial_state():
    """Same seed should produce identical game setup."""
    state1 = initiate_state(2, seed=42)
    state2 = initiate_state(2, seed=42)

    assert state1.bird_deck == state2.bird_deck
    assert state1.bonus_deck == state2.bonus_deck
    assert state1.feeder == state2.feeder
    assert state1.bird_tray == state2.bird_tray
    assert state1.round_goal_config
    assert state2.round_goal_config
    assert (
        state1.round_goal_config.selected_goals
        == state2.round_goal_config.selected_goals
    )

    for p1, p2 in zip(state1.players, state2.players):
        assert p1.bird_hand == p2.bird_hand
        assert p1.bonus_hand == p2.bonus_hand
        assert p1.first_player == p2.first_player


def test_different_seeds_produce_different_states():
    """Different seeds should produce different game setups."""
    state1 = initiate_state(2, seed=42)
    state2 = initiate_state(2, seed=43)

    assert state1.round_goal_config
    assert state2.round_goal_config

    different = (
        state1.bird_deck != state2.bird_deck
        or state1.feeder != state2.feeder
        or state1.round_goal_config.selected_goals
        != state2.round_goal_config.selected_goals
    )
    assert different


def test_copy_state_creates_independent_rng():
    """Copied state should have independent RNG that starts at same point."""
    state = initiate_state(2, seed=42)
    copied = copy_state(state)

    r1 = state.rng.random()
    r2 = copied.rng.random()

    assert r1 == r2


def test_copy_state_rng_diverges_after_use():
    """After using one RNG, they should diverge."""
    state = initiate_state(2, seed=42)
    copied = copy_state(state)

    state.rng.random()
    state.rng.random()

    r_original = state.rng.random()
    r_copied = copied.rng.random()

    assert r_original != r_copied


def test_full_game_reproducibility():
    """Playing the same game twice with same seed should produce same result."""

    def play_game(seed: int) -> tuple:
        state = initiate_state(2, seed=seed)
        action_rng = random.Random(seed)
        actions_taken = []

        while actions := get_actions(state):
            action = action_rng.choice(actions)
            actions_taken.append(action)
            state = transition_state(state, action)

        scores = [p.score.total for p in state.players]
        return tuple(scores), actions_taken

    scores1, actions1 = play_game(seed=123)
    scores2, actions2 = play_game(seed=123)

    assert scores1 == scores2
    assert actions1 == actions2
