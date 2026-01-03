"""End-to-end tests for Power 14: Repeat another bird's power in this habitat."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase, get_bird_power, get_bird
from game.engine import transition_state
from game.actions import get_actions


def get_all_birds(state):
    """Get all birds from game state (deck, tray, and player hands)."""
    return (
        list(state.bird_deck)
        + list(state.bird_tray)
        + list(state.players[0].bird_hand)
        + list(state.players[1].bird_hand)
    )


def test_power_14_brown_repeat_simple_power():
    """Test Power 14 (brown): Repeat a simple brown power (Power 3: cache seed)."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find Power 14 (brown) bird
    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (brown) bird"

    # Find Power 3 bird
    power_3_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 3:
            power_3_bird = bird
            break

    assert power_3_bird, "Should find Power 3 bird"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place birds in same habitat (forest)
    state.players[0].board[0][0].bird = power_14_bird
    state.players[0].board[0][1].bird = power_3_bird

    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird.id,
                "power_id": 14,
                "power_data": power_14_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Should enter sub-phase for bird selection
    assert state.action_data.get("sub_phase") == "power_14_select_bird"

    # Verify bird selection available
    actions = get_actions(state)
    assert f"select_bird_{power_3_bird.id}" in actions

    # Select Power 3 bird - power executes immediately
    state = transition_state(state, f"select_bird_{power_3_bird.id}")

    # Verify Power 3 was executed (bird should have cached food)
    assert power_3_bird.stashed_food == 1

    # Verify cleanup - no sub_phase, turn should be done
    assert "sub_phase" not in state.action_data


def test_power_14_predator_repeat():
    """Test Power 14 (predator): Repeat a predator power (Power 11)."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "predator":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (predator) bird"

    # Find Power 11 bird
    power_11_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 11:
            power_11_bird = bird
            break

    assert power_11_bird, "Should find Power 11 bird"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place birds in same habitat (wetland)
    state.players[0].board[2][0].bird = power_14_bird
    state.players[0].board[2][1].bird = power_11_bird

    activating_spot = state.players[0].board[2][0]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird.id,
                "power_id": 14,
                "power_data": power_14_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Should enter sub-phase
    assert state.action_data.get("sub_phase") == "power_14_select_bird"

    # Select Power 11 bird
    actions = get_actions(state)
    assert f"select_bird_{power_11_bird.id}" in actions

    state = transition_state(state, f"select_bird_{power_11_bird.id}")

    # Verify Power 11 was executed (predator power draws from deck and tucks/discards)
    # The power executes immediately, no queue addition
    assert "sub_phase" not in state.action_data


def test_power_14_no_eligible_birds():
    """Test Power 14 cannot activate when no eligible birds in habitat."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find Power 14 (brown) bird
    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (brown) bird"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place Power 14 bird alone in forest (no other birds)
    state.players[0].board[0][0].bird = power_14_bird

    activating_spot = state.players[0].board[0][0]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird.id,
                "power_id": 14,
                "power_data": power_14_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Cannot activate (only skip available)
    actions = get_actions(state)
    assert "activate_power" not in actions
    assert "skip_power" in actions


def test_power_14_self_repeat_prevented():
    """Test Power 14 cannot repeat itself."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find two Power 14 (brown) birds
    power_14_birds = []
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_birds.append((bird, power))
                if len(power_14_birds) == 2:
                    break

    assert len(power_14_birds) >= 2, "Should find at least 2 Power 14 (brown) birds"

    power_14_bird_1, power_14_data_1 = power_14_birds[0]
    power_14_bird_2, power_14_data_2 = power_14_birds[1]

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place both in same habitat
    state.players[0].board[0][0].bird = power_14_bird_1
    state.players[0].board[0][1].bird = power_14_bird_2

    activating_spot = state.players[0].board[0][0]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird_1.id,
                "power_id": 14,
                "power_data": power_14_data_1,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Should enter sub-phase
    assert state.action_data.get("sub_phase") == "power_14_select_bird"

    # Verify activating bird is not in selection
    actions = get_actions(state)
    assert f"select_bird_{power_14_bird_1.id}" not in actions

    # Verify other Power 14 bird IS selectable
    assert f"select_bird_{power_14_bird_2.id}" in actions


def test_power_14_different_habitat_isolated():
    """Test Power 14 only finds birds in same habitat."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find Power 14 (brown) bird
    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (brown) bird"

    # Find a bird with brown power
    brown_power_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("color") == "brown" and bird.id != power_14_bird.id:
            brown_power_bird = bird
            break

    assert brown_power_bird, "Should find bird with brown power"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place Power 14 bird in forest (row 0)
    state.players[0].board[0][0].bird = power_14_bird

    # Place brown power bird in DIFFERENT habitat (grassland, row 1)
    state.players[0].board[1][0].bird = brown_power_bird

    activating_spot = state.players[0].board[0][0]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird.id,
                "power_id": 14,
                "power_data": power_14_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Cannot activate (bird in different habitat)
    actions = get_actions(state)
    assert "activate_power" not in actions
    assert "skip_power" in actions


def test_power_14_brown_filters_correctly():
    """Test Power 14 (brown) only selects brown power birds."""
    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find Power 14 (brown) bird
    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (brown) bird"

    # Find birds with different power colors
    brown_bird = None
    white_bird = None

    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and bird.id != power_14_bird.id:
            if power.get("color") == "brown" and not brown_bird:
                brown_bird = bird
            elif power.get("color") == "white" and not white_bird:
                white_bird = bird

    assert brown_bird and white_bird, "Should find both brown and white power birds"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place all in same habitat
    state.players[0].board[0][0].bird = power_14_bird
    state.players[0].board[0][1].bird = brown_bird
    state.players[0].board[0][2].bird = white_bird

    activating_spot = state.players[0].board[0][0]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_14_bird.id,
                "power_id": 14,
                "power_data": power_14_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Verify only brown bird is selectable
    actions = get_actions(state)
    assert f"select_bird_{brown_bird.id}" in actions
    assert f"select_bird_{white_bird.id}" not in actions


def test_power_14_validation():
    """Test Power 14 validation works correctly."""
    from game.powers import can_execute_power

    state = initiate_state(2)

    all_birds = get_all_birds(state)

    # Find Power 14 (brown) bird
    power_14_bird = None
    power_14_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 14:
            if power["data"].get("details", {}).get("type") == "brown":
                power_14_bird = bird
                power_14_data = power
                break

    assert power_14_bird, "Should find Power 14 (brown) bird"

    # Find brown power bird
    brown_power_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("color") == "brown" and bird.id != power_14_bird.id:
            brown_power_bird = bird
            break

    assert brown_power_bird, "Should find bird with brown power"

    state.current_player_index = 0
    state.players[0].board[0][0].bird = power_14_bird
    spot = state.players[0].board[0][0]

    # Invalid when no other birds in habitat
    power_entry = {
        "power_data": power_14_data,
        "spot": spot,
        "bird_id": power_14_bird.id,
    }
    assert not can_execute_power(state, power_entry)

    # Place brown power bird in same habitat
    state.players[0].board[0][1].bird = brown_power_bird

    # Valid when brown power bird exists in habitat
    assert can_execute_power(state, power_entry)


if __name__ == "__main__":
    print("Running Power 14 tests...")

    test_power_14_brown_repeat_simple_power()
    print("✓ test_power_14_brown_repeat_simple_power passed")

    test_power_14_predator_repeat()
    print("✓ test_power_14_predator_repeat passed")

    test_power_14_no_eligible_birds()
    print("✓ test_power_14_no_eligible_birds passed")

    test_power_14_self_repeat_prevented()
    print("✓ test_power_14_self_repeat_prevented passed")

    test_power_14_different_habitat_isolated()
    print("✓ test_power_14_different_habitat_isolated passed")

    test_power_14_brown_filters_correctly()
    print("✓ test_power_14_brown_filters_correctly passed")

    test_power_14_validation()
    print("✓ test_power_14_validation passed")

    print("\n✅ All Power 14 tests passed!")
