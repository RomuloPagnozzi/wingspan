"""End-to-end tests for Power 14: Repeat another bird's power in this habitat."""

import sys

sys.path.append(".")

from game.data import (
    initiate_state,
    GamePhase,
    get_bird_power,
    get_bird,
    QueuedPower,
    ActionData,
)
from game.engine import transition_state
from game.actions import get_actions
from game.power_validators import can_execute_power


def get_all_birds(state):
    """Get all birds from game state (deck, tray, and player hands)."""
    return (
        list(state.bird_deck)
        + list(state.bird_tray)
        + list(state.players[0].bird_hand)
        + list(state.players[1].bird_hand)
    )


def setup_power_queue(state, power_bird, power_data, spot):
    """Helper to set up the power queue with new ActionData structure."""
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=power_data["data"]["id"],
            bird_id=power_bird.id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=state.current_player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


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
    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Should have an execution on stack with select_bird phase
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "select_bird"

    # Verify bird selection available
    actions = get_actions(state)
    assert f"select_bird_{power_3_bird.id}" in actions

    # Select Power 3 bird - power executes immediately
    state = transition_state(state, f"select_bird_{power_3_bird.id}")

    # Verify Power 3 was executed (bird should have cached food)
    assert power_3_bird.stashed_food == 1

    # Verify cleanup - stack should be empty, turn should be done
    assert len(state.action_data.execution_stack) == 0


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
    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Should enter sub-phase
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "select_bird"

    # Select Power 11 bird
    actions = get_actions(state)
    assert f"select_bird_{power_11_bird.id}" in actions

    state = transition_state(state, f"select_bird_{power_11_bird.id}")

    # Verify Power 11 was executed (predator power draws from deck and tucks/discards)
    # Stack should be empty
    assert len(state.action_data.execution_stack) == 0


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
    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

    # Cannot activate (only skip available)
    actions = get_actions(state)
    assert "activate_power" not in actions
    assert "skip_power" in actions


def test_power_14_self_repeat_prevented():
    """Test Power 14 cannot repeat itself or other Power 14 birds."""
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

    # Place both in same habitat (only power 14 birds)
    state.players[0].board[0][0].bird = power_14_bird_1
    state.players[0].board[0][1].bird = power_14_bird_2

    activating_spot = state.players[0].board[0][0]
    setup_power_queue(state, power_14_bird_1, power_14_data_1, activating_spot)

    # Power 14 cannot repeat other power 14 birds, so activate_power should not be available
    actions = get_actions(state)
    assert (
        "activate_power" not in actions
    ), "Power 14 should not be activatable when only other Power 14 birds exist"
    assert "skip_power" in actions, "skip_power should be the only option"


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
    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

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
    white_bird = None

    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and bird.id != power_14_bird.id:
            if power.get("color") == "white" and not white_bird:
                white_bird = bird
                break

    assert white_bird, "Should find white power bird"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place power 14 bird and white bird in same habitat
    state.players[0].board[0][0].bird = power_14_bird
    state.players[0].board[0][2].bird = white_bird

    activating_spot = state.players[0].board[0][0]

    # Find a brown bird whose power can actually execute in this state
    brown_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and bird.id != power_14_bird.id and power.get("color") == "brown":
            # Skip other power 14 birds
            if power.get("data", {}).get("id") == 14:
                continue
            # Temporarily place to test if power can execute
            state.players[0].board[0][1].bird = bird
            power_entry_candidate = {
                "bird_id": bird.id,
                "spot": state.players[0].board[0][1],
                "power_data": power,
                "player_index": 0,
            }
            if can_execute_power(state, power_entry_candidate):
                brown_bird = bird
                break
            state.players[0].board[0][1].bird = None

    assert brown_bird, "Should find executable brown power bird"

    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

    # Execute Power 14
    state = transition_state(state, "activate_power")

    # Verify only brown bird is selectable
    actions = get_actions(state)
    assert f"select_bird_{brown_bird.id}" in actions
    assert f"select_bird_{white_bird.id}" not in actions


def test_power_14_validation():
    """Test Power 14 validation works correctly."""

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

    # Find brown power bird whose power can actually execute
    brown_power_bird = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("color") == "brown" and bird.id != power_14_bird.id:
            # Skip other power 14 birds
            if power.get("data", {}).get("id") == 14:
                continue
            # Temporarily place to test if power can execute
            state.players[0].board[0][1].bird = bird
            power_entry_candidate = {
                "bird_id": bird.id,
                "spot": state.players[0].board[0][1],
                "power_data": power,
                "player_index": 0,
            }
            if can_execute_power(state, power_entry_candidate):
                brown_power_bird = bird
                break
            state.players[0].board[0][1].bird = None

    assert brown_power_bird, "Should find bird with executable brown power"

    # Valid when executable brown power bird exists in habitat
    assert can_execute_power(state, power_entry)


def test_power_14_repeat_power_with_subphase():
    """Test Power 14 repeating a power that has its own sub-phase (Power 17).

    This tests that after selecting a bird to repeat, if the repeated power
    sets up a sub-phase (like Power 17's card selection), the action generator
    correctly uses the execution stack to find the right power's choices.
    """
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

    # Find Power 17 bird (tuck card from hand)
    power_17_bird = None
    power_17_data = None
    for bird in all_birds:
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 17:
            power_17_bird = bird
            power_17_data = power
            break

    assert power_17_bird, "Should find Power 17 bird"

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Ensure player has at least 1 card in hand (needed for Power 17)
    if len(state.players[0].bird_hand) < 1:
        state.players[0].bird_hand.append(state.bird_deck.pop())

    # Place both birds in same habitat (forest)
    state.players[0].board[0][0].bird = power_14_bird
    state.players[0].board[0][1].bird = power_17_bird

    activating_spot = state.players[0].board[0][0]
    setup_power_queue(state, power_14_bird, power_14_data, activating_spot)

    # Execute Power 14
    actions = get_actions(state)
    assert "activate_power" in actions
    state = transition_state(state, "activate_power")

    # Should be in Power 14's bird selection phase
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "select_bird"

    # Verify Power 17 bird is selectable
    actions = get_actions(state)
    assert f"select_bird_{power_17_bird.id}" in actions

    # Select Power 17 bird - this triggers Power 17 which sets up select_card phase
    state = transition_state(state, f"select_bird_{power_17_bird.id}")

    # Power 17 should now be on the stack with its card selection phase
    # Power 14 should have popped itself
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].power_id == 17
    assert (
        state.action_data.execution_stack[0].phase == "select_card"
    ), f"Expected phase='select_card', got '{state.action_data.execution_stack[0].phase}'"

    # The action generator now correctly uses the execution stack to find Power 17's choices
    actions = get_actions(state)
    assert len(actions) > 0, (
        f"Should have tuck_card actions for Power 17, but got empty. "
        f"phase={state.action_data.execution_stack[0].phase if state.action_data.execution_stack else 'no stack'}, "
        f"player hand size={len(state.players[0].bird_hand)}"
    )
    assert any(
        a.startswith("tuck_card_") for a in actions
    ), f"Expected tuck_card actions, got: {actions}"

    # Complete Power 17 by tucking a card
    tuck_action = [a for a in actions if a.startswith("tuck_card_")][0]
    state = transition_state(state, tuck_action)

    # Verify cleanup - power should be done or in food selection
    if state.action_data.execution_stack:
        # If Power 17 has multiple types, it might be in food selection
        assert state.action_data.execution_stack[0].phase == "select_food"
    else:
        # Power completed
        pass


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

    test_power_14_repeat_power_with_subphase()
    print("✓ test_power_14_repeat_power_with_subphase passed")

    print("\n✅ All Power 14 tests passed!")
