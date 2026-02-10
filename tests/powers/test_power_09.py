"""Comprehensive end-to-end tests for Power 9: Move bird to another habitat."""

from game.core import (
    initiate_state,
    GamePhase,
    get_bird_power,
    get_bird_card,
    BIRD_REGISTRY,
    init_registries,
    SimpleAction,
    NameAction,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import place_bird_on_board, setup_power_execution


def find_bird_with_power_9(min_habitats=2):
    """Find a bird ID with Power 9 and at least min_habitats."""
    init_registries()
    for bird_id, card in BIRD_REGISTRY.items():
        power_data = get_bird_power(bird_id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 9:
            if len(card.habitats) >= min_habitats:
                return bird_id, power_data
    return None, None


def test_power_9_bird_solo_in_row():
    """Test bird alone in habitat moving to another habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9 that has multiple habitats
    bird_id, power_data = find_bird_with_power_9(min_habitats=2)
    assert bird_id is not None, "Should find bird with power 9 and 2+ habitats"

    # Get bird card to check habitats
    bird_card = get_bird_card(bird_id)
    assert bird_card
    assert len(bird_card.habitats) >= 2, "Bird should have at least 2 habitats"

    # Place bird in first habitat (forest row, col 0)
    current_habitat = bird_card.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    place_bird_on_board(state, 0, current_row, 0, bird_id)
    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_execution(
        state, 9, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Record initial position
    initial_col = activating_spot.col
    initial_row = activating_spot.row

    # Verify can activate
    actions = get_actions(state)
    assert SimpleAction("activate_power") in actions

    # Execute activation
    state = transition_state(state, SimpleAction("activate_power"))

    # Check if auto-completed or requires choice
    if len(state.action_data.execution_stack) > 0:
        # Multiple valid habitats - requires selection
        assert state.action_data.execution_stack[-1].phase == "select_habitat"

        # Verify habitat selection actions available
        actions = get_actions(state)
        habitat_actions = [
            a
            for a in actions
            if isinstance(a, NameAction) and a.type == "select_habitat"
        ]
        assert len(habitat_actions) >= 1, "Should have at least one habitat choice"

        # Select the first available habitat
        selected_action = habitat_actions[0]
        target_habitat = selected_action.name

        # Execute habitat selection
        state = transition_state(state, selected_action)

        # Verify bird moved to target habitat (compare by ID)
        target_row = habitat_map[target_habitat]
        bird = state.players[0].board[target_row][0].bird
        assert bird is not None
        assert bird.id == bird_id
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

    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place power 9 bird in rightmost position (col 2) of its first habitat row
    current_habitat = bird_card.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    place_bird_on_board(state, 0, current_row, 2, bird_id)

    # Place two other birds to the left (col 0 and col 1)
    other_bird_id_1 = state.players[0].bird_hand[0]
    other_bird_id_2 = state.players[0].bird_hand[1]
    place_bird_on_board(state, 0, current_row, 0, other_bird_id_1)
    place_bird_on_board(state, 0, current_row, 1, other_bird_id_2)

    activating_spot = state.players[0].board[current_row][2]

    # Setup power activation
    setup_power_execution(
        state, 9, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify can activate (bird is rightmost)
    actions = get_actions(state)
    assert SimpleAction("activate_power") in actions

    # Execute activation
    state = transition_state(state, SimpleAction("activate_power"))

    # Should have habitat selection choices
    if len(state.action_data.execution_stack) > 0:
        assert state.action_data.execution_stack[-1].phase == "select_habitat"

        actions = get_actions(state)
        habitat_actions = [
            a
            for a in actions
            if isinstance(a, NameAction) and a.type == "select_habitat"
        ]

        # Select grassland if available, otherwise first option
        grassland_action = NameAction("select_habitat", "grassland")
        if grassland_action in actions:
            selected_action = grassland_action
        else:
            selected_action = habitat_actions[0]

        target_habitat = selected_action.name
        state = transition_state(state, selected_action)

        # Verify bird moved to leftmost spot (col 0) in target habitat (compare by ID)
        target_row = habitat_map[target_habitat]
        bird = state.players[0].board[target_row][0].bird
        assert bird is not None
        assert bird.id == bird_id

    # Verify old spot is empty
    assert state.players[0].board[current_row][2].bird is None

    # Verify other birds in original row unchanged (compare by ID)
    bird_0 = state.players[0].board[current_row][0].bird
    bird_1 = state.players[0].board[current_row][1].bird
    assert bird_0 is not None and bird_0.id == other_bird_id_1
    assert bird_1 is not None and bird_1.id == other_bird_id_2

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_9_bird_not_rightmost():
    """Test that power cannot activate when bird is not rightmost in habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9
    bird_id, power_data = find_bird_with_power_9(min_habitats=2)
    assert bird_id is not None

    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place power 9 bird at col 0 (NOT rightmost)
    current_habitat = bird_card.habitats[0]
    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_row = habitat_map[current_habitat]

    place_bird_on_board(state, 0, current_row, 0, bird_id)

    # Place another bird to the right (col 1) to make power 9 bird NOT rightmost
    other_bird_id = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, current_row, 1, other_bird_id)

    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_execution(
        state, 9, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate (bird is not rightmost)
    actions = get_actions(state)
    assert SimpleAction("activate_power") not in actions

    # Skip power should be available
    if SimpleAction("skip_power") in actions:
        state = transition_state(state, SimpleAction("skip_power"))

    # Verify bird position unchanged (compare by ID)
    bird_0 = state.players[0].board[current_row][0].bird
    bird_1 = state.players[0].board[current_row][1].bird
    assert bird_0 is not None and bird_0.id == bird_id
    assert bird_1 is not None and bird_1.id == other_bird_id


def test_power_9_all_other_rows_full():
    """Test that power cannot activate when all other habitats are full."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 9 that has all 3 habitats
    bird_id, power_data = find_bird_with_power_9(min_habitats=3)
    assert bird_id is not None

    bird_card = get_bird_card(bird_id)
    assert bird_card
    assert len(bird_card.habitats) == 3, "Bird should have all 3 habitats for this test"

    # Place power 9 bird in wetland row, rightmost position (col 0, solo)
    current_row = 2  # wetland

    place_bird_on_board(state, 0, current_row, 0, bird_id)

    # Fill all 5 spots in forest row (row 0) - use bird IDs from deck
    for col in range(5):
        filler_bird_id = state.bird_deck[col]
        place_bird_on_board(state, 0, 0, col, filler_bird_id)

    # Fill all 5 spots in grassland row (row 1)
    for col in range(5):
        filler_bird_id = state.bird_deck[col + 5]
        place_bird_on_board(state, 0, 1, col, filler_bird_id)

    activating_spot = state.players[0].board[current_row][0]

    # Setup power activation
    setup_power_execution(
        state, 9, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate (no valid target habitats with empty spots)
    actions = get_actions(state)
    assert SimpleAction("activate_power") not in actions

    # Skip power should be available
    if SimpleAction("skip_power") in actions:
        state = transition_state(state, SimpleAction("skip_power"))

    # Verify bird remains in original position (compare by ID)
    bird = state.players[0].board[current_row][0].bird
    assert bird is not None
    assert bird.id == bird_id
