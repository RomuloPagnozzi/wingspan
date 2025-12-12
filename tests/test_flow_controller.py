"""Test flow control and power activation."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase
from game.engine import (
    _finish_main_action,
    _finish_main_action_no_powers,
    _check_powers_done,
    transition_state,
)
from game.actions import get_actions


def test_finish_main_action_no_powers():
    """Main action with no triggered powers goes to MAIN_TURN."""
    state = initiate_state(2)
    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    state.current_player_index = first_player_idx
    state.players[first_player_idx].action_cubes = 5

    state = _finish_main_action(state, "forest")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == (first_player_idx + 1) % 2
    assert state.action_data == {}
    assert state.players[first_player_idx].action_cubes == 4


def test_finish_main_action_no_powers_explicit():
    """Main action that never triggers powers (play bird)."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].action_cubes = 5

    state = _finish_main_action_no_powers(state)

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].action_cubes == 4


def test_check_powers_done_transitions():
    """When power queue exhausted, transition to MAIN_TURN."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [{"bird_id": 1, "power_data": {}}],
        "current_power_index": 1,  # Past end of queue
    }

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.action_data == {}


def test_check_powers_done_continues():
    """When powers remain, stay in ACTIVATE_POWERS."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [
            {"bird_id": 1, "power_data": {}},
            {"bird_id": 2, "power_data": {}},
        ],
        "current_power_index": 0,
    }

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert "powers_queue" in state.action_data


def test_power_activation_skip():
    """Skipping a power advances the index."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            },
            {
                "bird_id": 2,
                "power_data": {"data": {"id": 1, "details": {"type": "fish"}}},
            },
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "skip_power")

    assert state.action_data["current_power_index"] == 1


def test_power_1_execution():
    """Power type 1 gives all players a resource."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    initial_p0 = state.players[0].food.get("seed", 0)
    initial_p1 = state.players[1].food.get("seed", 0)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert state.players[0].food.get("seed", 0) == initial_p0 + 1
    assert state.players[1].food.get("seed", 0) == initial_p1 + 1
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_2_sets_up_multi_player():
    """Power type 2 sets up multi-player state for sequential choices."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Give both players bowl nest birds
    bird0 = state.players[0].bird_hand[0]
    bird0.nest = "bowl"
    bird0.egg_limit = 3
    state.players[0].board[0][0].bird = bird0
    state.players[0].bird_hand.remove(bird0)

    bird1 = state.players[1].bird_hand[0]
    bird1.nest = "bowl"
    bird1.egg_limit = 3
    state.players[1].board[0][0].bird = bird1
    state.players[1].bird_hand.remove(bird1)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert state.action_data["sub_phase"] == "power_2_choices"
    assert state.action_data["activator"] == 0
    assert state.action_data["awaiting_players"] == [0, 1]
    assert state.action_data["nest_type"] == "bowl"
    assert state.current_player_index == 0  # Activator goes first


def test_multi_player_actions_generated():
    """Multi-player power generates correct choice actions."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    bird0 = state.players[0].bird_hand[0]
    bird0.nest = "bowl"
    bird0.egg_limit = 3
    state.players[0].board[0][0].bird = bird0
    state.players[0].bird_hand.remove(bird0)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
        "current_power_index": 0,
        "sub_phase": "power_2_choices",
        "nest_type": "bowl",
        "activator": 0,
        "awaiting_players": [0],
    }

    actions = get_actions(state)

    assert len(actions) > 0
    assert all(a.startswith("activate_") for a in actions)
