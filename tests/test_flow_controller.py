"""Test centralized flow control."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase
from game.effects import EffectResult, EffectContext
from game.engine import apply_effect_with_flow


def test_flow_main_action_no_powers():
    state = initiate_state(2)
    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    state.current_player_index = first_player_idx
    state.game_phase = GamePhase.DRAW_CARDS

    result = EffectResult(state=state, triggers_powers=False, consumes_action_cube=True)
    state = apply_effect_with_flow(state, result, EffectContext.MAIN_ACTION)

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == (first_player_idx + 1) % 2
    assert state.action_data == {}


def test_flow_power_activation_no_phase_change():
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [{"bird_id": 1, "power_data": {}}],
        "current_power_index": 0,
    }

    result = EffectResult(state=state)

    state = apply_effect_with_flow(state, result, EffectContext.POWER_ACTIVATION)

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert "powers_queue" in state.action_data


def test_flow_consumes_action_cube():
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].action_cubes = 5

    result = EffectResult(state=state, consumes_action_cube=True)

    state = apply_effect_with_flow(state, result, EffectContext.MAIN_ACTION)

    assert state.players[0].action_cubes == 4


def test_flow_callback_preservation():
    state = initiate_state(2)
    state.action_data = {
        "callback": {"game_phase": GamePhase.PLAY_BIRD, "action": "test"}
    }

    result = EffectResult(state=state)

    state = apply_effect_with_flow(state, result, EffectContext.MAIN_ACTION)

    assert "callback" in state.action_data
