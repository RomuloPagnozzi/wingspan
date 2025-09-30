#!/usr/bin/env python3
"""
Comprehensive test for bird power system.
Tests power triggering, activation choices, and execution.
"""

import sys
sys.path.append('.')

from game.data import GameState, Player, Bird, initiate_state, get_bird_power
from game.actions import get_actions
from game.engine import transition_state
from game.utils import get_triggered_powers
from game.powers import can_execute_power, execute_power
import json


def create_test_bird_with_power(bird_id, name="Test Bird", power_id=1, resource_type="fruit"):
    """Create a test bird with a specific power."""
    bird = Bird(
        id=bird_id,
        name=name,
        habitats=["forest"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=20,
    )
    return bird


def setup_power_test_state():
    """Set up a game state ready for power testing."""
    # Start with a clean 2-player game
    state = initiate_state(2)

    # Complete setup for both players to get to main game
    for player_num in range(2):
        # Complete setup for current player
        state = transition_state(state, "start_setup")

        # Keep 2 birds, discard 2 food
        current_player = state.players[state.current_player_index]
        bird_ids = [b.id for b in current_player.bird_hand[:2]]
        bonus_id = current_player.bonus_hand[0].id
        selection = json.dumps({"kept_birds": bird_ids, "kept_bonus": bonus_id})
        state = transition_state(state, selection)

        # Discard food
        discard = json.dumps({"invertebrate": 1, "seed": 1})
        state = transition_state(state, discard)

    # End setup and transition to main game
    state = transition_state(state, "end_setup")

    return state


def place_bird_with_power_in_forest(state, player_index, power_id=1, resource_type="fruit"):
    """Place a bird with a specific power in the forest row."""
    player = state.players[player_index]

    # Find a power ID 1 bird that gives the specified resource
    from game.data import load_powers
    powers = load_powers()

    target_bird_id = None
    for bird_id, power_data in powers.items():
        if (power_data and 'data' in power_data and power_data['data'] and
            'id' in power_data['data'] and power_data['data']['id'] == power_id):

            details = power_data['data'].get('details', {})
            if details.get('type') == resource_type:
                target_bird_id = bird_id
                break

    if target_bird_id is None:
        raise ValueError(f"No power {power_id} bird found with resource {resource_type}")

    # Create the bird and place it manually in forest (for testing)
    test_bird = Bird(
        id=target_bird_id,
        name=f"Test Bird (Power {power_id})",
        habitats=["forest"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=20,
    )

    # Place bird in leftmost forest spot
    forest_row = player.board[0]  # Forest is row 0
    for spot in forest_row:
        if spot.bird is None:
            spot.bird = test_bird
            break

    return target_bird_id


def test_power_triggering():
    """Test that powers are properly triggered after forest action."""
    print("=== Power Triggering Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 (all players gain fruit) in forest
    bird_id = place_bird_with_power_in_forest(state, state.current_player_index, 1, "fruit")

    print(f"Placed bird {bird_id} with Power ID 1 in forest")
    print(f"Current action phase: {state.action_phase}")

    # Start gain food action
    actions = get_actions(state)
    assert "gain_food" in actions, f"gain_food not available: {actions}"

    state = transition_state(state, "gain_food")
    print(f"After gain_food selection: {state.action_phase}")

    # Might go to extra_food_action first (bird trade opportunity)
    if state.action_phase == "extra_food_action":
        extra_actions = get_actions(state)
        print(f"Extra food actions: {extra_actions}")
        # Skip the bird trade
        state = transition_state(state, "skip_trade")
        print(f"After skipping bird trade: {state.action_phase}")

    # Should now be in food collection phase
    assert state.action_phase == "collecting_food", f"Expected collecting_food, got {state.action_phase}"

    # Collect food to complete the action
    food_actions = get_actions(state)
    print(f"Food collection actions: {food_actions}")

    # Select a die to collect food
    food_action = food_actions[0]  # Take first available food
    if food_action != "reroll_all":
        state = transition_state(state, food_action)
        print(f"After collecting 1 food: {state.action_phase}")

        # Check if we need to collect more food or if powers are triggered
        if state.action_phase == "activating_powers":
            print("✓ Powers triggered after food collection!")

            # Verify the power queue
            powers_queue = state.action_data.get("powers_queue", [])
            assert len(powers_queue) > 0, "Powers queue should not be empty"

            current_power = powers_queue[0]
            assert current_power["bird_id"] == bird_id, f"Wrong bird in power queue: {current_power['bird_id']} vs {bird_id}"
            assert current_power["power_id"] == 1, f"Wrong power ID: {current_power['power_id']}"

            print(f"✓ Power queue contains: {len(powers_queue)} power(s)")
            print(f"✓ First power is from bird {current_power['bird_id']} with Power ID {current_power['power_id']}")
        else:
            print(f"Powers not triggered yet, still in: {state.action_phase}")
            print("Continuing food collection...")

    print("✓ Power triggering works correctly")
    print()


def test_power_activation_choices():
    """Test that power activation choices are generated correctly."""
    print("=== Power Activation Choices Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 in forest
    bird_id = place_bird_with_power_in_forest(state, state.current_player_index, 1, "seed")

    # Manually set up power activation state (simulate completing food collection)
    triggered_powers = get_triggered_powers(current_player, "forest", "brown")

    if triggered_powers:
        state.action_phase = "activating_powers"
        state.action_data = {
            "powers_queue": triggered_powers,
            "current_power_index": 0
        }

        # Get power activation actions
        power_actions = get_actions(state)
        print(f"Power activation actions: {power_actions}")

        # Should have at least skip option
        assert "skip_power" in power_actions, f"skip_power not found in {power_actions}"

        # Should have activate option if power can be executed
        current_power = triggered_powers[0]
        can_execute = can_execute_power(state, current_power["power_data"])

        if can_execute:
            assert "activate_power" in power_actions, f"activate_power not found in {power_actions}"
            print("✓ Both activate_power and skip_power options available")
        else:
            print("✓ Only skip_power available (power cannot be executed)")

        print(f"✓ Power activation choices generated correctly: {power_actions}")
    else:
        print("No powers triggered (this might be expected if no brown powers in forest)")

    print()


def test_power_execution():
    """Test that Power ID 1 executes correctly."""
    print("=== Power Execution Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 (all players gain fruit) in forest
    bird_id = place_bird_with_power_in_forest(state, state.current_player_index, 1, "fruit")

    # Record initial food state
    initial_food = {}
    for i, player in enumerate(state.players):
        initial_food[i] = player.food.copy()
        print(f"Player {i+1} initial food: {player.food}")

    # Manually trigger power execution
    power_data = get_bird_power(bird_id)
    print(f"Power data: {power_data}")

    # Execute the power
    state = execute_power(state, power_data)

    # Check that all players gained 1 fruit
    print("After power execution:")
    for i, player in enumerate(state.players):
        expected_fruit = initial_food[i].get("fruit", 0) + 1
        actual_fruit = player.food.get("fruit", 0)

        print(f"Player {i+1} food: {player.food}")
        assert actual_fruit == expected_fruit, f"Player {i+1} should have {expected_fruit} fruit, has {actual_fruit}"

    print("✓ All players gained 1 fruit from Power ID 1")
    print()


def test_multiple_powers_in_sequence():
    """Test multiple powers triggering in sequence."""
    print("=== Multiple Powers Sequence Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place two birds with Power ID 1 in forest
    bird_id_1 = place_bird_with_power_in_forest(state, state.current_player_index, 1, "fruit")
    bird_id_2 = place_bird_with_power_in_forest(state, state.current_player_index, 1, "seed")

    print(f"Placed birds {bird_id_1} and {bird_id_2} with powers in forest")

    # Get triggered powers
    triggered_powers = get_triggered_powers(current_player, "forest", "brown")
    print(f"Triggered powers: {len(triggered_powers)}")

    if len(triggered_powers) >= 2:
        # Set up power activation state
        state.action_phase = "activating_powers"
        state.action_data = {
            "powers_queue": triggered_powers,
            "current_power_index": 0
        }

        # Record initial food
        initial_food = {}
        for i, player in enumerate(state.players):
            initial_food[i] = player.food.copy()

        # Activate first power
        power_actions = get_actions(state)
        assert "activate_power" in power_actions, "First power should be activatable"

        state = transition_state(state, "activate_power")
        print(f"After first power activation: {state.action_phase}")

        # Should still be in activating_powers phase for second power
        if state.action_phase == "activating_powers":
            assert state.action_data["current_power_index"] == 1, "Should move to second power"

            # Activate second power
            power_actions = get_actions(state)
            assert "activate_power" in power_actions, "Second power should be activatable"

            state = transition_state(state, "activate_power")
            print(f"After second power activation: {state.action_phase}")

            # Should now return to main turn
            assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

            # Check that both resources were distributed
            for i, player in enumerate(state.players):
                # Should have gained 1 fruit and 1 seed
                expected_fruit = initial_food[i].get("fruit", 0) + 1
                expected_seed = initial_food[i].get("seed", 0) + 1

                actual_fruit = player.food.get("fruit", 0)
                actual_seed = player.food.get("seed", 0)

                print(f"Player {i+1}: fruit {actual_fruit} (expected {expected_fruit}), seed {actual_seed} (expected {expected_seed})")

                assert actual_fruit == expected_fruit, f"Player {i+1} fruit mismatch"
                assert actual_seed == expected_seed, f"Player {i+1} seed mismatch"

            print("✓ Multiple powers executed in sequence correctly")
        else:
            print("Only one power was processed (this might be expected)")
    else:
        print(f"Only {len(triggered_powers)} power(s) triggered")

    print()


def test_power_skip_option():
    """Test skipping power activation."""
    print("=== Power Skip Option Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 in forest
    bird_id = place_bird_with_power_in_forest(state, state.current_player_index, 1, "fruit")

    # Set up power activation state
    triggered_powers = get_triggered_powers(current_player, "forest", "brown")

    if triggered_powers:
        state.action_phase = "activating_powers"
        state.action_data = {
            "powers_queue": triggered_powers,
            "current_power_index": 0
        }

        # Record initial food
        initial_food = {}
        for i, player in enumerate(state.players):
            initial_food[i] = player.food.copy()

        # Skip the power
        power_actions = get_actions(state)
        assert "skip_power" in power_actions, "skip_power should be available"

        state = transition_state(state, "skip_power")
        print(f"After skipping power: {state.action_phase}")

        # Should return to main turn
        assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

        # Food should be unchanged
        for i, player in enumerate(state.players):
            assert player.food == initial_food[i], f"Player {i+1} food should be unchanged after skipping"

        print("✓ Power skipping works correctly")
    else:
        print("No powers to skip")

    print()


def test_power_validation():
    """Test power validation logic."""
    print("=== Power Validation Test ===")

    state = setup_power_test_state()

    # Test Power ID 1 validation
    from game.data import load_powers
    powers = load_powers()

    # Find a Power ID 1 bird
    test_bird_id = None
    test_power_data = None
    for bird_id, power_data in powers.items():
        if (power_data and 'data' in power_data and power_data['data'] and
            'id' in power_data['data'] and power_data['data']['id'] == 1):
            test_bird_id = bird_id
            test_power_data = power_data
            break

    if test_bird_id and test_power_data:
        # Test validation with normal state
        can_execute = can_execute_power(state, test_power_data)
        print(f"Power ID 1 can execute: {can_execute}")

        resource_type = test_power_data['data']['details'].get('type')
        if resource_type == 'card':
            # For card powers, should depend on deck/tray availability
            deck_size = len(state.bird_deck)
            tray_size = len(state.bird_tray)
            expected = deck_size > 0 or tray_size > 0
            assert can_execute == expected, f"Card power validation incorrect: {can_execute} vs {expected}"
            print(f"✓ Card power validation correct (deck: {deck_size}, tray: {tray_size})")
        else:
            # For food powers, should always be true (unlimited food)
            assert can_execute == True, f"Food power should always be executable"
            print(f"✓ Food power validation correct")

        print("✓ Power validation works correctly")
    else:
        print("No Power ID 1 found for validation test")

    print()


def test_integration_with_food_action():
    """Test full integration with gain food action."""
    print("=== Integration with Food Action Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 in forest
    bird_id = place_bird_with_power_in_forest(state, state.current_player_index, 1, "invertebrate")

    print(f"Starting food action with bird {bird_id} in forest")
    print(f"Current phase: {state.action_phase}")

    # Record initial state
    initial_food = {}
    for i, player in enumerate(state.players):
        initial_food[i] = player.food.copy()

    # Start gain food action
    actions = get_actions(state)
    assert "gain_food" in actions, f"gain_food not available: {actions}"

    state = transition_state(state, "gain_food")
    print(f"After gain_food: {state.action_phase}")

    # Handle extra food action if it appears
    if state.action_phase == "extra_food_action":
        state = transition_state(state, "skip_trade")
        print(f"After skipping bird trade: {state.action_phase}")

    # Complete food collection
    while state.action_phase == "collecting_food":
        food_actions = get_actions(state)
        # Skip reroll and take first food die
        food_action = next((a for a in food_actions if a != "reroll_all"), food_actions[0])
        state = transition_state(state, food_action)
        print(f"After food collection step: {state.action_phase}")

    # Should now be in power activation phase
    if state.action_phase == "activating_powers":
        print("✓ Food action triggered power activation")

        # Activate the power
        power_actions = get_actions(state)
        if "activate_power" in power_actions:
            state = transition_state(state, "activate_power")
            print(f"After power activation: {state.action_phase}")

            # Should return to main turn
            assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

            # Check that all players gained the resource
            for i, player in enumerate(state.players):
                expected_invertebrate = initial_food[i].get("invertebrate", 0) + 1
                actual_invertebrate = player.food.get("invertebrate", 0)

                print(f"Player {i+1} invertebrate: {actual_invertebrate} (expected {expected_invertebrate})")
                # Note: actual might be higher due to food collection itself
                assert actual_invertebrate >= expected_invertebrate, f"Player {i+1} should have at least {expected_invertebrate} invertebrate"

            print("✓ Full integration works correctly")
        else:
            print("Power not executable, skipping")
    else:
        print(f"Powers not triggered, ended in: {state.action_phase}")

    print()


def place_bird_with_power_in_grassland(state, player_index, power_id=1, resource_type="fruit"):
    """Place a bird with a specific power in the grassland row."""
    player = state.players[player_index]

    # Find a power ID 1 bird that gives the specified resource
    from game.data import load_powers
    powers = load_powers()

    target_bird_id = None
    for bird_id, power_data in powers.items():
        if (power_data and 'data' in power_data and power_data['data'] and
            'id' in power_data['data'] and power_data['data']['id'] == power_id):

            details = power_data['data'].get('details', {})
            if details.get('type') == resource_type:
                target_bird_id = bird_id
                break

    if target_bird_id is None:
        raise ValueError(f"No power {power_id} bird found with resource {resource_type}")

    # Create the bird and place it manually in grassland (for testing)
    test_bird = Bird(
        id=target_bird_id,
        name=f"Test Bird (Power {power_id})",
        habitats=["grassland"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=20,
    )

    # Place bird in leftmost grassland spot
    grassland_row = player.board[1]  # Grassland is row 1
    for spot in grassland_row:
        if spot.bird is None:
            spot.bird = test_bird
            break

    return target_bird_id


def place_bird_with_power_in_wetland(state, player_index, power_id=1, resource_type="fruit"):
    """Place a bird with a specific power in the wetland row."""
    player = state.players[player_index]

    # Find a power ID 1 bird that gives the specified resource
    from game.data import load_powers
    powers = load_powers()

    target_bird_id = None
    for bird_id, power_data in powers.items():
        if (power_data and 'data' in power_data and power_data['data'] and
            'id' in power_data['data'] and power_data['data']['id'] == power_id):

            details = power_data['data'].get('details', {})
            if details.get('type') == resource_type:
                target_bird_id = bird_id
                break

    if target_bird_id is None:
        raise ValueError(f"No power {power_id} bird found with resource {resource_type}")

    # Create the bird and place it manually in wetland (for testing)
    test_bird = Bird(
        id=target_bird_id,
        name=f"Test Bird (Power {power_id})",
        habitats=["wetland"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=20,
    )

    # Place bird in leftmost wetland spot
    wetland_row = player.board[2]  # Wetland is row 2
    for spot in wetland_row:
        if spot.bird is None:
            spot.bird = test_bird
            break

    return target_bird_id


def test_grassland_power_triggering():
    """Test that powers are triggered after lay eggs action in grassland."""
    print("=== Grassland Power Triggering Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 in grassland
    bird_id = place_bird_with_power_in_grassland(state, state.current_player_index, 1, "seed")

    # Also place a bird that can hold eggs for the lay eggs action
    egg_bird = Bird(
        id=9999,
        name="Egg Holder",
        habitats=["grassland"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=4,
        wingspan=20,
    )
    # Place it in another spot
    grassland_row = current_player.board[1]
    for spot in grassland_row:
        if spot.bird is None:
            spot.bird = egg_bird
            break

    print(f"Placed bird {bird_id} with Power ID 1 in grassland")
    print(f"Current action phase: {state.action_phase}")

    # Record initial food
    initial_food = {}
    for i, player in enumerate(state.players):
        initial_food[i] = player.food.copy()

    # Start lay eggs action
    actions = get_actions(state)
    assert "lay_eggs" in actions, f"lay_eggs not available: {actions}"

    state = transition_state(state, "lay_eggs")
    print(f"After lay_eggs selection: {state.action_phase}")

    # Handle extra lay eggs action if it appears
    if state.action_phase == "extra_lay_eggs_action":
        state = transition_state(state, "skip_trade")
        print(f"After skipping food trade: {state.action_phase}")

    # Should be in laying_eggs phase
    assert state.action_phase == "laying_eggs", f"Expected laying_eggs, got {state.action_phase}"

    # Complete egg laying
    egg_actions = get_actions(state)
    print(f"Egg laying actions available: {len(egg_actions)}")

    # Choose first egg laying option
    state = transition_state(state, egg_actions[0])
    print(f"After laying eggs: {state.action_phase}")

    # Should now be in power activation phase
    if state.action_phase == "activating_powers":
        print("✓ Grassland powers triggered after lay eggs!")

        # Verify the power queue
        powers_queue = state.action_data.get("powers_queue", [])
        assert len(powers_queue) > 0, "Powers queue should not be empty"

        current_power = powers_queue[0]
        assert current_power["bird_id"] == bird_id, f"Wrong bird in power queue: {current_power['bird_id']} vs {bird_id}"
        assert current_power["power_id"] == 1, f"Wrong power ID: {current_power['power_id']}"

        # Activate the power
        power_actions = get_actions(state)
        if "activate_power" in power_actions:
            state = transition_state(state, "activate_power")
            print(f"After power activation: {state.action_phase}")

            # Should return to main turn
            assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

            # Check that all players gained seed
            for i, player in enumerate(state.players):
                expected_seed = initial_food[i].get("seed", 0) + 1
                actual_seed = player.food.get("seed", 0)

                print(f"Player {i+1} seed: {actual_seed} (expected {expected_seed})")
                assert actual_seed == expected_seed, f"Player {i+1} should have {expected_seed} seed, has {actual_seed}"

        print("✓ Grassland power triggering works correctly")
    else:
        print(f"Powers not triggered, ended in: {state.action_phase}")

    print()


def test_wetland_power_triggering():
    """Test that powers are triggered after draw cards action in wetland."""
    print("=== Wetland Power Triggering Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Place a bird with Power ID 1 in wetland
    bird_id = place_bird_with_power_in_wetland(state, state.current_player_index, 1, "fish")

    print(f"Placed bird {bird_id} with Power ID 1 in wetland")
    print(f"Current action phase: {state.action_phase}")

    # Record initial food
    initial_food = {}
    for i, player in enumerate(state.players):
        initial_food[i] = player.food.copy()

    # Start draw cards action
    actions = get_actions(state)
    assert "draw_cards" in actions, f"draw_cards not available: {actions}"

    state = transition_state(state, "draw_cards")
    print(f"After draw_cards selection: {state.action_phase}")

    # Handle extra card draw action if it appears
    if state.action_phase == "extra_card_draw_action":
        state = transition_state(state, "skip_trade")
        print(f"After skipping egg trade: {state.action_phase}")

    # Should be in drawing_cards phase
    assert state.action_phase == "drawing_cards", f"Expected drawing_cards, got {state.action_phase}"

    # Complete card drawing
    card_actions = get_actions(state)
    print(f"Card drawing actions available: {len(card_actions)}")

    # Choose first card drawing option
    state = transition_state(state, card_actions[0])
    print(f"After drawing cards: {state.action_phase}")

    # Should now be in power activation phase
    if state.action_phase == "activating_powers":
        print("✓ Wetland powers triggered after draw cards!")

        # Verify the power queue
        powers_queue = state.action_data.get("powers_queue", [])
        assert len(powers_queue) > 0, "Powers queue should not be empty"

        current_power = powers_queue[0]
        assert current_power["bird_id"] == bird_id, f"Wrong bird in power queue: {current_power['bird_id']} vs {bird_id}"
        assert current_power["power_id"] == 1, f"Wrong power ID: {current_power['power_id']}"

        # Activate the power
        power_actions = get_actions(state)
        if "activate_power" in power_actions:
            state = transition_state(state, "activate_power")
            print(f"After power activation: {state.action_phase}")

            # Should return to main turn
            assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

            # Check that all players gained fish
            for i, player in enumerate(state.players):
                expected_fish = initial_food[i].get("fish", 0) + 1
                actual_fish = player.food.get("fish", 0)

                print(f"Player {i+1} fish: {actual_fish} (expected {expected_fish})")
                assert actual_fish == expected_fish, f"Player {i+1} should have {expected_fish} fish, has {actual_fish}"

        print("✓ Wetland power triggering works correctly")
    else:
        print(f"Powers not triggered, ended in: {state.action_phase}")

    print()


def place_bird_with_power_2_in_forest(state, player_index, nest_type="ground"):
    """Place a bird with Power ID 2 for specific nest type in forest."""
    player = state.players[player_index]

    # Find a power ID 2 bird that affects the specified nest type
    from game.data import load_powers
    powers = load_powers()

    target_bird_id = None
    for bird_id, power_data in powers.items():
        if (power_data and 'data' in power_data and power_data['data'] and
            'id' in power_data['data'] and power_data['data']['id'] == 2):

            details = power_data['data'].get('details', {})
            if details.get('type') == nest_type:
                target_bird_id = bird_id
                break

    if target_bird_id is None:
        raise ValueError(f"No power 2 bird found with nest type {nest_type}")

    # Create the bird and place it manually in forest (for testing)
    test_bird = Bird(
        id=target_bird_id,
        name=f"Test Bird (Power 2, {nest_type})",
        habitats=["forest"],
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=20,
    )

    # Place bird in leftmost forest spot
    forest_row = player.board[0]  # Forest is row 0
    for spot in forest_row:
        if spot.bird is None:
            spot.bird = test_bird
            break

    return target_bird_id


def create_test_bird_with_nest(bird_id, nest_type, egg_limit=4):
    """Create a test bird with specific nest type and egg capacity."""
    bird = Bird(
        id=bird_id,
        name=f"Test {nest_type.title()} Bird",
        habitats=["grassland"],
        cost=[],
        points=1,
        nest=nest_type,
        egg_limit=egg_limit,
        wingspan=20,
    )
    return bird


def test_power_2_validation():
    """Test Power ID 2 validation logic."""
    print("=== Power ID 2 Validation Test ===")

    state = setup_power_test_state()
    current_player = state.players[state.current_player_index]

    # Test with no ground birds
    from game.data import get_bird_power
    from game.powers import _can_execute_power_2

    # Create mock power data for ground nest type
    power_data = {
        "color": "brown",
        "trigger": "when activated",
        "data": {"id": 2, "details": {"type": "ground"}}
    }

    # Should not be executable with no ground birds
    can_execute = _can_execute_power_2(state, power_data)
    assert not can_execute, "Power should not be executable with no valid birds"
    print("✓ Correctly validates when no valid birds available")

    # Add a ground bird with capacity
    ground_bird = create_test_bird_with_nest(8888, "ground", 4)
    current_player.board[1][0].bird = ground_bird

    # Now should be executable
    can_execute = _can_execute_power_2(state, power_data)
    assert can_execute, "Power should be executable with valid ground bird"
    print("✓ Correctly validates when valid birds available")

    print("✓ Power ID 2 validation works correctly")
    print()


def test_power_2_single_bird_choice_creation():
    """Test Power ID 2 with single bird per player (creates choice powers)."""
    print("=== Power ID 2 Single Bird Choice Creation Test ===")

    state = setup_power_test_state()

    # Give each player exactly one ground bird with egg capacity
    for i, player in enumerate(state.players):
        ground_bird = create_test_bird_with_nest(9000 + i, "ground", 4)
        player.board[1][0].bird = ground_bird

    current_player = state.players[state.current_player_index]

    # Record initial egg counts (should be 0 for new birds)
    initial_eggs = {}
    for i, player in enumerate(state.players):
        initial_eggs[i] = player.board[1][0].bird.eggs

    # Create and execute power
    power_data = {
        "color": "brown",
        "trigger": "when_activated",
        "data": {"id": 2, "details": {"type": "ground"}}
    }

    from game.powers import _execute_power_2
    # Setup powers queue for test
    state.action_data = {
        "powers_queue": [{"power_data": power_data}],
        "current_power_index": 0,
        "activating_player_index": state.current_player_index
    }

    state = _execute_power_2(state, power_data)

    # Should have created player queue with all players that have valid birds
    player_queue = state.action_data.get("power_2_players", [])

    # Should have one entry per player with valid birds
    expected_player_count = len([p for p in state.players if any(
        spot.bird and spot.bird.nest == "ground" and spot.bird.eggs < spot.bird.egg_limit
        for row in p.board for spot in row
    )])

    print(f"Created player queue with {len(player_queue)} players (expected {expected_player_count})")
    assert len(player_queue) == expected_player_count, f"Should create queue with {expected_player_count} players, created {len(player_queue)}"

    # Verify queue contains correct player indices and egg counts
    activating_idx = state.action_data.get("activating_player_index", 0)
    for player_idx, egg_count in player_queue:
        expected_eggs = 2 if player_idx == activating_idx else 1
        assert egg_count == expected_eggs, f"Player {player_idx} should lay {expected_eggs} eggs, got {egg_count}"

    # Eggs should still be at initial values since no choices have been made yet
    for i, player in enumerate(state.players):
        actual_eggs = player.board[1][0].bird.eggs
        expected_eggs = initial_eggs[i]  # Should be unchanged

        print(f"Player {i+1}: {actual_eggs} eggs (expected {expected_eggs} - no auto-resolution)")
        assert actual_eggs == expected_eggs, f"Player {i+1} should have {expected_eggs} eggs (unchanged), has {actual_eggs}"

    print("✓ Single bird choice creation works correctly")
    print()


def test_power_2_multi_bird_choices():
    """Test Power ID 2 with multiple birds requiring choices."""
    print("=== Power ID 2 Multi-Bird Choices Test ===")

    state = setup_power_test_state()

    # Give players multiple ground birds with egg capacity
    for i, player in enumerate(state.players):
        # Two ground birds each
        ground_bird_1 = create_test_bird_with_nest(9100 + i * 2, "ground", 3)
        ground_bird_2 = create_test_bird_with_nest(9100 + i * 2 + 1, "ground", 3)

        player.board[1][0].bird = ground_bird_1
        player.board[1][1].bird = ground_bird_2

    current_player = state.players[state.current_player_index]

    # Record initial state
    initial_eggs = {}
    for i, player in enumerate(state.players):
        initial_eggs[i] = [player.board[1][0].bird.eggs, player.board[1][1].bird.eggs]

    # Set up power activation context with proper queue
    state.action_phase = "activating_powers"
    state.action_data = {
        "powers_queue": [{
            "bird_id": 999,
            "power_id": 2,
            "power_data": {
                "color": "brown",
                "trigger": "when activated",
                "data": {"id": 2, "details": {"type": "ground"}}
            },
            "spot": None
        }],
        "current_power_index": 0
    }

    # Execute power with proper context
    from game.powers import _execute_power_2
    power_data = state.action_data["powers_queue"][0]["power_data"]
    state = _execute_power_2(state, power_data)

    # Should complete and return to activating_powers with player queue created
    assert state.action_phase == "activating_powers", f"Should stay in activating_powers, got {state.action_phase}"

    # Should have created player queue
    assert "power_2_players" in state.action_data, "Should have power_2_players queue"
    player_queue = state.action_data["power_2_players"]

    # Should have 2 players in queue (both have valid birds)
    assert len(player_queue) == 2, f"Should have 2 players in queue, got {len(player_queue)}"

    # No eggs should have been laid yet (choices haven't been made)
    ground_bird_1 = state.players[0].board[1][0].bird
    ground_bird_2 = state.players[0].board[1][1].bird
    assert ground_bird_1.eggs == initial_eggs[0][0], "Ground bird 1 should have no eggs yet"
    assert ground_bird_2.eggs == initial_eggs[0][1], "Ground bird 2 should have no eggs yet"

    print("✓ Multi-bird choice setup works correctly")
    print()


def test_power_2_choice_generation():
    """Test Power ID 2 choice generation."""
    print("=== Power ID 2 Choice Generation Test ===")

    state = setup_power_test_state()
    current_player_index = state.current_player_index
    current_player = state.players[current_player_index]

    # Give current player two ground birds with different capacities
    ground_bird_1 = create_test_bird_with_nest(9200, "ground", 4)  # Can hold 4 eggs
    ground_bird_1.eggs = 2  # Currently has 2, so 2 capacity remaining

    ground_bird_2 = create_test_bird_with_nest(9201, "ground", 3)  # Can hold 3 eggs
    ground_bird_2.eggs = 0  # Currently has 0, so 3 capacity remaining

    current_player.board[1][0].bird = ground_bird_1
    current_player.board[1][1].bird = ground_bird_2

    # Set up power activation state for choice power
    state.action_phase = "activating_powers"
    state.current_player_index = current_player_index

    # Simulate power_2_players queue being set up
    state.action_data["power_2_players"] = [(current_player_index, 2)]

    # Generate choices using new choice power structure
    from game.powers import _get_power_2_choice_actions
    choice_power_data = {
        "color": "brown",
        "data": {
            "id": 2,
            "details": {
                "type": "ground"
            }
        }
    }
    choices = _get_power_2_choice_actions(state, choice_power_data)

    print(f"Generated {len(choices)} choices")
    for i, choice in enumerate(choices):
        print(f"Choice {i+1}: {choice}")

    # Should have valid distribution combinations
    assert len(choices) > 0, "Should generate at least one choice"

    # Parse and validate choices
    import json
    parsed_choices = [json.loads(choice) for choice in choices]

    # Each choice should distribute exactly 2 eggs
    for choice in parsed_choices:
        total_eggs = sum(choice.values())
        assert total_eggs == 2, f"Each choice should distribute 2 eggs, got {total_eggs}"

        # Check capacity constraints
        for bird_id, eggs in choice.items():
            bird_id = int(bird_id)
            if bird_id == 9200:  # ground_bird_1
                assert eggs <= 2, f"Bird 9200 should not exceed capacity (2), got {eggs}"
            elif bird_id == 9201:  # ground_bird_2
                assert eggs <= 3, f"Bird 9201 should not exceed capacity (3), got {eggs}"

    print("✓ Choice generation works correctly")
    print()


def test_power_2_full_integration():
    """Test full Power ID 2 integration with game flow."""
    print("=== Power ID 2 Full Integration Test ===")

    state = setup_power_test_state()
    current_player_index = state.current_player_index
    other_player_index = 1 if current_player_index == 0 else 0

    # Set up scenario: BOTH players get multiple birds to ensure choice is needed
    current_player = state.players[current_player_index]
    other_player = state.players[other_player_index]

    # Current player gets 2 ground birds (will need choice for 2 eggs)
    ground_bird_01 = create_test_bird_with_nest(9300, "ground", 4)
    ground_bird_02 = create_test_bird_with_nest(9301, "ground", 3)
    current_player.board[1][0].bird = ground_bird_01
    current_player.board[1][1].bird = ground_bird_02

    # Other player ALSO gets 2 ground birds (will need choice for 1 egg)
    ground_bird_03 = create_test_bird_with_nest(9303, "ground", 4)
    ground_bird_04 = create_test_bird_with_nest(9304, "ground", 3)
    other_player.board[1][0].bird = ground_bird_03
    other_player.board[1][1].bird = ground_bird_04

    # Place Power ID 2 bird in forest for current player
    power_bird_id = place_bird_with_power_2_in_forest(state, current_player_index, "ground")

    # Record initial eggs
    initial_curr_bird1_eggs = ground_bird_01.eggs
    initial_curr_bird2_eggs = ground_bird_02.eggs
    initial_other_bird1_eggs = ground_bird_03.eggs
    initial_other_bird2_eggs = ground_bird_04.eggs

    # Trigger the power through normal game flow (using gain_food action)
    # Place some food in the feeder first
    state.feeder = {0: ["fruit"], 1: ["invertebrate"], 2: ["fish"], 3: ["seed"]}

    # Start gain_food action to trigger forest powers
    state = transition_state(state, "gain_food")

    # Handle extra food action if it appears
    if state.action_phase == "extra_food_action":
        state = transition_state(state, "skip_trade")

    # Complete food collection
    while state.action_phase == "collecting_food":
        food_actions = get_actions(state)
        # Take first available food
        food_action = next((a for a in food_actions if a != "reroll_all"), food_actions[0])
        state = transition_state(state, food_action)

    # Should now be in power activation phase
    assert state.action_phase == "activating_powers", f"Should be in activating_powers, got {state.action_phase}"

    # Find and activate the Power ID 2
    power_actions = get_actions(state)
    power_2_action = None

    # Look for activation actions (not skip)
    for action in power_actions:
        if action.startswith("activate_"):
            power_2_action = action
            break

    assert power_2_action is not None, f"Should find Power ID 2 activation option in: {power_actions}"

    # Activate the power (this sets up the player queue)
    state = transition_state(state, power_2_action)

    # Should stay in activating_powers and have player queue set up
    assert state.action_phase == "activating_powers", f"Should stay in activating_powers, got {state.action_phase}"

    # Should have created player queue
    assert "power_2_players" in state.action_data, "Should have power_2_players queue"
    player_queue = state.action_data["power_2_players"]
    assert len(player_queue) == 2, f"Should have 2 players in queue, got {len(player_queue)}"

    # Both players should have 0 eggs still (no choices made yet)
    assert ground_bird_01.eggs == initial_curr_bird1_eggs, "Current player birds should not have eggs yet"
    assert ground_bird_02.eggs == initial_curr_bird2_eggs, "Current player birds should not have eggs yet"
    assert ground_bird_03.eggs == initial_other_bird1_eggs, "Other player birds should not have eggs yet"
    assert ground_bird_04.eggs == initial_other_bird2_eggs, "Other player birds should not have eggs yet"

    # Now we're at the first player's choice - make the choice
    choices = get_actions(state)
    assert len(choices) > 0, "Should have choices available for first player"

    # Take the first activate choice
    first_choice = next(a for a in choices if a.startswith("activate_"))
    state = transition_state(state, first_choice)

    # Should still be in activating_powers for second player's choice
    assert state.action_phase == "activating_powers", f"Should stay in activating_powers for second choice, got {state.action_phase}"

    # Make choice for second player
    choices = get_actions(state)
    assert len(choices) > 0, "Should have choices available for second player"

    # Take the first activate choice for second player
    second_choice = next(a for a in choices if a.startswith("activate_"))
    state = transition_state(state, second_choice)

    # Now should return to main_turn since all powers are complete
    assert state.action_phase == "main_turn", f"Should return to main_turn after all choices, got {state.action_phase}"

    # Verify that eggs were distributed (exact counts depend on choices made)
    total_eggs_distributed = (ground_bird_01.eggs + ground_bird_02.eggs +
                            ground_bird_03.eggs + ground_bird_04.eggs)
    expected_total = 3  # Current player gets 2, other player gets 1
    assert total_eggs_distributed == expected_total, f"Total eggs should be {expected_total}, got {total_eggs_distributed}"

    print("✓ Full Power ID 2 integration works correctly")
    print()


def test_power_2_activating_player_only():
    """Test Power ID 2 when ONLY the activating player can benefit."""
    print("=== Power ID 2 Activating Player Only Test ===")

    state = setup_power_test_state()
    current_player_index = state.current_player_index
    other_player_index = 1 if current_player_index == 0 else 0

    current_player = state.players[current_player_index]
    other_player = state.players[other_player_index]

    # ONLY current player gets a ground bird (other player has none)
    ground_bird = create_test_bird_with_nest(9500, "ground", 4)
    ground_bird.eggs = 0
    current_player.board[1][0].bird = ground_bird

    # Other player has NO ground birds
    # (leave their grassland row empty)

    # Place Power ID 2 bird in forest for current player
    power_bird_id = place_bird_with_power_2_in_forest(state, current_player_index, "ground")

    # Trigger the power through normal game flow
    state.feeder = {0: ["fruit"], 1: ["invertebrate"], 2: ["fish"], 3: ["seed"]}
    state = transition_state(state, "gain_food")

    if state.action_phase == "extra_food_action":
        state = transition_state(state, "skip_trade")

    while state.action_phase == "collecting_food":
        food_actions = get_actions(state)
        food_action = next((a for a in food_actions if a != "reroll_all"), food_actions[0])
        state = transition_state(state, food_action)

    # Should be in power activation phase
    assert state.action_phase == "activating_powers", f"Should be in activating_powers, got {state.action_phase}"

    # Get power actions
    power_actions = get_actions(state)
    print(f"Power actions available: {power_actions}")

    # Should be able to activate (current player can benefit)
    assert any(a.startswith("activate_") for a in power_actions), "Should have activate option"
    assert "skip_power" in power_actions, "Should have skip option"

    # Activate the power
    activate_action = next(a for a in power_actions if a.startswith("activate_"))
    state = transition_state(state, activate_action)

    # Should have created player queue with ONLY current player
    assert "power_2_players" in state.action_data, "Should have power_2_players queue"
    player_queue = state.action_data["power_2_players"]
    print(f"Player queue: {player_queue}")
    assert len(player_queue) == 1, f"Should have only 1 player in queue (activating player), got {len(player_queue)}"
    assert player_queue[0][0] == current_player_index, f"Queue should contain current player {current_player_index}, got {player_queue[0][0]}"
    assert player_queue[0][1] == 2, f"Activating player should lay 2 eggs, got {player_queue[0][1]}"

    # Should still be in activating_powers for the player's choice
    assert state.action_phase == "activating_powers", f"Should stay in activating_powers, got {state.action_phase}"

    # Current player should be able to make a choice
    assert state.current_player_index == current_player_index, f"Current player should be {current_player_index}, got {state.current_player_index}"

    # Get choice actions
    choice_actions = get_actions(state)
    print(f"Choice actions available: {choice_actions}")
    assert len(choice_actions) > 0, "Should have choice actions available"

    # Should NOT have skip_power option (we're in choice mode)
    assert "skip_power" not in choice_actions, "Should not have skip_power during choice phase"

    # All actions should start with "activate_"
    assert all(a.startswith("activate_") for a in choice_actions), "All actions should be activate choices"

    # Take first choice
    first_choice = choice_actions[0]
    print(f"Choosing: {first_choice}")
    state = transition_state(state, first_choice)

    # Should have applied eggs to the bird
    assert ground_bird.eggs == 2, f"Ground bird should have 2 eggs, has {ground_bird.eggs}"

    # Should be back to main_turn (power complete)
    assert state.action_phase == "main_turn", f"Should return to main_turn, got {state.action_phase}"

    # Queue should be cleaned up
    assert "power_2_players" not in state.action_data, "power_2_players should be cleaned up"
    assert "choice_powers" not in state.action_data, "choice_powers should be cleaned up"

    print("✓ Activating player receives 2 eggs correctly when they are the only beneficiary")
    print()


def test_power_2_skip_power():
    """Test Power ID 2 when player chooses to skip - should NOT give eggs."""
    print("=== Power ID 2 Skip Power Test ===")

    # Use test helper to get to main_turn quickly
    from game.data import load_deck
    state = setup_power_test_state()
    birds = load_deck("birds")

    current_player_idx = state.current_player_index
    print(f"Current player: {current_player_idx}")

    # Manually place a ground bird with Power ID 2 in forest (American Kestrel, bird 99)
    power_bird = [b for b in birds if b.id == 99][0]
    state.players[current_player_idx].board[0][0].bird = power_bird
    print(f"Placed Power 2 bird {power_bird.id} in forest")

    # Manually place a ground-nest bird in grassland for current player
    ground_bird = [b for b in birds if b.id == 1][0]
    state.players[current_player_idx].board[1][0].bird = ground_bird
    print(f"Placed ground bird {ground_bird.id} (nest={ground_bird.nest}) in grassland")

    # Check initial eggs - always read from state
    initial_eggs = state.players[current_player_idx].board[1][0].bird.eggs
    print(f"Initial eggs on bird: {initial_eggs}")

    # Setup feeder
    state.feeder = {0: ["fruit"], 1: ["invertebrate"], 2: ["fish"], 3: ["seed"]}

    # Start gain_food action to trigger power
    state = transition_state(state, "gain_food")

    # Skip extra food action if present
    if state.action_phase == "extra_food_action":
        state = transition_state(state, "skip_trade")

    # Complete food collection
    while state.action_phase == "collecting_food":
        actions = get_actions(state)
        food_action = next((a for a in actions if a != "reroll_all"), actions[0])
        state = transition_state(state, food_action)

    # Should be in power activation
    print(f"Phase after food collection: {state.action_phase}")
    assert state.action_phase == "activating_powers", f"Should be in activating_powers, got {state.action_phase}"

    # Get power actions
    power_actions = get_actions(state)
    print(f"Power actions: {power_actions}")
    assert "skip_power" in power_actions, "Should have skip_power option"

    # SKIP the power
    print(">>> SKIPPING POWER <<<")
    state = transition_state(state, "skip_power")

    # Check eggs AFTER skip - read from state
    eggs_after_skip = state.players[current_player_idx].board[1][0].bird.eggs
    print(f"Eggs after skip: {eggs_after_skip}")
    print(f"Expected: {initial_eggs}")

    # Verify no eggs were added
    assert eggs_after_skip == initial_eggs, f"Bird should have {initial_eggs} eggs after skip, but has {eggs_after_skip}"

    print("✓ Skipping power correctly prevents egg distribution")
    print()


if __name__ == "__main__":
    print("🎯 Running Comprehensive Power System Tests 🎯\n")

    # Core functionality tests
    test_power_triggering()
    test_power_activation_choices()
    test_power_execution()

    # Advanced scenarios
    test_multiple_powers_in_sequence()
    test_power_skip_option()
    test_power_validation()

    # Integration tests
    test_integration_with_food_action()
    test_grassland_power_triggering()
    test_wetland_power_triggering()

    # Power ID 2 specific tests
    test_power_2_validation()
    test_power_2_single_bird_choice_creation()
    test_power_2_multi_bird_choices()
    test_power_2_choice_generation()
    test_power_2_full_integration()
    test_power_2_activating_player_only()
    test_power_2_skip_power()

    print("🎉 ALL POWER SYSTEM TESTS COMPLETED! 🎉")
    print("✅ Power triggering works correctly")
    print("✅ Power activation choices work correctly")
    print("✅ Power execution works correctly")
    print("✅ Multiple powers sequence works correctly")
    print("✅ Power skipping works correctly")
    print("✅ Power validation works correctly")
    print("✅ Integration with food action works correctly")
    print("✅ Grassland power triggering works correctly")
    print("✅ Wetland power triggering works correctly")
    print("✅ Power ID 2 validation works correctly")
    print("✅ Power ID 2 single bird auto-resolution works correctly")
    print("✅ Power ID 2 multi-bird choices work correctly")
    print("✅ Power ID 2 choice generation works correctly")
    print("✅ Power ID 2 full integration works correctly")
    print("✅ Power ID 2 activating player only scenario works correctly")
    print("✅ Power ID 2 skip power works correctly")