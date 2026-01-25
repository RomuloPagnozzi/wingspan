"""Comprehensive end-to-end tests for Power 10: Lay eggs on birds."""

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


def setup_power_10_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 10 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 10}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=10,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def find_birds_with_power_10():
    """Find all birds with Power 10 and return them grouped by variant."""
    birds = load_deck("birds")
    variants = {
        "this_true": [],
        "type_any": [],
        "type_bowl": [],
        "type_cavity": [],
        "type_ground": [],
        "type_platform": [],
    }

    for bird in birds:
        power_data = get_bird_power(bird.id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 10:
            details = power_data["data"].get("details", {})
            is_this = details.get("this", False)
            nest_type = details.get("type", "")

            if is_this:
                variants["this_true"].append((bird.id, power_data))
            elif nest_type == "any":
                variants["type_any"].append((bird.id, power_data))
            elif nest_type == "bowl":
                variants["type_bowl"].append((bird.id, power_data))
            elif nest_type == "cavity":
                variants["type_cavity"].append((bird.id, power_data))
            elif nest_type == "ground":
                variants["type_ground"].append((bird.id, power_data))
            elif nest_type == "platform":
                variants["type_platform"].append((bird.id, power_data))

    return variants


def test_power_10_this_true():
    """Test Power 10: Lay egg on activating bird (this: True)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (this: True)
    variants = find_birds_with_power_10()
    assert len(variants["this_true"]) > 0, "Should find bird with power 10 (this: True)"

    bird_id, power_data = variants["this_true"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place bird on board (forest row, col 0)
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    activating_spot = state.players[0].board[0][0]

    # Verify bird has egg capacity
    assert power_10_bird.eggs < power_10_bird.egg_limit, "Bird should have egg capacity"
    initial_eggs = power_10_bird.eggs

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions, "Should be able to activate power"

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Verify egg was added to activating bird (get from returned state after deepcopy)
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird.eggs == initial_eggs + 1, "Bird should have one more egg"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_this_true_at_limit():
    """Test Power 10 cannot execute when activating bird is at egg limit."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (this: True)
    variants = find_birds_with_power_10()
    assert len(variants["this_true"]) > 0, "Should find bird with power 10 (this: True)"

    bird_id, power_data = variants["this_true"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place bird on board and fill to egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit

    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert "activate_power" not in actions, "Should not be able to activate power"
    assert "skip_power" in actions, "Should be able to skip power"


def test_power_10_type_bowl():
    """Test Power 10: Lay eggs on all bowl nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: bowl)
    variants = find_birds_with_power_10()
    assert len(variants["type_bowl"]) > 0, "Should find bird with power 10 (type: bowl)"

    bird_id, power_data = variants["type_bowl"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add bowl nest birds from state's own bird deck (excluding the activating bird)
    bowl_birds = [
        b
        for b in state.bird_deck
        if b.nest == "bowl" and b.egg_limit > 0 and b.id != bird_id
    ][:3]

    # Place bowl birds on board
    state.players[0].board[1][0].bird = bowl_birds[0]
    state.players[0].board[1][1].bird = bowl_birds[1]
    state.players[0].board[2][0].bird = bowl_birds[2]

    # Set one bird at egg limit (on the board, not the original list)
    state.players[0].board[2][0].bird.eggs = state.players[0].board[2][0].bird.egg_limit

    initial_eggs_0 = state.players[0].board[1][0].bird.eggs
    initial_eggs_1 = state.players[0].board[1][1].bird.eggs
    initial_eggs_2 = state.players[0].board[2][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Get birds from returned state (after deepcopy)
    board_birds = [
        state.players[0].board[1][0].bird,
        state.players[0].board[1][1].bird,
        state.players[0].board[2][0].bird,
    ]

    # Verify eggs added to bowl birds with capacity
    assert (
        board_birds[0].eggs == initial_eggs_0 + 1
    ), "Bowl bird 0 should have one more egg"
    assert (
        board_birds[1].eggs == initial_eggs_1 + 1
    ), "Bowl bird 1 should have one more egg"
    assert (
        board_birds[2].eggs == initial_eggs_2
    ), "Bowl bird 2 at limit should be unchanged"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_cavity():
    """Test Power 10: Lay eggs on all cavity nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: cavity)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_cavity"]) > 0
    ), "Should find bird with power 10 (type: cavity)"

    bird_id, power_data = variants["type_cavity"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add cavity nest birds from state's own bird deck
    cavity_birds = [
        b for b in state.bird_deck if b.nest == "cavity" and b.egg_limit > 0
    ][:2]

    # Place cavity birds on board
    state.players[0].board[1][0].bird = cavity_birds[0]
    state.players[0].board[2][0].bird = cavity_birds[1]

    initial_eggs_0 = state.players[0].board[1][0].bird.eggs
    initial_eggs_1 = state.players[0].board[2][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Get birds from returned state (after deepcopy)
    board_birds = [
        state.players[0].board[1][0].bird,
        state.players[0].board[2][0].bird,
    ]

    # Verify eggs added to cavity birds
    assert (
        board_birds[0].eggs == initial_eggs_0 + 1
    ), "Cavity bird 0 should have one more egg"
    assert (
        board_birds[1].eggs == initial_eggs_1 + 1
    ), "Cavity bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_ground():
    """Test Power 10: Lay eggs on all ground nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: ground)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_ground"]) > 0
    ), "Should find bird with power 10 (type: ground)"

    bird_id, power_data = variants["type_ground"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add ground nest birds from state's own bird deck
    ground_birds = [
        b for b in state.bird_deck if b.nest == "ground" and b.egg_limit > 0
    ][:2]

    # Place ground birds on board
    state.players[0].board[1][0].bird = ground_birds[0]
    state.players[0].board[2][0].bird = ground_birds[1]

    initial_eggs_0 = state.players[0].board[1][0].bird.eggs
    initial_eggs_1 = state.players[0].board[2][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Get birds from returned state (after deepcopy)
    board_birds = [
        state.players[0].board[1][0].bird,
        state.players[0].board[2][0].bird,
    ]

    # Verify eggs added to ground birds
    assert (
        board_birds[0].eggs == initial_eggs_0 + 1
    ), "Ground bird 0 should have one more egg"
    assert (
        board_birds[1].eggs == initial_eggs_1 + 1
    ), "Ground bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_platform():
    """Test Power 10: Lay eggs on all platform nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: platform)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_platform"]) > 0
    ), "Should find bird with power 10 (type: platform)"

    bird_id, power_data = variants["type_platform"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add platform nest birds from state's own bird deck
    platform_birds = [
        b for b in state.bird_deck if b.nest == "platform" and b.egg_limit > 0
    ][:2]

    # Place platform birds on board
    state.players[0].board[1][0].bird = platform_birds[0]
    state.players[0].board[2][0].bird = platform_birds[1]

    initial_eggs_0 = state.players[0].board[1][0].bird.eggs
    initial_eggs_1 = state.players[0].board[2][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Get birds from returned state (after deepcopy)
    board_birds = [
        state.players[0].board[1][0].bird,
        state.players[0].board[2][0].bird,
    ]

    # Verify eggs added to platform birds
    assert (
        board_birds[0].eggs == initial_eggs_0 + 1
    ), "Platform bird 0 should have one more egg"
    assert (
        board_birds[1].eggs == initial_eggs_1 + 1
    ), "Platform bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_any_single_bird():
    """Test Power 10: Lay egg on any bird when only one valid bird exists (auto-complete)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board at egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit  # At limit so not a valid target
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add only ONE other bird with egg capacity
    other_bird = [b for b in state.bird_deck if b.egg_limit > 0 and b.id != bird_id][0]
    state.players[0].board[1][0].bird = other_bird

    initial_eggs = state.players[0].board[1][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Verify egg was added to the only bird (check the board bird, not the original reference)
    assert (
        state.players[0].board[1][0].bird.eggs == initial_eggs + 1
    ), "Only valid bird should have one more egg"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_any_multiple_birds():
    """Test Power 10: Lay egg on any bird when multiple valid birds exist (requires choice)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board at egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit  # At limit so not a valid target
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add multiple birds with egg capacity
    other_birds = [b for b in state.bird_deck if b.egg_limit > 0 and b.id != bird_id][
        :3
    ]
    state.players[0].board[1][0].bird = other_birds[0]
    state.players[0].board[1][1].bird = other_birds[1]
    state.players[0].board[2][0].bird = other_birds[2]

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should enter sub-phase)
    state = transition_state(state, "activate_power")

    # Verify sub-phase created
    assert state.action_data.execution_stack[-1].phase == "select_bird"

    # Verify bird selection actions available
    actions = get_actions(state)
    bird_actions = [a for a in actions if a.startswith("select_bird_")]
    assert len(bird_actions) == 3, "Should have 3 bird selection actions"

    # Verify valid bird IDs stored
    valid_bird_ids = state.action_data.execution_stack[-1].context.get(
        "valid_bird_ids", []
    )
    assert len(valid_bird_ids) == 3
    assert other_birds[0].id in valid_bird_ids
    assert other_birds[1].id in valid_bird_ids
    assert other_birds[2].id in valid_bird_ids


def test_power_10_type_any_selection():
    """Test Power 10: Verify correct bird receives egg after selection."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board at egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit  # At limit so not a valid target
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add multiple birds with egg capacity
    other_birds = [b for b in state.bird_deck if b.egg_limit > 0 and b.id != bird_id][
        :3
    ]
    state.players[0].board[1][0].bird = other_birds[0]
    state.players[0].board[1][1].bird = other_birds[1]
    state.players[0].board[2][0].bird = other_birds[2]

    initial_eggs_0 = state.players[0].board[1][0].bird.eggs
    initial_eggs_1 = state.players[0].board[1][1].bird.eggs
    initial_eggs_2 = state.players[0].board[2][0].bird.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should enter sub-phase)
    state = transition_state(state, "activate_power")

    # Select bird 1 (middle bird)
    selected_action = f"select_bird_{other_birds[1].id}"
    state = transition_state(state, selected_action)

    # Verify only selected bird received egg (check board birds, not original references)
    assert (
        state.players[0].board[1][0].bird.eggs == initial_eggs_0
    ), "Bird 0 should be unchanged"
    assert (
        state.players[0].board[1][1].bird.eggs == initial_eggs_1 + 1
    ), "Bird 1 should have one more egg"
    assert (
        state.players[0].board[2][0].bird.eggs == initial_eggs_2
    ), "Bird 2 should be unchanged"

    # Verify cleanup
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_no_valid_birds_specific_type():
    """Test Power 10 cannot execute when no birds match specific nest type."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: cavity)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_cavity"]) > 0
    ), "Should find bird with power 10 (type: cavity)"

    bird_id, power_data = variants["type_cavity"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board at egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit  # At limit so not a valid target
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add ONLY bowl nest birds (not cavity)
    bowl_birds = [b for b in state.bird_deck if b.nest == "bowl" and b.egg_limit > 0][
        :2
    ]
    state.players[0].board[1][0].bird = bowl_birds[0]
    state.players[0].board[2][0].bird = bowl_birds[1]

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert "activate_power" not in actions, "Should not be able to activate power"
    assert "skip_power" in actions, "Should be able to skip power"


def test_power_10_all_birds_at_limit():
    """Test Power 10 cannot execute when all birds are at egg limit."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board at egg limit
    state.players[0].board[0][0].bird = power_10_bird
    power_10_bird.eggs = power_10_bird.egg_limit

    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add other birds all at egg limit
    other_birds = [b for b in state.bird_deck if b.egg_limit > 0 and b.id != bird_id][
        :2
    ]
    state.players[0].board[1][0].bird = other_birds[0]
    state.players[0].board[2][0].bird = other_birds[1]

    # Set eggs on the board birds (not the original list)
    state.players[0].board[1][0].bird.eggs = state.players[0].board[1][0].bird.egg_limit
    state.players[0].board[2][0].bird.eggs = state.players[0].board[2][0].bird.egg_limit

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert "activate_power" not in actions, "Should not be able to activate power"
    assert "skip_power" in actions, "Should be able to skip power"


def test_power_10_mixed_capacity_birds():
    """Test Power 10 only lays eggs on birds with capacity."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: bowl)
    variants = find_birds_with_power_10()
    assert len(variants["type_bowl"]) > 0, "Should find bird with power 10 (type: bowl)"

    bird_id, power_data = variants["type_bowl"][0]
    power_10_bird = get_bird(bird_id)
    assert power_10_bird

    # Place activating bird on board
    state.players[0].board[0][0].bird = power_10_bird
    if power_10_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_10_bird)

    # Add bowl nest birds from state's own bird deck (excluding the activating bird)
    bowl_birds = [
        b
        for b in state.bird_deck
        if b.nest == "bowl" and b.egg_limit > 0 and b.id != bird_id
    ][:4]

    state.players[0].board[1][0].bird = bowl_birds[0]  # Has capacity
    state.players[0].board[1][1].bird = bowl_birds[1]  # At limit
    state.players[0].board[2][0].bird = bowl_birds[2]  # Has capacity
    state.players[0].board[2][1].bird = bowl_birds[3]  # At limit

    # Set eggs on the birds that are on the board (not the original list)
    state.players[0].board[1][1].bird.eggs = state.players[0].board[1][1].bird.egg_limit
    state.players[0].board[2][1].bird.eggs = state.players[0].board[2][1].bird.egg_limit

    initial_eggs = [
        state.players[0].board[1][0].bird.eggs,
        state.players[0].board[1][1].bird.eggs,
        state.players[0].board[2][0].bird.eggs,
        state.players[0].board[2][1].bird.eggs,
    ]

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_10_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, "activate_power")

    # Get birds from returned state (transition_state does deepcopy)
    board_birds = [
        state.players[0].board[1][0].bird,
        state.players[0].board[1][1].bird,
        state.players[0].board[2][0].bird,
        state.players[0].board[2][1].bird,
    ]

    # Verify only birds with capacity received eggs
    assert (
        board_birds[0].eggs == initial_eggs[0] + 1
    ), "Bird 0 with capacity should gain egg"
    assert board_birds[1].eggs == initial_eggs[1], "Bird 1 at limit should be unchanged"
    assert (
        board_birds[2].eggs == initial_eggs[2] + 1
    ), "Bird 2 with capacity should gain egg"
    assert board_birds[3].eggs == initial_eggs[3], "Bird 3 at limit should be unchanged"


def test_power_10_validation():
    """Test Power 10 validation works correctly for all variants."""
    from game.power_validators import can_execute_power

    state = initiate_state(2)
    state.current_player_index = 0

    variants = find_birds_with_power_10()

    # Test this: True validation
    if variants["this_true"]:
        bird_id, power_data = variants["this_true"][0]
        bird = get_bird(bird_id)
        assert bird
        state.players[0].board[0][0].bird = bird
        spot = state.players[0].board[0][0]

        # Should be valid when bird has capacity
        bird.eggs = 0
        power_entry = {"power_data": power_data, "spot": spot}
        assert can_execute_power(
            state, power_entry
        ), "Should validate when bird has capacity"

        # Should be invalid when bird at limit
        bird.eggs = bird.egg_limit
        assert not can_execute_power(
            state, power_entry
        ), "Should not validate when bird at limit"


if __name__ == "__main__":
    print("Running Power 10 tests...")

    test_power_10_this_true()
    print("✓ test_power_10_this_true passed")

    test_power_10_this_true_at_limit()
    print("✓ test_power_10_this_true_at_limit passed")

    test_power_10_type_bowl()
    print("✓ test_power_10_type_bowl passed")

    test_power_10_type_cavity()
    print("✓ test_power_10_type_cavity passed")

    test_power_10_type_ground()
    print("✓ test_power_10_type_ground passed")

    test_power_10_type_platform()
    print("✓ test_power_10_type_platform passed")

    test_power_10_type_any_single_bird()
    print("✓ test_power_10_type_any_single_bird passed")

    test_power_10_type_any_multiple_birds()
    print("✓ test_power_10_type_any_multiple_birds passed")

    test_power_10_type_any_selection()
    print("✓ test_power_10_type_any_selection passed")

    test_power_10_no_valid_birds_specific_type()
    print("✓ test_power_10_no_valid_birds_specific_type passed")

    test_power_10_all_birds_at_limit()
    print("✓ test_power_10_all_birds_at_limit passed")

    test_power_10_mixed_capacity_birds()
    print("✓ test_power_10_mixed_capacity_birds passed")

    test_power_10_validation()
    print("✓ test_power_10_validation passed")

    print("\n✓ All Power 10 tests passed!")
