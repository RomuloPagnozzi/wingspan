"""Comprehensive end-to-end tests for Power 9: Move bird to another habitat."""

import sys

sys.path.append(".")

from game.data import (
    initiate_state,
    GamePhase,
    load_deck,
    get_bird_power,
    get_bird,
    ActionData,
    QueuedPower,
)
from game.engine import transition_state
from game.actions import get_actions


def setup_power_9_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 9 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 9}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=9,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def find_bird_with_power_9(min_habitats=2):
    """Find a bird ID with Power 9 and at least min_habitats."""
    birds = load_deck("birds")
    for bird in birds:
        power_data = get_bird_power(bird.id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 9:
            if len(bird.habitats) >= min_habitats:
                return bird.id, power_data
    return None, None


def test_power_9_bird_solo_in_row():
    """Test bird alone in habitat moving to another habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9 that has multiple habitats
    bird_id, power_data = find_bird_with_power_9(min_habitats=2)
    assert bird_id is not None, "Should find bird with power 9 and 2+ habitats"

    # Get bird and place on board
    power_9_bird = get_bird(bird_id)
    assert power_9_bird
    assert len(power_9_bird.habitats) >= 2, "Bird should have at least 2 habitats"

    # Place bird in first habitat (forest row, col 0)
    current_habitat = power_9_bird.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    state.players[0].board[current_row][0].bird = power_9_bird
    if power_9_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_9_bird)

    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_9_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial position
    initial_col = activating_spot.col
    initial_row = activating_spot.row

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation
    state = transition_state(state, "activate_power")

    # Check if auto-completed or requires choice
    if len(state.action_data.execution_stack) > 0:
        # Multiple valid habitats - requires selection
        assert state.action_data.execution_stack[-1].phase == "select_habitat"

        # Verify habitat selection actions available
        actions = get_actions(state)
        habitat_actions = [a for a in actions if a.startswith("select_habitat_")]
        assert len(habitat_actions) >= 1, "Should have at least one habitat choice"

        # Select the first available habitat
        selected_action = habitat_actions[0]
        target_habitat = selected_action.split("_")[2]

        # Execute habitat selection
        state = transition_state(state, selected_action)

        # Verify bird moved to target habitat
        target_row = habitat_map[target_habitat]
        assert state.players[0].board[target_row][0].bird == power_9_bird
    else:
        # Auto-completed - find where bird moved
        bird_found = False
        for row_idx, row in enumerate(state.players[0].board):
            for spot in row:
                if spot.bird and spot.bird.id == bird_id:
                    bird_found = True
                    # Should be in a different row than initial
                    assert (
                        row_idx != initial_row
                    ), "Bird should have moved to different habitat"
                    break
            if bird_found:
                break
        assert bird_found, "Bird should be found on board after move"

    # Verify old spot is empty
    assert state.players[0].board[initial_row][initial_col].bird is None

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_9_full_row_bird_last():
    """Test bird that is rightmost in a full row moving to another habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9 that has multiple habitats
    bird_id, power_data = find_bird_with_power_9(min_habitats=2)
    assert bird_id is not None

    power_9_bird = get_bird(bird_id)

    # Place power 9 bird in rightmost position (col 2) of forest row
    assert power_9_bird
    current_habitat = power_9_bird.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    state.players[0].board[current_row][2].bird = power_9_bird
    if power_9_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_9_bird)

    # Place two other birds to the left (col 0 and col 1)
    other_bird_1 = state.players[0].bird_hand[0]
    other_bird_2 = state.players[0].bird_hand[1]
    state.players[0].board[current_row][0].bird = other_bird_1
    state.players[0].board[current_row][1].bird = other_bird_2

    activating_spot = state.players[0].board[current_row][2]

    # Setup power activation
    setup_power_9_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify can activate (bird is rightmost)
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation
    state = transition_state(state, "activate_power")

    # Should have habitat selection choices
    if len(state.action_data.execution_stack) > 0:
        assert state.action_data.execution_stack[-1].phase == "select_habitat"

        actions = get_actions(state)
        habitat_actions = [a for a in actions if a.startswith("select_habitat_")]

        # Select grassland if available, otherwise first option
        if any("grassland" in a for a in habitat_actions):
            selected_action = "select_habitat_grassland"
        else:
            selected_action = habitat_actions[0]

        target_habitat = selected_action.split("_")[2]
        state = transition_state(state, selected_action)

        # Verify bird moved to leftmost spot (col 0) in target habitat
        target_row = habitat_map[target_habitat]
        assert state.players[0].board[target_row][0].bird == power_9_bird

    # Verify old spot is empty
    assert state.players[0].board[current_row][2].bird is None

    # Verify other birds in original row unchanged
    assert state.players[0].board[current_row][0].bird == other_bird_1
    assert state.players[0].board[current_row][1].bird == other_bird_2

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0
    assert len(state.action_data.execution_stack) == 0


def test_power_9_bird_not_rightmost():
    """Test that power cannot activate when bird is not rightmost in habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9
    bird_id, power_data = find_bird_with_power_9(min_habitats=2)
    assert bird_id is not None

    power_9_bird = get_bird(bird_id)

    # Place power 9 bird at col 0 (NOT rightmost)
    assert power_9_bird
    current_habitat = power_9_bird.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    state.players[0].board[current_row][0].bird = power_9_bird
    if power_9_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_9_bird)

    # Place another bird to the right (col 1) to make power 9 bird NOT rightmost
    other_bird = state.players[0].bird_hand[0]
    state.players[0].board[current_row][1].bird = other_bird

    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_9_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate (bird is not rightmost)
    actions = get_actions(state)
    assert "activate_power" not in actions

    # Skip power should be available
    if "skip_power" in actions:
        state = transition_state(state, "skip_power")

    # Verify bird position unchanged
    assert state.players[0].board[current_row][0].bird == power_9_bird
    assert state.players[0].board[current_row][1].bird == other_bird


def test_power_9_all_other_rows_full():
    """Test that power cannot activate when all other habitats are full."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9 that has all 3 habitats
    bird_id, power_data = find_bird_with_power_9(min_habitats=3)
    assert bird_id is not None

    power_9_bird = get_bird(bird_id)
    assert power_9_bird
    assert (
        len(power_9_bird.habitats) == 3
    ), "Bird should have all 3 habitats for this test"

    # Place power 9 bird in wetland row, rightmost position (col 0, solo)
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = 2  # wetland

    state.players[0].board[current_row][0].bird = power_9_bird
    if power_9_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_9_bird)

    # Fill all 5 spots in forest row (row 0) - use dummy birds from deck
    from game.data import load_deck

    deck_birds = load_deck("birds")

    for col in range(5):
        state.players[0].board[0][col].bird = deck_birds[col]

    # Fill all 5 spots in grassland row (row 1)
    for col in range(5):
        state.players[0].board[1][col].bird = deck_birds[col + 5]

    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_9_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate (no valid target habitats with empty spots)
    actions = get_actions(state)
    assert "activate_power" not in actions

    # Skip power should be available
    if "skip_power" in actions:
        state = transition_state(state, "skip_power")

    # Verify bird remains in original position
    assert state.players[0].board[current_row][0].bird == power_9_bird
