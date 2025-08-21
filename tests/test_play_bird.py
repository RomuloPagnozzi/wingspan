#!/usr/bin/env python3
"""
Comprehensive test for play_bird flow with both egg and food payment requirements.
Tests the complete action sequence and state management.
"""

import sys
sys.path.append('.')

from game.data import GameState, Player, Bird
from game.actions import get_actions
from game.engine import transition_state
import json

def create_test_bird_with_cost():
    """Create a bird that requires food payment."""
    return Bird(
        id=999,
        name="Test Expensive Bird", 
        habitats=["forest"],
        cost=[{"seed": 2, "fruit": 1}],  # Requires 2 seeds + 1 fruit
        points=3,
        nest="bowl",
        egg_limit=2,
        wingspan=25,
        power={}
    )

def create_test_bird_with_eggs():
    """Create a bird already on board with eggs for payment."""
    bird = Bird(
        id=888,
        name="Test Bird With Eggs",
        habitats=["forest"], 
        cost=[],
        points=1,
        nest="bowl",
        egg_limit=3,
        wingspan=20,
        power={}
    )
    bird.eggs = 2  # Has 2 eggs available
    return bird

def setup_test_state():
    """Set up a game state for testing both egg and food payment."""
    state = GameState()
    
    # Create player with resources
    player = Player(id=1)
    player.food = {
        "invertebrate": 1,
        "seed": 3,        # Enough to pay bird cost  
        "fish": 1,
        "fruit": 2,       # Enough to pay bird cost
        "rodent": 1
    }
    
    # Add test bird to player's hand (requires food payment)
    test_bird = create_test_bird_with_cost()
    player.bird_hand = [test_bird]
    
    # Place a bird with eggs on the board (for egg payment)
    bird_with_eggs = create_test_bird_with_eggs() 
    player.board[0][0].bird = bird_with_eggs  # Place in first forest spot
    
    state.players = [player]
    state.current_player_index = 0
    
    return state, test_bird

def test_play_bird_comprehensive():
    """Test complete play_bird flow with both egg and food payments."""
    print("=== Comprehensive Play Bird Test ===\n")
    
    state, test_bird = setup_test_state()
    current_player = state.players[0]
    
    # Print initial state
    print("Initial State:")
    print(f"Player food: {current_player.food}")
    print(f"Bird in hand: {test_bird.name} (ID: {test_bird.id})")
    print(f"Bird cost: {test_bird.cost}")
    board_bird = current_player.board[0][0].bird
    print(f"Bird on board with eggs: {board_bird.name if board_bird else 'None'} with {board_bird.eggs if board_bird else 0} eggs")
    print(f"Target spot (forest[0][1]): egg_cost={current_player.board[0][1].egg_cost}")
    print()
    
    # Step 1: Start play_bird action
    state.action_phase = "play_bird"
    print("=== Step 1: Get play_bird actions ===")
    actions = get_actions(state)
    print(f"Available actions: {actions}")
    
    # Should have action to play test bird at forest spot [0][1] (which has egg_cost=1)
    target_action = f"play_bird_{test_bird.id}_at_0_1"
    assert target_action in actions, f"Expected action {target_action} not found in {actions}"
    print(f"✓ Found expected action: {target_action}")
    print()
    
    # Step 2: Execute play_bird action (should trigger egg payment)
    print("=== Step 2: Execute play_bird action ===")
    state = transition_state(state, target_action)
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to pay_egg_cost phase
    assert state.action_phase == "pay_egg_cost", f"Expected pay_egg_cost, got {state.action_phase}"
    assert state.action_data.get("egg_cost") == 1, f"Expected egg_cost=1, got {state.action_data.get('egg_cost')}"
    print("✓ Correctly transitioned to pay_egg_cost phase")
    print()
    
    # Step 3: Get egg payment options
    print("=== Step 3: Get egg payment actions ===")
    egg_actions = get_actions(state)
    print(f"Egg payment options: {egg_actions}")
    
    # Should have option to pay 1 egg from bird ID 888
    expected_payment = json.dumps({888: 1})
    assert expected_payment in egg_actions, f"Expected payment {expected_payment} not found"
    print(f"✓ Found expected egg payment option: {expected_payment}")
    print()
    
    # Step 4: Pay egg cost
    print("=== Step 4: Execute egg payment ===")
    board_bird = current_player.board[0][0].bird
    assert board_bird is not None, "Board bird should exist for egg payment"
    eggs_before = board_bird.eggs
    state = transition_state(state, expected_payment)
    # Get updated reference after state transition
    current_player = state.players[0]
    board_bird_after = current_player.board[0][0].bird
    eggs_after = board_bird_after.eggs if board_bird_after else 0
    
    print(f"Eggs before payment: {eggs_before}")
    print(f"Eggs after payment: {eggs_after}")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to pay_food_cost phase (THE CRITICAL TEST!)
    assert eggs_after == eggs_before - 1, "Egg payment failed"
    assert state.action_phase == "pay_food_cost", f"Expected pay_food_cost, got {state.action_phase}"
    print("✓ Egg payment successful, correctly transitioned to pay_food_cost phase")
    print()
    
    # Step 5: Get food payment options  
    print("=== Step 5: Get food payment actions ===")
    food_actions = get_actions(state)
    print(f"Food payment options: {food_actions}")
    
    # Should have option to pay bird's food cost
    expected_food_payment = json.dumps({"seed": 2, "fruit": 1})
    assert expected_food_payment in food_actions, f"Expected payment {expected_food_payment} not found"
    print(f"✓ Found expected food payment option: {expected_food_payment}")
    print()
    
    # Step 6: Pay food cost
    print("=== Step 6: Execute food payment ===")
    food_before = current_player.food.copy()
    state = transition_state(state, expected_food_payment)
    # Get updated reference after state transition
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    print(f"Food before payment: {food_before}")
    print(f"Food after payment: {food_after}")
    print(f"New action_phase: {state.action_phase}")
    print()
    
    # Should return to main_turn and bird should be placed
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert food_after["seed"] == food_before["seed"] - 2, "Seed payment failed"
    assert food_after["fruit"] == food_before["fruit"] - 1, "Fruit payment failed"
    print("✓ Food payment successful, returned to main_turn phase")
    
    # Step 7: Verify bird placement
    print("=== Step 7: Verify final state ===")
    current_player = state.players[0]  # Ensure fresh reference
    target_spot = current_player.board[0][1]
    
    print(f"Bird at target spot: {target_spot.bird}")
    print(f"Bird in hand: {len(current_player.bird_hand)} birds")
    
    assert target_spot.bird is not None, "Bird was not placed on board"
    assert target_spot.bird.id == test_bird.id, f"Wrong bird placed: {target_spot.bird.id} vs {test_bird.id}"
    assert len(current_player.bird_hand) == 0, "Bird was not removed from hand"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    print("✓ Bird successfully placed on board and removed from hand")
    print()
    
    print("🎉 ALL TESTS PASSED! 🎉")
    print("The play_bird flow correctly handles both egg and food payments.")

def create_free_bird():
    """Create a bird with no cost (free to play)."""
    return Bird(
        id=1001,
        name="Free Bird",
        habitats=["forest"],
        cost=[],  # No cost
        points=1,
        nest="bowl",
        egg_limit=2,
        wingspan=15,
        power={}
    )

def create_bird_with_2_to_1_trade():
    """Create a bird requiring 2:1 trade (player lacks exact food)."""
    return Bird(
        id=1002,
        name="Trade Required Bird",
        habitats=["forest"],
        cost=[{"fruit": 3}],  # Player will only have 2 fruit, needs 2:1 trade
        points=2,
        nest="cavity",
        egg_limit=2,
        wingspan=20,
        power={}
    )

def create_bird_with_wild_cost():
    """Create a bird with wild cost."""
    return Bird(
        id=1003,
        name="Wild Cost Bird",
        habitats=["forest"],
        cost=[{"wild": 2}],  # Any 2 food types
        points=3,
        nest="platform",
        egg_limit=3,
        wingspan=25,
        power={}
    )

def create_bird_with_mixed_cost():
    """Create a bird with both specific and wild costs."""
    return Bird(
        id=1004,
        name="Mixed Cost Bird",
        habitats=["forest"],
        cost=[{"seed": 1, "wild": 1}],  # 1 seed + any 1 food
        points=4,
        nest="bowl",
        egg_limit=2,
        wingspan=30,
        power={}
    )

def test_free_bird_no_egg_cost():
    """Test: Free bird on spot with no egg cost - direct placement."""
    print("=== Test: Free Bird, No Egg Cost ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Free bird 
    free_bird = create_free_bird()
    player.bird_hand = [free_bird]
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "play_bird"
    
    print(f"Bird cost: {free_bird.cost}")
    print(f"Target spot egg_cost: {player.board[0][0].egg_cost}")
    
    # Step 1: Get actions
    actions = get_actions(state)
    target_action = f"play_bird_{free_bird.id}_at_0_0"
    assert target_action in actions, f"Action {target_action} not found"
    print(f"✓ Found action: {target_action}")
    
    # Step 2: Execute action - should place directly
    state = transition_state(state, target_action)
    current_player = state.players[0]
    
    print(f"Final action_phase: {state.action_phase}")
    print(f"Action cubes: {current_player.action_cubes}")
    
    # Verify direct placement
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.board[0][0].bird is not None, "Bird not placed"
    assert current_player.board[0][0].bird.id == free_bird.id, "Wrong bird placed"
    assert len(current_player.bird_hand) == 0, "Bird not removed from hand"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    
    print("✓ Free bird placed directly with no payments required")
    print()

def test_free_bird_with_egg_cost():
    """Test: Free bird on spot requiring egg payment."""
    print("=== Test: Free Bird, With Egg Cost ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Free bird
    free_bird = create_free_bird()
    player.bird_hand = [free_bird]
    
    # Place bird with eggs on board
    egg_bird = create_test_bird_with_eggs()
    player.board[0][0].bird = egg_bird
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "play_bird"
    
    print(f"Bird cost: {free_bird.cost}")
    print(f"Target spot egg_cost: {player.board[0][1].egg_cost}")
    print(f"Available eggs: {egg_bird.eggs}")
    
    # Step 1: Get actions
    actions = get_actions(state)
    target_action = f"play_bird_{free_bird.id}_at_0_1"
    assert target_action in actions, f"Action {target_action} not found"
    print(f"✓ Found action: {target_action}")
    
    # Step 2: Execute - should go to egg payment
    state = transition_state(state, target_action)
    assert state.action_phase == "pay_egg_cost", f"Expected pay_egg_cost, got {state.action_phase}"
    print("✓ Correctly transitioned to pay_egg_cost")
    
    # Step 3: Pay eggs
    egg_actions = get_actions(state)
    egg_payment = json.dumps({888: 1})
    assert egg_payment in egg_actions, f"Payment {egg_payment} not found"
    
    eggs_before = player.board[0][0].bird.eggs
    state = transition_state(state, egg_payment)
    current_player = state.players[0]
    eggs_after = current_player.board[0][0].bird.eggs
    
    print(f"Eggs: {eggs_before} → {eggs_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    # Verify final state
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert eggs_after == eggs_before - 1, "Eggs not deducted"
    assert current_player.board[0][1].bird is not None, "Bird not placed"
    assert current_player.board[0][1].bird.id == free_bird.id, "Wrong bird placed"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    
    print("✓ Free bird placed after egg payment only")
    print()

def test_bird_with_2_to_1_trade():
    """Test: Bird requiring 2:1 trade for food payment."""
    print("=== Test: Bird Requiring 2:1 Trade ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Bird requiring 3 fruit, but player only has 2 fruit + other foods for trade
    trade_bird = create_bird_with_2_to_1_trade()
    player.bird_hand = [trade_bird]
    
    # Set up food: only 2 fruit but plenty of other foods for 2:1 trades
    player.food = {
        "invertebrate": 4,  # Can trade 2 → 1 fruit
        "seed": 4,          # Can trade 2 → 1 fruit  
        "fish": 1,
        "fruit": 2,         # Need 3 total, have 2, need 1 more via trade
        "rodent": 2
    }
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "play_bird"
    
    print(f"Bird cost: {trade_bird.cost}")
    print(f"Player food: {player.food}")
    print(f"Target spot egg_cost: {player.board[0][0].egg_cost}")
    
    # Step 1: Get actions
    actions = get_actions(state)
    target_action = f"play_bird_{trade_bird.id}_at_0_0"
    assert target_action in actions, f"Action {target_action} not found"
    print(f"✓ Found action: {target_action}")
    
    # Step 2: Execute - should go to food payment
    state = transition_state(state, target_action)
    assert state.action_phase == "pay_food_cost", f"Expected pay_food_cost, got {state.action_phase}"
    print("✓ Correctly transitioned to pay_food_cost")
    
    # Step 3: Get food payment options (should include 2:1 trades)
    food_actions = get_actions(state)
    print(f"Food payment options: {len(food_actions)} available")
    
    # Find a valid 2:1 trade payment
    valid_payment = None
    for action in food_actions:
        payment = json.loads(action)
        # Look for payment that uses 2:1 trade (more resources than cost)
        if sum(payment.values()) > 3:  # More than the 3 fruit needed
            valid_payment = action
            break
    
    assert valid_payment is not None, f"No 2:1 trade payment found in {food_actions}"
    print(f"✓ Found 2:1 trade payment option")
    
    # Step 4: Execute payment
    food_before = player.food.copy()
    state = transition_state(state, valid_payment)
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    print(f"Food before: {food_before}")
    print(f"Food after: {food_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    # Verify final state
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.board[0][0].bird is not None, "Bird not placed"
    assert current_player.board[0][0].bird.id == trade_bird.id, "Wrong bird placed"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    
    # Verify more resources were spent than the base cost (proving 2:1 trade)
    total_spent = sum(food_before[food] - food_after.get(food, 0) for food in food_before)
    assert total_spent > 3, f"Expected >3 resources spent for 2:1 trade, got {total_spent}"
    
    print("✓ Bird placed using 2:1 trade mechanism")
    print()

def test_bird_with_wild_cost():
    """Test: Bird with wild cost payment."""
    print("=== Test: Bird With Wild Cost ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Bird requiring 2 wild (any food types)
    wild_bird = create_bird_with_wild_cost()
    player.bird_hand = [wild_bird]
    
    # Set up food with variety for wild payment
    player.food = {
        "invertebrate": 2,
        "seed": 1,
        "fish": 1,
        "fruit": 1,
        "rodent": 1
    }
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "play_bird"
    
    print(f"Bird cost: {wild_bird.cost}")
    print(f"Player food: {player.food}")
    
    # Step 1: Get actions
    actions = get_actions(state)
    target_action = f"play_bird_{wild_bird.id}_at_0_0"
    assert target_action in actions, f"Action {target_action} not found"
    print(f"✓ Found action: {target_action}")
    
    # Step 2: Execute - should go to food payment
    state = transition_state(state, target_action)
    assert state.action_phase == "pay_food_cost", f"Expected pay_food_cost, got {state.action_phase}"
    print("✓ Correctly transitioned to pay_food_cost")
    
    # Step 3: Get food payment options
    food_actions = get_actions(state)
    print(f"Food payment options: {len(food_actions)} available")
    
    # Should have various wild payment combinations
    assert len(food_actions) > 0, "No food payment options found"
    
    # Pick first valid payment
    valid_payment = food_actions[0]
    payment = json.loads(valid_payment)
    
    # Verify it uses exactly 2 food items for wild cost
    total_used = sum(payment.values())
    assert total_used == 2, f"Expected 2 food for wild cost, got {total_used}"
    print(f"✓ Wild payment uses exactly 2 food: {payment}")
    
    # Step 4: Execute payment
    food_before = player.food.copy()
    state = transition_state(state, valid_payment)
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    print(f"Food before: {food_before}")
    print(f"Food after: {food_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    # Verify final state
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.board[0][0].bird is not None, "Bird not placed"
    assert current_player.board[0][0].bird.id == wild_bird.id, "Wrong bird placed"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    
    print("✓ Bird with wild cost placed successfully")
    print()

def test_bird_with_mixed_cost():
    """Test: Bird with both specific and wild costs."""
    print("=== Test: Bird With Mixed Cost (Specific + Wild) ===")
    
    state = GameState()
    player = Player(id=1)
    
    # Bird requiring 1 seed + 1 wild
    mixed_bird = create_bird_with_mixed_cost()
    player.bird_hand = [mixed_bird]
    
    # Set up food
    player.food = {
        "invertebrate": 1,
        "seed": 2,      # Has enough seed for specific cost
        "fish": 1,      # Can use for wild
        "fruit": 1,
        "rodent": 1
    }
    
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "play_bird"
    
    print(f"Bird cost: {mixed_bird.cost}")
    print(f"Player food: {player.food}")
    
    # Step 1: Get actions
    actions = get_actions(state)
    target_action = f"play_bird_{mixed_bird.id}_at_0_0"
    assert target_action in actions, f"Action {target_action} not found"
    print(f"✓ Found action: {target_action}")
    
    # Step 2: Execute - should go to food payment
    state = transition_state(state, target_action)
    assert state.action_phase == "pay_food_cost", f"Expected pay_food_cost, got {state.action_phase}"
    print("✓ Correctly transitioned to pay_food_cost")
    
    # Step 3: Get food payment options
    food_actions = get_actions(state)
    print(f"Food payment options: {len(food_actions)} available")
    
    # Should have payment that includes 1 seed + 1 other food
    valid_payment = None
    for action in food_actions:
        payment = json.loads(action)
        if payment.get("seed", 0) >= 1 and sum(payment.values()) == 2:
            valid_payment = action
            break
    
    assert valid_payment is not None, "No valid mixed cost payment found"
    payment = json.loads(valid_payment)
    print(f"✓ Found mixed cost payment: {payment}")
    
    # Step 4: Execute payment
    food_before = player.food.copy()
    state = transition_state(state, valid_payment)
    current_player = state.players[0]
    food_after = current_player.food.copy()
    
    print(f"Food before: {food_before}")
    print(f"Food after: {food_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    # Verify final state
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.board[0][0].bird is not None, "Bird not placed"
    assert current_player.board[0][0].bird.id == mixed_bird.id, "Wrong bird placed"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    
    # Verify correct amounts deducted
    assert food_after["seed"] == food_before["seed"] - payment["seed"], "Seed not deducted correctly"
    
    print("✓ Bird with mixed cost (specific + wild) placed successfully")
    print()

if __name__ == "__main__":
    print("🎯 Running Comprehensive Play Bird Tests 🎯\n")
    
    # Original comprehensive test
    test_play_bird_comprehensive()
    
    # Edge case tests
    test_free_bird_no_egg_cost()
    test_free_bird_with_egg_cost()
    test_bird_with_2_to_1_trade()
    test_bird_with_wild_cost()
    test_bird_with_mixed_cost()
    
    print("🎉 ALL COMPREHENSIVE TESTS PASSED! 🎉")
    print("✅ Both egg and food payment flows work correctly")
    print("✅ Free birds work correctly")
    print("✅ 2:1 trade mechanism works correctly") 
    print("✅ Wild cost payment works correctly")
    print("✅ Mixed cost payment works correctly")