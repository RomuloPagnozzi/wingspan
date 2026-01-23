"""Tests for Power 16: Trade 1 food for any other type from supply."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase, ActionData, QueuedPower
from game.engine import transition_state
from game.actions import get_actions
from game.power_validators import can_execute_power


def setup_power_16_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 16 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 16}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=16,
            bird_id=bird_id,
            spot_row=(
                spot.row if spot else 0
            ),  # All powers have spots (bird locations); None is just a testing convenience
            spot_col=spot.col if spot else 0,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def create_power_16_data():
    """Create Power 16 data structure."""
    return {
        "color": "brown",
        "data": {
            "id": 16,
            "details": {},
        },
    }


def setup_power_16_state(state, food_dict):
    """Setup state with Power 16 activation and specified food."""
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    state.players[0].food = food_dict.copy()

    power_data = create_power_16_data()

    setup_power_16_execution(state, state.current_player_index, 1, None, power_data)

    return state


def test_power_16_cannot_execute_when_no_food():
    """Test Power 16 cannot execute when player has no food tokens."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].food = {}

    spot = state.players[0].board[0][0]
    power_data = create_power_16_data()

    power_entry = {
        "power_data": power_data,
        "spot": spot,
        "bird_id": 9999,
    }

    assert not can_execute_power(state, power_entry)


def test_power_16_can_execute_when_has_food():
    """Test Power 16 can execute when player has at least one food token."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].food = {"seed": 1}

    spot = state.players[0].board[0][0]
    power_data = create_power_16_data()

    power_entry = {
        "power_data": power_data,
        "spot": spot,
        "bird_id": 9999,
    }

    assert can_execute_power(state, power_entry)


def test_power_16_generates_correct_actions_single_food_type():
    """Test Power 16 generates 4 trade actions when player has one food type."""
    state = initiate_state(2)
    state = setup_power_16_state(state, {"seed": 2})

    state = transition_state(state, "activate_power")

    assert state.action_data.execution_stack[-1].phase == "select_trade"

    actions = get_actions(state)

    expected_actions = [
        "trade_seed_for_invertebrate",
        "trade_seed_for_fish",
        "trade_seed_for_fruit",
        "trade_seed_for_rodent",
    ]

    assert len(actions) == 4
    for expected in expected_actions:
        assert expected in actions


def test_power_16_generates_correct_actions_multiple_food_types():
    """Test Power 16 generates 8 trade actions when player has two food types."""
    state = initiate_state(2)
    state = setup_power_16_state(state, {"seed": 2, "fish": 1})

    state = transition_state(state, "activate_power")

    assert state.action_data.execution_stack[-1].phase == "select_trade"

    actions = get_actions(state)

    expected_actions = [
        "trade_seed_for_invertebrate",
        "trade_seed_for_fish",
        "trade_seed_for_fruit",
        "trade_seed_for_rodent",
        "trade_fish_for_invertebrate",
        "trade_fish_for_seed",
        "trade_fish_for_fruit",
        "trade_fish_for_rodent",
    ]

    assert len(actions) == 8
    for expected in expected_actions:
        assert expected in actions


def test_power_16_trade_executes_correctly():
    """Test Power 16 trade correctly removes and adds food."""
    state = initiate_state(2)
    state = setup_power_16_state(state, {"seed": 2, "fish": 1})

    state = transition_state(state, "activate_power")
    state = transition_state(state, "trade_seed_for_invertebrate")

    assert state.players[0].food.get("seed") == 1
    assert state.players[0].food.get("fish") == 1
    assert state.players[0].food.get("invertebrate") == 1

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_16_trade_removes_food_type_when_depleted():
    """Test Power 16 removes food type from dict when trading last unit."""
    state = initiate_state(2)
    state = setup_power_16_state(state, {"seed": 1})

    state = transition_state(state, "activate_power")
    state = transition_state(state, "trade_seed_for_fruit")

    assert "seed" not in state.players[0].food
    assert state.players[0].food.get("fruit") == 1

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


if __name__ == "__main__":
    print("Running Power 16 tests...")

    test_power_16_cannot_execute_when_no_food()
    print("✓ test_power_16_cannot_execute_when_no_food passed")

    test_power_16_can_execute_when_has_food()
    print("✓ test_power_16_can_execute_when_has_food passed")

    test_power_16_generates_correct_actions_single_food_type()
    print("✓ test_power_16_generates_correct_actions_single_food_type passed")

    test_power_16_generates_correct_actions_multiple_food_types()
    print("✓ test_power_16_generates_correct_actions_multiple_food_types passed")

    test_power_16_trade_executes_correctly()
    print("✓ test_power_16_trade_executes_correctly passed")

    test_power_16_trade_removes_food_type_when_depleted()
    print("✓ test_power_16_trade_removes_food_type_when_depleted passed")

    print("\n✅ All Power 16 tests passed!")
