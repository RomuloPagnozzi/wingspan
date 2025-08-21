#!/usr/bin/env python3
"""
Comprehensive test for draw_cards flow with bonus egg trade and card selection.
Tests the complete action sequence and state management.
"""

import sys
sys.path.append('.')

from game.data import GameState, Player, Bird
from game.actions import get_actions
from game.engine import transition_state
import json

def create_test_bird_with_eggs():
    """Create a bird that has eggs for trading."""
    bird = Bird(
        id=777,
        name="Test Bird With Eggs",
        habitats=["wetland"],
        cost=[],
        points=2,
        nest="bowl",
        egg_limit=3,
        wingspan=20,
        power={}
    )
    bird.eggs = 2  # Has 2 eggs for trading
    return bird

def create_second_test_bird():
    """Create another bird for testing egg availability."""
    bird = Bird(
        id=888,
        name="Second Test Bird",
        habitats=["wetland"],
        cost=[],
        points=3,
        nest="cavity",
        egg_limit=2,
        wingspan=25,
        power={}
    )
    bird.eggs = 1  # Has 1 egg
    return bird

def setup_test_state():
    """Set up a game state for testing draw cards with bonus egg trade."""
    state = GameState()
    
    # Create player with birds that have eggs for trading
    player = Player(id=1)
    
    # Place birds with eggs on the wetland row
    # Place birds so the leftmost empty spot has extra_resource=True
    bird1 = create_test_bird_with_eggs()
    bird2 = create_second_test_bird()
    player.board[2][0].bird = bird1  # First wetland spot  
    player.board[2][2].bird = bird2  # Third wetland spot (skip [2][1] which has extra_resource=True)
    
    state.players = [player]
    state.current_player_index = 0
    
    # Ensure bird tray has cards
    if len(state.bird_tray) < 3:
        while len(state.bird_tray) < 3 and state.bird_deck:
            state.bird_tray.append(state.bird_deck.pop())
    
    return state, bird1, bird2

def test_draw_cards_comprehensive():
    """Test complete draw_cards flow with egg trade and card selection."""
    print("=== Comprehensive Draw Cards Test ===\n")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    # Print initial state
    print("Initial State:")
    print(f"Bird 1 on board: {bird1.name} (ID: {bird1.id}) - eggs: {bird1.eggs}/{bird1.egg_limit}")
    print(f"Bird 2 on board: {bird2.name} (ID: {bird2.id}) - eggs: {bird2.eggs}/{bird2.egg_limit}")
    print(f"Player hand size: {len(current_player.bird_hand)}")
    print(f"Bird tray: {[bird.id for bird in state.bird_tray]}")
    print(f"Bird deck size: {len(state.bird_deck)}")
    print(f"Wetland spot (next): resource_amount={current_player.board[2][1].resource_amount}, extra_resource={current_player.board[2][1].extra_resource}")
    print(f"Action cubes: {current_player.action_cubes}")
    print()
    
    # Step 1: Check if draw_cards is available
    state.action_phase = "main_turn"
    print("=== Step 1: Get main turn actions ===")
    actions = get_actions(state)
    print(f"Available actions: {actions}")
    
    assert "draw_cards" in actions, f"draw_cards action not found in {actions}"
    print("✓ Found draw_cards action")
    print()
    
    # Step 2: Execute draw_cards action (should trigger extra action choice)
    print("=== Step 2: Execute draw_cards action ===")
    state = transition_state(state, "draw_cards")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to extra_card_draw_action phase (player has eggs and spot has extra_resource=True)
    assert state.action_phase == "extra_card_draw_action", f"Expected extra_card_draw_action, got {state.action_phase}"
    base_cards = state.action_data.get("base_cards_amount")
    assert base_cards == 1, f"Expected base_cards_amount=1, got {base_cards}"  # Wetland row[1] gives 1 card
    print("✓ Correctly transitioned to extra_card_draw_action phase")
    print()
    
    # Step 3: Get extra action options
    print("=== Step 3: Get extra card draw actions ===")
    extra_actions = get_actions(state)
    print(f"Extra action options: {extra_actions}")
    
    assert "trade_egg" in extra_actions, "trade_egg option not found"
    assert "skip_trade" in extra_actions, "skip_trade option not found"
    print("✓ Found expected extra action options")
    print()
    
    # Step 4: Choose to trade egg for extra card
    print("=== Step 4: Execute trade_egg action ===")
    state = transition_state(state, "trade_egg")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to select_egg_to_discard phase
    assert state.action_phase == "select_egg_to_discard", f"Expected select_egg_to_discard, got {state.action_phase}"
    print("✓ Correctly transitioned to select_egg_to_discard phase")
    print()
    
    # Step 5: Get egg discard options
    print("=== Step 5: Get egg discard actions ===")
    egg_actions = get_actions(state)
    print(f"Egg discard options: {egg_actions}")
    
    # Should have options to discard eggs from birds with eggs
    expected_eggs = ["discard_egg_777", "discard_egg_888"]
    for egg_action in expected_eggs:
        assert egg_action in egg_actions, f"Expected egg action {egg_action} not found"
    print("✓ Found all expected egg discard options")
    print()
    
    # Step 6: Discard an egg
    print("=== Step 6: Execute egg discard ===")
    eggs_before = {
        bird1.id: current_player.board[2][0].bird.eggs,
        bird2.id: current_player.board[2][2].bird.eggs
    }
    state = transition_state(state, "discard_egg_777")
    # Get updated reference after state transition
    current_player = state.players[0]
    eggs_after = {
        bird1.id: current_player.board[2][0].bird.eggs,
        bird2.id: current_player.board[2][2].bird.eggs
    }
    
    print(f"Eggs before discard: {eggs_before}")
    print(f"Eggs after discard: {eggs_after}")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action_data: {state.action_data}")
    
    # Should transition to drawing_cards phase with extra card
    assert state.action_phase == "drawing_cards", f"Expected drawing_cards, got {state.action_phase}"
    assert eggs_after[bird1.id] == eggs_before[bird1.id] - 1, "Egg not discarded correctly"
    cards_needed = state.action_data.get("cards_needed")
    assert cards_needed == 2, f"Expected cards_needed=2 (1+1), got {cards_needed}"  # Base 1 + 1 extra
    print("✓ Egg discarded successfully, moved to drawing_cards phase with extra card")
    print()
    
    # Step 7: Get card draw options
    print("=== Step 7: Get card draw actions ===")
    card_actions = get_actions(state)
    print(f"Card draw options: {len(card_actions)} combinations")
    
    # Print first few options for inspection
    for i, action in enumerate(card_actions[:3]):
        selection = json.loads(action)
        print(f"  Option {i+1}: {selection}")
    
    # Should have various ways to draw 3 cards from tray/deck
    assert len(card_actions) > 0, "No card draw options found"
    print("✓ Found card draw options")
    print()
    
    # Step 8: Choose a draw selection (1 from tray, 1 from deck)
    print("=== Step 8: Execute card draw ===")
    tray_bird_ids = [bird.id for bird in state.bird_tray[:1]]  # Take first 1 from tray
    target_selection = json.dumps({"tray_birds": tray_bird_ids, "deck_cards": 1})
    
    # Verify this selection is available
    assert target_selection in card_actions, f"Target selection {target_selection} not found in options"
    
    hand_size_before = len(current_player.bird_hand)
    tray_size_before = len(state.bird_tray)
    deck_size_before = len(state.bird_deck)
    
    state = transition_state(state, target_selection)
    # Get updated references after state transition
    current_player = state.players[0]
    
    hand_size_after = len(current_player.bird_hand)
    tray_size_after = len(state.bird_tray)
    deck_size_after = len(state.bird_deck)
    
    print(f"Hand size: {hand_size_before} → {hand_size_after}")
    print(f"Tray size: {tray_size_before} → {tray_size_after}")
    print(f"Deck size: {deck_size_before} → {deck_size_after}")
    print(f"New action_phase: {state.action_phase}")
    print(f"Action cubes: {current_player.action_cubes}")
    print()
    
    # Should return to main_turn and cards should be drawn
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert hand_size_after == hand_size_before + 2, f"Hand size not updated correctly"
    assert tray_size_after == 3, f"Tray not refilled correctly"  # Should always be 3
    assert deck_size_after == deck_size_before - 2, f"Deck size not updated correctly"  # 1 for refill + 1 drawn
    assert current_player.action_cubes == 7, "Action cube not deducted"
    print("✓ Cards drawn successfully, returned to main_turn phase")
    print()
    
    # Step 9: Verify cards were drawn from correct sources
    print("=== Step 9: Verify card sources ===")
    hand_bird_ids = [bird.id for bird in current_player.bird_hand]
    
    # Check that the tray birds we selected are now in hand
    for bird_id in tray_bird_ids:
        assert bird_id in hand_bird_ids, f"Tray bird {bird_id} not found in hand"
    print(f"✓ Tray birds {tray_bird_ids} successfully drawn to hand")
    
    # Step 10: Verify final state
    print("=== Step 10: Verify final state ===")
    current_player = state.players[0]  # Ensure fresh reference
    final_bird1 = current_player.board[2][0].bird
    final_bird2 = current_player.board[2][2].bird
    
    print(f"Final bird1 eggs: {final_bird1.eggs}/{final_bird1.egg_limit}")
    print(f"Final bird2 eggs: {final_bird2.eggs}/{final_bird2.egg_limit}")
    print(f"Final hand size: {len(current_player.bird_hand)}")
    print(f"Final action cubes: {current_player.action_cubes}")
    
    assert final_bird1.eggs == 1, f"Bird1 should have 1 egg, has {final_bird1.eggs}"
    assert final_bird2.eggs == 1, f"Bird2 should have 1 egg, has {final_bird2.eggs}"
    assert len(current_player.bird_hand) == 2, f"Should have 2 cards in hand, has {len(current_player.bird_hand)}"  # 0 initial + 2 drawn
    print("✓ All final state checks passed")
    print()
    
    print("🎉 ALL TESTS PASSED! 🎉")
    print("The draw_cards flow correctly handles egg trading and card selection.")

def test_draw_cards_no_trade():
    """Test draw_cards without bonus egg trade."""
    print("=== Test: Draw Cards No Trade ===")
    
    state = GameState()
    player = Player(id=1)
    
    # No birds with eggs, so no trade option
    state.players = [player]
    state.current_player_index = 0
    state.action_phase = "main_turn"
    
    print("No birds with eggs on board")
    
    # Step 1: Execute draw_cards
    state = transition_state(state, "draw_cards")
    
    # Should go directly to drawing_cards (no trade option)
    assert state.action_phase == "drawing_cards", f"Expected drawing_cards, got {state.action_phase}"
    print("✓ Correctly skipped trade phase (no eggs)")
    
    # Step 2: Get draw options
    card_actions = get_actions(state)
    print(f"Draw options: {len(card_actions)}")
    
    # Should be able to draw base amount (3 cards for wetland row[1])
    assert len(card_actions) > 0, "No draw options found"
    
    # Execute draw
    hand_size_before = len(player.bird_hand)
    state = transition_state(state, card_actions[0])
    current_player = state.players[0]
    hand_size_after = len(current_player.bird_hand)
    
    print(f"Hand size: {hand_size_before} → {hand_size_after}")
    print(f"Final action_phase: {state.action_phase}")
    
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert hand_size_after > hand_size_before, "Cards not added"
    print("✓ Draw cards without trade completed successfully")
    print()

def test_draw_cards_skip_trade():
    """Test draw_cards with skip trade option."""
    print("=== Test: Draw Cards Skip Trade ===")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    print(f"Bird eggs available: {bird1.eggs + bird2.eggs}")
    
    # Step 1: Execute draw_cards
    state.action_phase = "main_turn"
    state = transition_state(state, "draw_cards")
    
    # Should go to extra action choice
    assert state.action_phase == "extra_card_draw_action", f"Expected extra_card_draw_action, got {state.action_phase}"
    print("✓ Reached extra action choice")
    
    # Step 2: Skip trade
    eggs_before = {
        bird1.id: current_player.board[2][0].bird.eggs,
        bird2.id: current_player.board[2][2].bird.eggs
    }
    state = transition_state(state, "skip_trade")
    current_player = state.players[0]
    eggs_after = {
        bird1.id: current_player.board[2][0].bird.eggs,
        bird2.id: current_player.board[2][2].bird.eggs
    }
    
    # Should go to drawing_cards with base amount only
    assert state.action_phase == "drawing_cards", f"Expected drawing_cards, got {state.action_phase}"
    assert eggs_after == eggs_before, "Eggs changed when they shouldn't have"
    
    cards_needed = state.action_data.get("cards_needed")
    assert cards_needed == 1, f"Expected base cards_needed=1, got {cards_needed}"  # Wetland spot [2][1] gives 1 card
    print("✓ Correctly skipped trade, moved to drawing_cards with base amount")
    
    # Step 3: Complete draw
    card_actions = get_actions(state)
    hand_size_before = len(current_player.bird_hand)
    state = transition_state(state, card_actions[0])
    current_player = state.players[0]
    hand_size_after = len(current_player.bird_hand)
    
    assert state.action_phase == "main_turn", f"Expected main_turn, got {state.action_phase}"
    assert current_player.action_cubes == 7, "Action cube not deducted"
    assert hand_size_after == hand_size_before + 1, "Should have drawn 1 card"
    print("✓ Skip trade flow completed successfully")
    print()

def test_draw_cards_deck_only():
    """Test drawing cards only from deck."""
    print("=== Test: Draw Cards Deck Only ===")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    # Go through full flow to get to card selection
    state.action_phase = "main_turn"
    state = transition_state(state, "draw_cards")
    state = transition_state(state, "skip_trade")  # Skip trade for simplicity
    
    # Get draw options
    card_actions = get_actions(state)
    
    # Find option that draws all from deck
    deck_only_action = None
    for action in card_actions:
        selection = json.loads(action)
        if len(selection["tray_birds"]) == 0:
            deck_only_action = action
            break
    
    assert deck_only_action is not None, "No deck-only option found"
    print(f"Found deck-only option: {deck_only_action}")
    
    # Execute deck-only draw
    hand_size_before = len(current_player.bird_hand)
    deck_size_before = len(state.bird_deck)
    tray_before = [bird.id for bird in state.bird_tray]
    
    state = transition_state(state, deck_only_action)
    current_player = state.players[0]
    
    hand_size_after = len(current_player.bird_hand)
    deck_size_after = len(state.bird_deck)
    tray_after = [bird.id for bird in state.bird_tray]
    
    print(f"Hand size: {hand_size_before} → {hand_size_after}")
    print(f"Deck size: {deck_size_before} → {deck_size_after}")
    print(f"Tray before: {tray_before}")
    print(f"Tray after: {tray_after}")
    
    # Tray should be unchanged, cards drawn only from deck
    assert tray_after == tray_before, "Tray changed when drawing from deck only"
    assert hand_size_after == hand_size_before + 1, "Should have drawn 1 card from deck"
    print("✓ Deck-only draw completed successfully")
    print()

def test_draw_cards_tray_only():
    """Test drawing cards only from tray."""
    print("=== Test: Draw Cards Tray Only ===")
    
    state, bird1, bird2 = setup_test_state()
    current_player = state.players[0]
    
    # Go through full flow to get to card selection
    state.action_phase = "main_turn"
    state = transition_state(state, "draw_cards")
    state = transition_state(state, "skip_trade")  # Skip trade for simplicity
    
    # Get draw options
    card_actions = get_actions(state)
    
    # Find option that draws all from tray (if possible with only 1 card needed)
    tray_only_action = None
    for action in card_actions:
        selection = json.loads(action)
        if selection["deck_cards"] == 0 and len(selection["tray_birds"]) == 1:
            tray_only_action = action
            break
    
    assert tray_only_action is not None, "No tray-only option found"
    print(f"Found tray-only option: {tray_only_action}")
    
    # Execute tray-only draw
    hand_size_before = len(current_player.bird_hand)
    deck_size_before = len(state.bird_deck)
    tray_before = [bird.id for bird in state.bird_tray]
    
    state = transition_state(state, tray_only_action)
    current_player = state.players[0]
    
    hand_size_after = len(current_player.bird_hand)
    deck_size_after = len(state.bird_deck)
    tray_after = [bird.id for bird in state.bird_tray]
    
    print(f"Hand size: {hand_size_before} → {hand_size_after}")
    print(f"Deck size: {deck_size_before} → {deck_size_after}")
    print(f"Tray before: {tray_before}")
    print(f"Tray after: {tray_after}")
    
    # Should have drawn from tray and refilled from deck
    assert hand_size_after == hand_size_before + 1, "Should have drawn 1 card from tray"
    assert len(state.bird_tray) == 3, "Tray should be refilled to 3 cards"
    assert deck_size_after == deck_size_before - 1, "Deck should have provided 1 card for refill"
    print("✓ Tray-only draw completed successfully")
    print()

if __name__ == "__main__":
    print("🎯 Running Comprehensive Draw Cards Tests 🎯\n")
    
    # Main comprehensive test
    test_draw_cards_comprehensive()
    
    # Edge case tests
    test_draw_cards_no_trade()
    test_draw_cards_skip_trade()
    test_draw_cards_deck_only()
    test_draw_cards_tray_only()
    
    print("🎉 ALL DRAW CARDS TESTS PASSED! 🎉")
    print("✅ Egg trade mechanism works correctly")
    print("✅ Card selection works correctly")
    print("✅ No trade scenario works correctly")
    print("✅ Skip trade option works correctly")
    print("✅ Deck-only drawing works correctly")
    print("✅ Tray-only drawing works correctly")