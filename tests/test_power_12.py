"""Comprehensive end-to-end tests for Power 12: Play additional bird in habitat."""

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


def setup_power_12_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 12 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 12}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=12,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def find_birds_with_power_12():
    """Find all birds with Power 12 grouped by habitat variant."""
    birds = load_deck("birds")
    variants = {
        "forest": [],
        "grassland": [],
        "wetland": [],
        "this": [],
    }

    for bird in birds:
        power_data = get_bird_power(bird.id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 12:
            details = power_data["data"].get("details", {})
            habitat = details.get("habitat", "")

            if habitat in variants:
                variants[habitat].append((bird.id, power_data))

    return variants


def test_power_12_forest_basic():
    """Test Power 12 with habitat=forest: basic successful placement."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Give player plenty of resources
    state.players[0].food = {
        "invertebrate": 5,
        "seed": 5,
        "fish": 5,
        "fruit": 5,
        "rodent": 5,
    }

    variants = find_birds_with_power_12()
    assert len(variants["forest"]) > 0, "Should find bird with power 12 (forest)"

    bird_id, power_data = variants["forest"][0]
    power_12_bird = get_bird(bird_id)
    assert power_12_bird

    # Place power 12 bird on board with eggs
    state.players[0].board[0][0].bird = power_12_bird
    power_12_bird.eggs = 5  # Give it eggs to pay for next bird placement
    if power_12_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_12_bird)

    activating_spot = state.players[0].board[0][0]

    # Find a bird that can be played in forest
    birds = load_deck("birds")
    forest_bird = [b for b in birds if "forest" in b.habitats][0]
    state.players[0].bird_hand.append(forest_bird)

    # Setup power activation
    setup_power_12_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    initial_cubes = state.players[0].action_cubes

    # Verify can activate
    actions = get_actions(state)
    if "activate_power" not in actions:
        print(f"Available actions: {actions}")
        print(f"Power 12 bird: {power_12_bird}")
        print(f"Forest bird: {forest_bird}")
        print(f"Player hand: {[b.id for b in state.players[0].bird_hand]}")
        print(f"Player food: {state.players[0].food}")
    assert "activate_power" in actions, "Should be able to activate power"

    # Execute activation - should transition to PLAY_BIRD phase
    state = transition_state(state, "activate_power")
    if state.game_phase != GamePhase.PLAY_BIRD:
        print(f"Got phase: {state.game_phase}, expected PLAY_BIRD")
        print(f"action_data: {state.action_data}")
    assert (
        state.game_phase == GamePhase.PLAY_BIRD
    ), "Should transition to PLAY_BIRD phase"

    # Verify only forest birds at forest spots appear in actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if a.startswith("play_bird_")]
    assert len(play_bird_actions) > 0, "Should have at least one play_bird action"

    # All actions should be for forest row (row 0)
    for action in play_bird_actions:
        # Parse: "play_bird_123_at_0_2" → row=0
        parts = action.replace("play_bird_", "").split("_at_")
        row, col = parts[1].split("_")
        assert (
            row == "0"
        ), f"Action {action} should be for forest row (0), got row {row}"

    # Select first valid action and execute
    selected_action = play_bird_actions[0]
    state = transition_state(state, selected_action)

    # Parse the action to get bird_id and position
    parts = selected_action.replace("play_bird_", "").split("_at_")
    placed_bird_id = int(parts[0])
    row, col = parts[1].split("_")

    # Handle egg cost payment if needed
    if state.game_phase == GamePhase.PAY_EGG_COST:
        egg_actions = get_actions(state)
        state = transition_state(state, egg_actions[0])

    # Handle food cost payment if needed
    if state.game_phase == GamePhase.PAY_FOOD_COST:
        food_actions = get_actions(state)
        state = transition_state(state, food_actions[0])

    # Verify bird is on board at correct position
    placed_bird = state.players[0].board[int(row)][int(col)].bird
    assert placed_bird is not None, "Bird should be placed on board"
    if placed_bird.id != placed_bird_id:
        print(f"Expected bird ID: {placed_bird_id}")
        print(f"Actual bird ID: {placed_bird.id}")
        print(f"Actual bird: {placed_bird}")
    assert placed_bird.id == placed_bird_id, "Correct bird should be placed"
    assert int(row) == 0, "Bird should be in forest row"

    # Verify no action cube consumed
    assert (
        state.players[0].action_cubes == initial_cubes
    ), "No action cube should be consumed"

    # Verify reached end phase
    assert state.game_phase in [
        GamePhase.ACTIVATE_POWERS,
        GamePhase.MAIN_TURN,
    ], "Should complete to ACTIVATE_POWERS or MAIN_TURN"


def test_power_12_habitat_filtering():
    """Test that ONLY correct habitat/bird combinations appear in actions."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Give player plenty of resources
    state.players[0].food = {
        "invertebrate": 5,
        "seed": 5,
        "fish": 5,
        "fruit": 5,
        "rodent": 5,
    }

    variants = find_birds_with_power_12()
    assert len(variants["forest"]) > 0, "Should find bird with power 12 (forest)"

    bird_id, power_data = variants["forest"][0]
    power_12_bird = get_bird(bird_id)

    # Place power 12 bird on board with eggs
    state.players[0].board[0][0].bird = power_12_bird
    power_12_bird.eggs = 5  # Give it eggs to pay for next bird placement
    if power_12_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_12_bird)

    activating_spot = state.players[0].board[0][0]

    # Add specific test birds to hand
    all_birds = load_deck("birds")

    # Find birds with different habitat combinations
    forest_only = [b for b in all_birds if b.habitats == ["forest"]]
    grassland_only = [b for b in all_birds if b.habitats == ["grassland"]]
    forest_wetland = [b for b in all_birds if set(b.habitats) == {"forest", "wetland"}]
    grassland_wetland = [
        b for b in all_birds if set(b.habitats) == {"grassland", "wetland"}
    ]

    # Clear hand and add test birds
    state.players[0].bird_hand = []

    bird_a = forest_only[0] if forest_only else None
    bird_b = grassland_only[0] if grassland_only else None
    bird_c = forest_wetland[0] if forest_wetland else None
    bird_d = grassland_wetland[0] if grassland_wetland else None

    if bird_a:
        state.players[0].bird_hand.append(bird_a)
    if bird_b:
        state.players[0].bird_hand.append(bird_b)
    if bird_c:
        state.players[0].bird_hand.append(bird_c)
    if bird_d:
        state.players[0].bird_hand.append(bird_d)

    # Setup power activation
    setup_power_12_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Activate power
    state = transition_state(state, "activate_power")
    assert state.game_phase == GamePhase.PLAY_BIRD

    # Get play_bird actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if a.startswith("play_bird_")]

    # Parse bird IDs from actions
    bird_ids_in_actions = set()
    for action in play_bird_actions:
        parts = action.replace("play_bird_", "").split("_at_")
        bird_ids_in_actions.add(int(parts[0]))
        # Verify all actions are for forest row (row 0)
        row, col = parts[1].split("_")
        assert row == "0", f"All actions should be for forest row, got {row}"

    # Verify only forest-compatible birds appear
    if bird_a:
        assert bird_a.id in bird_ids_in_actions, "Forest-only bird should appear"
    if bird_b:
        assert (
            bird_b.id not in bird_ids_in_actions
        ), "Grassland-only bird should NOT appear"
    if bird_c:
        assert bird_c.id in bird_ids_in_actions, "Forest+wetland bird should appear"
    if bird_d:
        assert (
            bird_d.id not in bird_ids_in_actions
        ), "Grassland+wetland bird should NOT appear"


def test_power_12_this_variant():
    """Test Power 12 with habitat=this resolves to activating bird's habitat."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Give player plenty of resources
    state.players[0].food = {
        "invertebrate": 5,
        "seed": 5,
        "fish": 5,
        "fruit": 5,
        "rodent": 5,
    }

    variants = find_birds_with_power_12()
    assert len(variants["this"]) > 0, "Should find bird with power 12 (this)"

    bird_id, power_data = variants["this"][0]
    power_12_bird = get_bird(bird_id)
    assert power_12_bird

    # Place power 12 bird in grassland row (row 1) with eggs
    state.players[0].board[1][0].bird = power_12_bird
    power_12_bird.eggs = 5  # Give it eggs to pay for next bird placement
    if power_12_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_12_bird)

    activating_spot = state.players[0].board[1][0]

    # Find a bird that can be played in grassland
    birds = load_deck("birds")
    grassland_bird = [b for b in birds if "grassland" in b.habitats][0]
    state.players[0].bird_hand.append(grassland_bird)

    # Setup power activation
    setup_power_12_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Activate power
    state = transition_state(state, "activate_power")
    assert state.game_phase == GamePhase.PLAY_BIRD

    # Get play_bird actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if a.startswith("play_bird_")]
    assert len(play_bird_actions) > 0, "Should have grassland play actions"

    # Verify all actions are for grassland row (row 1)
    for action in play_bird_actions:
        parts = action.replace("play_bird_", "").split("_at_")
        row, col = parts[1].split("_")
        assert row == "1", f"'this' should resolve to grassland (row 1), got row {row}"


def test_power_12_no_valid_birds():
    """Test Power 12 cannot activate when no valid birds available."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_12()
    assert len(variants["forest"]) > 0, "Should find bird with power 12 (forest)"

    bird_id, power_data = variants["forest"][0]
    power_12_bird = get_bird(bird_id)

    # Place power 12 bird on board with eggs
    state.players[0].board[0][0].bird = power_12_bird
    power_12_bird.eggs = 5  # Give it eggs to pay for next bird placement
    if power_12_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_12_bird)

    activating_spot = state.players[0].board[0][0]

    # Remove all birds from hand OR add only non-forest birds
    all_birds = load_deck("birds")
    grassland_birds = [
        b for b in all_birds if "grassland" in b.habitats and "forest" not in b.habitats
    ][:2]
    state.players[0].bird_hand = grassland_birds

    # Setup power activation
    setup_power_12_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Verify cannot activate
    actions = get_actions(state)
    assert "activate_power" not in actions, "Should not be able to activate power"
    assert "skip_power" in actions, "Should be able to skip power"


def test_power_12_validation():
    """Test can_execute_power validator for Power 12."""
    from game.power_validators import can_execute_power

    state = initiate_state(2)
    state.current_player_index = 0

    # Give player plenty of resources
    state.players[0].food = {
        "invertebrate": 5,
        "seed": 5,
        "fish": 5,
        "fruit": 5,
        "rodent": 5,
    }

    variants = find_birds_with_power_12()

    if variants["forest"]:
        bird_id, power_data = variants["forest"][0]
        power_12_bird = get_bird(bird_id)

        # Place bird on board with eggs
        state.players[0].board[0][0].bird = power_12_bird
        power_12_bird.eggs = 5  # Give it eggs to pay for next bird placement
        activating_spot = state.players[0].board[0][0]

        # Add forest-compatible bird to hand
        all_birds = load_deck("birds")
        forest_bird = [b for b in all_birds if "forest" in b.habitats][0]
        state.players[0].bird_hand.append(forest_bird)

        power_entry = {
            "power_data": power_data,
            "spot": activating_spot,
        }

        # Should validate when forest bird available
        assert can_execute_power(
            state, power_entry
        ), "Should validate when forest-compatible bird is available"

        # Remove forest birds from hand
        state.players[0].bird_hand = [
            b for b in state.players[0].bird_hand if "forest" not in b.habitats
        ]

        # Should not validate when no forest birds
        assert not can_execute_power(
            state, power_entry
        ), "Should not validate when no forest-compatible birds available"


if __name__ == "__main__":
    print("Running Power 12 tests...")

    test_power_12_forest_basic()
    print("✓ test_power_12_forest_basic passed")

    test_power_12_habitat_filtering()
    print("✓ test_power_12_habitat_filtering passed")

    test_power_12_this_variant()
    print("✓ test_power_12_this_variant passed")

    test_power_12_no_valid_birds()
    print("✓ test_power_12_no_valid_birds passed")

    test_power_12_validation()
    print("✓ test_power_12_validation passed")

    print("\n✅ All Power 12 tests passed!")
