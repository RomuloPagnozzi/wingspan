#!/usr/bin/env python3
"""
Comprehensive test for lay_eggs flow with bonus food trade and egg distribution.
Tests the complete action sequence and state management.
"""

import sys
sys.path.append('.')

from game.data import GameState, Player, Bird
from game.actions import get_actions
from game.engine import transition_state
import json

def create_test_bird_with_capacity():
    """Create a bird that can receive eggs."""
    bird = Bird(
        id=777,
        name="Test Bird With Capacity",
        habitats=["grassland"],
        cost=[],
        points=2,
        nest="bowl",
        egg_limit=3,
        wingspan=20,
        power={}
    )
    bird.eggs = 1  # Has 1 egg, can receive 2 more
    return bird

def create_second_test_bird():
    """Create another bird for testing multiple egg distribution."""
    bird = Bird(
        id=888,
        name="Second Test Bird",
        habitats=["grassland"],
        cost=[],
        points=3,
        nest="cavity",
        egg_limit=2,
        wingspan=25,
        power={}
    )
    bird.eggs = 0  # Empty, can receive 2 eggs
    return bird

def setup_test_state():
    """Set up a game state for testing lay eggs with bonus food trade."""
    state = GameState()
    
    # Create player with food for trading
    player = Player(id=1)
    player.food = {
        "invertebrate": 1,
        "seed": 2,
        "fish": 1,
        "fruit": 2,  # Has food for trading
        "rodent": 1
    }
    
    # Place birds with egg capacity on the grassland row
    # Place birds so the leftmost empty spot has extra_resource=True
    bird1 = create_test_bird_with_capacity()
    bird2 = create_second_test_bird()
    player.board[1][0].bird = bird1  # First grassland spot  
    player.board[1][2].bird = bird2  # Third grassland spot (skip [1][1] which has extra_resource=True)
    
    state.players = [player]
    state.current_player_index = 0
    
    return state, bird1, bird2

def test_lay_eggs_comprehensive():
    """Test complete lay_eggs flow with food trade and egg distribution."""
    print("=== Comprehensive Lay Eggs Test ===\n")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    # Print initial state
    print("Initial State:")
    print(f"Player food: {current_player.food}")
    print(f"Bird 1 on board: {bird1.name} (ID: {bird1.id}) - eggs: {bird1.eggs}/{bird1.egg_limit}")
    print(f"Bird 2 on board: {bird2.name} (ID: {bird2.id}) - eggs: {bird2.eggs}/{bird2.egg_limit}")
    print(f"Grassland spot (next): resource_amount={current_player.board[1][1].resource_amount}, extra_resource={current_player.board[1][1].extra_resource}")
    print(f"Action cubes: {current_player.action_cubes}")
    print()
    
    # Step 1: Check if lay_eggs is available
    state.action_phase = "main_turn"
    print("=== Step 1: Get main turn actions ===")
    actions = get_actions(state)
    print(f"Available actions: {actions}")
    
    assert "lay_eggs" in actions, f"lay_eggs action not found in {actions}"
    print("✓ Found lay_eggs action")
    print()
    
    # Step 2: Execute lay_eggs action (should trigger extra action choice)
    print("=== Step 2: Execute lay_eggs action ===")
    state = transition_state(state, "lay_eggs")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to extra_lay_eggs_action phase (player has food and spot has extra_resource=True)
    assert state.action_phase == "extra_lay_eggs_action", f"Expected extra_lay_eggs_action, got {state.action_phase}"
    base_eggs = state.action_data.get("base_eggs_amount")
    assert base_eggs == 2, f"Expected base_eggs_amount=2, got {base_eggs}"  # Grassland row[1] gives 2 eggs (1+1)
    print("✓ Correctly transitioned to extra_lay_eggs_action phase")
    print()
    
    # Step 3: Get extra action options
    print("=== Step 3: Get extra lay eggs actions ===")
    extra_actions = get_actions(state)
    print(f"Extra action options: {extra_actions}")
    
    assert "trade_food" in extra_actions, "trade_food option not found"
    assert "skip_trade" in extra_actions, "skip_trade option not found"
    print("✓ Found expected extra action options")
    print()
    
    # Step 4: Choose to trade food for extra egg
    print("=== Step 4: Execute trade_food action ===")
    state = transition_state(state, "trade_food")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to select_food_to_discard phase
    assert state.action_phase == "select_food_to_discard", f"Expected select_food_to_discard, got {state.action_phase}"
    print("✓ Correctly transitioned to select_food_to_discard phase")
    print()
    
    # Step 5: Get food discard options
    print("=== Step 5: Get food discard actions ===")
    food_actions = get_actions(state)
    print(f"Food discard options: {food_actions}")
    
    # Should have options to discard each food type
    expected_foods = ["discard_food_invertebrate", "discard_food_seed", "discard_food_fish", "discard_food_fruit", "discard_food_rodent"]
    for food_action in expected_foods:
        assert food_action in food_actions, f"Expected food action {food_action} not found"
    print("✓ Found all expected food discard options")
    print()
    
    # Step 6: Discard a food token
    print("=== Step 6: Execute food discard ===")
    food_before = current_player.food.copy()
    state = transition_state(state, "discard_food_fruit")
    # Get updated reference after state transition
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    print(f"Food before discard: {food_before}")
    print(f"Food after discard: {food_after}")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to laying_eggs phase with extra egg
    assert state.action_phase == "laying_eggs", f"Expected laying_eggs, got {state.action_phase}"
    assert food_after["fruit"] == food_before["fruit"] - 1, "Food not discarded correctly"
    eggs_needed = state.action_data.get("eggs_needed")
    assert eggs_needed == 3, f"Expected eggs_needed=3 (2+1), got {eggs_needed}"  # Base 2 + 1 extra
    print("✓ Food discarded successfully, moved to laying_eggs phase with extra egg")
    print()
    
    # Step 7: Get egg distribution options
    print("=== Step 7: Get egg distribution actions ===")
    egg_actions = get_actions(state)
    print(f"Egg distribution options: {len(egg_actions)} combinations")
    
    # Print first few options for inspection
    for i, action in enumerate(egg_actions[:3]):
        distribution = json.loads(action)
        print(f"  Option {i+1}: {distribution}")
    
    # Should have various ways to distribute 3 eggs between birds
    assert len(egg_actions) > 0, "No egg distribution options found"
    print("✓ Found egg distribution options")
    print()
    
    # Step 8: Choose a distribution (give 2 to bird1, 1 to bird2)
    print("=== Step 8: Execute egg distribution ===")
    target_distribution = json.dumps({777: 2, 888: 1})  # 2 eggs to bird1, 1 to bird2
    
    # Verify this distribution is available
    assert target_distribution in egg_actions, f"Target distribution {target_distribution} not found in options"
    
    eggs_before = {
        bird1.id: current_player.board[1][0].bird.eggs,
        bird2.id: current_player.board[1][2].bird.eggs
    }
    state = transition_state(state, target_distribution)
    # Get updated references after state transition
    current_player = state.players[0]
    eggs_after = {
        bird1.id: current_player.board[1][0].bird.eggs,
        bird2.id: current_player.board[1][2].bird.eggs
    }
    
    print(f"Eggs before distribution: {eggs_before}")
    print(f"Eggs after distribution: {eggs_after}")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action cubes: {current_player.action_cubes}")
    print()
    
    # Should return to main_turn and eggs should be distributed
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert eggs_after[bird1.id] == eggs_before[bird1.id] + 2, f"Bird1 eggs not updated correctly"
    assert eggs_after[bird2.id] == eggs_before[bird2.id] + 1, f"Bird2 eggs not updated correctly"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    print("✓ Eggs distributed successfully, returned to main_turn phase")
    print()
    
    # Step 9: Verify final state
    print("=== Step 9: Verify final state ===")
    current_player = state.players[0]  # Ensure fresh reference
    final_bird1 = current_player.board[1][0].bird
    final_bird2 = current_player.board[1][2].bird
    
    print(f"Final bird1 eggs: {final_bird1.eggs}/{final_bird1.egg_limit}")
    print(f"Final bird2 eggs: {final_bird2.eggs}/{final_bird2.egg_limit}")
    print(f"Final food: {current_player.food}")
    print(f"Final action cubes: {current_player.action_cubes}")
    
    assert final_bird1.eggs == 3, f"Bird1 should have 3 eggs, has {final_bird1.eggs}"
    assert final_bird2.eggs == 1, f"Bird2 should have 1 egg, has {final_bird2.eggs}"
    assert current_player.food["fruit"] == 1, f"Should have 1 fruit left, has {current_player.food.get('fruit', 0)}"
    print("✓ All final state checks passed")
    print()
    
    print("🎉 ALL TESTS PASSED! 🎉")
    print("The lay_eggs flow correctly handles food trading and egg distribution.")

def test_lay_eggs_no_trade():
    """Test lay_eggs without bonus food trade."""
    print("=== Test: Lay Eggs No Trade ===")
    
    state = GameState()
    player = Player(id=1)
    
    # No food, so no trade option
    player.food = {}
    
    # Place bird with egg capacity
    bird = create_test_bird_with_capacity()
    player.board[1][0].bird = bird
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "main_turn"
    
    print(f"Player food: {player.food}")
    print(f"Bird eggs: {bird.eggs}/{bird.egg_limit}")
    
    # Step 1: Execute lay_eggs
    state = transition_state(state, "lay_eggs")
    
    # Should go directly to laying_eggs (no trade option)
    assert state.action_phase == "laying_eggs", f"Expected laying_eggs, got {state.action_phase}"
    print("✓ Correctly skipped trade phase (no food)")
    
    # Step 2: Get distribution options
    egg_actions = get_actions(state)
    print(f"Distribution options: {len(egg_actions)}")
    
    # Should be able to distribute base amount (2 eggs for grassland row[2])
    assert len(egg_actions) > 0, "No distribution options found"
    
    # Execute distribution
    distribution = json.loads(egg_actions[0])
    eggs_before = bird.eggs
    state = transition_state(state, egg_actions[0])
    current_player = state.players[0]
    eggs_after = current_player.board[1][0].bird.eggs
    
    print(f"Eggs: {eggs_before} → {eggs_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert eggs_after > eggs_before, "Eggs not added"
    print("✓ Lay eggs without trade completed successfully")
    print()

def test_lay_eggs_skip_trade():
    """Test lay_eggs with skip trade option."""
    print("=== Test: Lay Eggs Skip Trade ===")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    print(f"Player food: {current_player.food}")
    
    # Step 1: Execute lay_eggs
    state.action_phase = "main_turn"
    state = transition_state(state, "lay_eggs")
    
    # Should go to extra action choice
    assert state.action_phase == "extra_lay_eggs_action", f"Expected extra_lay_eggs_action, got {state.action_phase}"
    print("✓ Reached extra action choice")
    
    # Step 2: Skip trade
    food_before = current_player.food.copy()
    state = transition_state(state, "skip_trade")
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    # Should go to laying_eggs with base amount only
    assert state.action_phase == "laying_eggs", f"Expected laying_eggs, got {state.action_phase}"
    assert food_after == food_before, "Food changed when it shouldn't have"
    
    eggs_needed = state.action_data.get("eggs_needed")
    assert eggs_needed == 2, f"Expected base eggs_needed=2, got {eggs_needed}"  # Grassland spot [1][2] gives 2 eggs
    print("✓ Correctly skipped trade, moved to laying_eggs with base amount")
    
    # Step 3: Complete distribution
    egg_actions = get_actions(state)
    state = transition_state(state, egg_actions[0])
    current_player = state.players[0]
    
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    print("✓ Skip trade flow completed successfully")
    print()

def test_lay_eggs_no_capacity():
    """Test lay_eggs when no birds have egg capacity."""
    print("=== Test: Lay Eggs No Capacity ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Place bird with full egg capacity
    bird = create_test_bird_with_capacity()
    bird.eggs = bird.egg_limit  # Full capacity
    player.board[1][0].bird = bird
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "main_turn"
    
    print(f"Bird eggs: {bird.eggs}/{bird.egg_limit} (full)")
    
    # Step 1: Check main turn actions
    actions = get_actions(state)
    
    # lay_eggs should not be available (no capacity)
    assert "lay_eggs" not in actions, f"lay_eggs should not be available when no capacity, but found in {actions}"
    print("✓ lay_eggs correctly not available when no egg capacity")
    print()

def test_lay_eggs_excess_distribution():
    """Test that excess eggs are handled correctly."""
    print("=== Test: Lay Eggs Excess Distribution ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Set up scenario with limited capacity but many eggs to distribute
    player.food = {"fruit": 3}  # Can trade for extra eggs
    
    # Place bird with limited capacity
    bird = create_test_bird_with_capacity() 
    bird.eggs = 2  # Has 2, limit 3, so only 1 capacity
    player.board[1][0].bird = bird
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "main_turn"
    
    print(f"Bird capacity: {bird.egg_limit - bird.eggs} (limited)")
    print(f"Player food: {player.food}")
    
    # Execute lay_eggs with trade to get many eggs
    state = transition_state(state, "lay_eggs")
    state = transition_state(state, "trade_food")  # Trade for extra
    state = transition_state(state, "discard_food_fruit")  # Get +1 egg
    
    # Now we have base 2 + 1 extra = 3 eggs, but bird can only take 1
    eggs_needed = state.action_data.get("eggs_needed")
    print(f"Eggs to distribute: {eggs_needed}")
    print(f"Available capacity: 1")
    
    # Get distribution actions
    egg_actions = get_actions(state)
    print(f"Distribution options: {len(egg_actions)}")
    
    # Should have option to give 1 egg (excess 2 eggs are lost)
    valid_distributions = []
    for action in egg_actions:
        distribution = json.loads(action)
        total_distributed = sum(distribution.values())
        if total_distributed <= 1:  # Can't exceed capacity
            valid_distributions.append(distribution)
    
    assert len(valid_distributions) > 0, "No valid distributions found respecting capacity"
    print(f"✓ Valid distributions respect capacity limits: {valid_distributions}")
    
    # Execute one distribution
    state = transition_state(state, egg_actions[0])
    current_player = state.players[0]
    final_bird = current_player.board[1][0].bird
    
    assert final_bird.eggs <= final_bird.egg_limit, f"Eggs exceed limit: {final_bird.eggs}/{final_bird.egg_limit}"
    print(f"✓ Final bird eggs: {final_bird.eggs}/{final_bird.egg_limit} (within limit)")
    print()

if __name__ == "__main__":
    print("🎯 Running Comprehensive Lay Eggs Tests 🎯\n")
    
    # Main comprehensive test
    test_lay_eggs_comprehensive()
    
    # Edge case tests
    test_lay_eggs_no_trade()
    test_lay_eggs_skip_trade()
    test_lay_eggs_no_capacity()
    test_lay_eggs_excess_distribution()
    
    print("🎉 ALL LAY EGGS TESTS PASSED! 🎉")
    print("✅ Food trade mechanism works correctly")
    print("✅ Egg distribution works correctly")
    print("✅ No trade scenario works correctly")
    print("✅ Skip trade option works correctly")
    print("✅ No capacity edge case handled correctly")
    print("✅ Excess egg distribution handled correctly")