"""Tests for game engine: state transitions, turn lifecycle, and power activation."""

from game.core import (
    initiate_state,
    GamePhase,
    ActionData,
    QueuedPower,
)
from game.engine import (
    finish_main_action,
    _check_powers_done,
)
from game.engine import transition_state
from conftest import setup_power_queue


def test_finish_main_action_no_powers():
    """Main action with no triggered powers goes to MAIN_TURN."""
    state = initiate_state(2)
    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    state.current_player_index = first_player_idx
    state.players[first_player_idx].action_cubes = 5

    state = finish_main_action(state, "brown", habitat="forest")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == (first_player_idx + 1) % 2
    assert state.action_data is None or (
        isinstance(state.action_data, ActionData)
        and len(state.action_data.powers_queue) == 0
    )
    assert state.players[first_player_idx].action_cubes == 4


def test_finish_main_action_no_powers_explicit():
    """Main action with white power color but no white powers."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].action_cubes = 5

    state = finish_main_action(state, "white")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].action_cubes == 4


def test_check_powers_done_transitions():
    """When power queue exhausted, transition to MAIN_TURN."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=1,
            bird_id=1,
            spot_row=0,
            spot_col=0,
            player_index=0,
            power_data={},
        )
    ]
    state.action_data.current_power_index = 1  # Past end of queue

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.MAIN_TURN


def test_check_powers_done_continues():
    """When powers remain, stay in ACTIVATE_POWERS."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=1, bird_id=1, spot_row=0, spot_col=0, player_index=0, power_data={}
        ),
        QueuedPower(
            power_id=2, bird_id=2, spot_row=0, spot_col=0, player_index=0, power_data={}
        ),
    ]
    state.action_data.current_power_index = 0

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert len(state.action_data.powers_queue) == 2


def test_power_activation_skip():
    """Skipping a power advances the index."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            },
            {
                "bird_id": 2,
                "power_data": {"data": {"id": 1, "details": {"type": "fish"}}},
            },
        ],
    )

    state = transition_state(state, "skip_power")

    assert state.action_data.current_power_index == 1
