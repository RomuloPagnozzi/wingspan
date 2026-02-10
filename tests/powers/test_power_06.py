"""Comprehensive end-to-end test for Power 6: Draw N+1 cards, all players select clockwise."""

from game.core import (
    initiate_state,
    GamePhase,
    get_bird_card,
    SimpleAction,
    IdAction,
    PlayBirdAction,
    FoodMapAction,
    frozen_map,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import place_bird_on_board, setup_power_execution


def test_power_6_full_game_scenario_with_3_players():
    """
    End-to-end test: Power 6 in a realistic 3-player game scenario.

    Game scenario:
    - 3 players
    - Player 0 plays American Oystercatcher (ID 8) with Power 6
    - Power 6: "Draw cards equal to number of players +1. Starting with you and
      proceeding clockwise, each player selects 1. You keep the extra card."
    - Should draw 4 cards (3 players + 1)
    - Selection order: Player 0 -> Player 1 -> Player 2 -> Player 0
    - Final result: Each player gets 1 card, Player 0 gets 2 cards total
    """
    # Setup: Create 3-player game
    state = initiate_state(3)
    state.game_phase = GamePhase.MAIN_TURN
    state.current_player_index = 0

    # Give player 0 resources to play the bird
    player0 = state.players[0]
    player0.action_cubes = 5
    player0.food = {"invertebrate": 3, "seed": 2}

    # Get the American Oystercatcher (Power 6 bird)
    power_6_bird_id = 8
    bird_card = get_bird_card(power_6_bird_id)
    assert bird_card is not None, "Bird ID 8 should exist"
    assert bird_card.name == "American Oystercatcher"

    # Add bird to player's hand (as ID)
    player0.bird_hand.append(power_6_bird_id)

    initial_deck_size = len(state.bird_deck)

    # Player 0 chooses to play a bird
    state = transition_state(state, SimpleAction("play_bird"))
    assert state.game_phase == GamePhase.PLAY_BIRD

    # Check available actions - should be able to play the bird in wetland habitat
    actions = get_actions(state)
    play_action = PlayBirdAction(power_6_bird_id, 2, 0)  # Wetland row, first spot
    assert play_action in actions, f"Should be able to play bird. Actions: {actions}"

    # Play the bird in wetland (row 2, col 0)
    state = transition_state(state, play_action)

    # Should transition to pay food cost
    assert state.game_phase == GamePhase.PAY_FOOD_COST
    assert state.action_data.pending_cost is not None
    assert state.action_data.pending_cost.cost_type == "food"

    # Pay the food cost (2 invertebrates)
    payment = {"invertebrate": 2}
    state = transition_state(state, FoodMapAction("pay_food", frozen_map(payment)))

    # After paying and placing bird, white power should trigger
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.powers_queue is not None

    # Verify the bird is on the board
    assert state.players[0].board[2][0].bird is not None
    assert state.players[0].board[2][0].bird.id == power_6_bird_id

    # Note: Action cube not yet consumed - will be consumed after power activates
    assert player0.action_cubes == 5

    # Query actual hand sizes AFTER bird was played - this is our baseline for power 6
    hand_size_p0_before_power = len(state.players[0].bird_hand)
    hand_size_p1_before_power = len(state.players[1].bird_hand)
    hand_size_p2_before_power = len(state.players[2].bird_hand)

    # Check the power queue
    powers_queue = state.action_data.powers_queue
    assert len(powers_queue) == 1
    current_power = powers_queue[0]
    assert current_power.power_data["data"]["id"] == 6

    # Get available actions - should be able to activate or skip
    actions = get_actions(state)
    assert SimpleAction("activate_power") in actions
    assert SimpleAction("skip_power") in actions

    # Activate Power 6
    state = transition_state(state, SimpleAction("activate_power"))

    # Should be in select_card phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    current_exec = state.action_data.execution_stack[-1]
    assert current_exec.phase == "select_card"

    # Verify 4 cards were drawn (3 players + 1)
    # available_cards now contains bird IDs, not Bird objects
    available_ids = current_exec.context.get("available_cards", [])
    assert len(available_ids) == 4, "Should draw 4 cards for 3 players"
    assert len(state.bird_deck) == initial_deck_size - 4, "4 cards removed from deck"

    # Verify player order: [0, 1, 2, 0]
    awaiting_players = current_exec.context.get("awaiting_players", [])
    assert awaiting_players == [
        0,
        1,
        2,
        0,
    ], "Should cycle clockwise with activator twice"
    assert current_exec.context.get("activator") == 0

    # Current player should be Player 0 (activator goes first)
    assert state.current_player_index == 0

    # Get available card selection actions
    actions = get_actions(state)
    assert len(actions) == 4, "Should have 4 cards to choose from"
    assert all(
        isinstance(action, IdAction) and action.type == "select_card"
        for action in actions
    )

    # Store card IDs for verification
    ids = list(available_ids)

    # Player 0 selects first card
    selected_card_0_first_id = available_ids[0]
    state = transition_state(state, IdAction("select_card", selected_card_0_first_id))

    # Verify Player 0 received the card - query actual hand size
    assert selected_card_0_first_id in state.players[0].bird_hand
    assert len(state.players[0].bird_hand) == hand_size_p0_before_power + 1

    # Should advance to Player 1
    assert state.current_player_index == 1
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    current_exec = state.action_data.execution_stack[-1]
    assert current_exec.phase == "select_card"

    # Verify 3 cards remain
    remaining_ids = current_exec.context.get("available_cards", [])
    assert len(remaining_ids) == 3
    assert selected_card_0_first_id not in remaining_ids

    # Player 1 selects a card
    actions = get_actions(state)
    assert len(actions) == 3
    selected_card_1_id = remaining_ids[0]
    state = transition_state(state, IdAction("select_card", selected_card_1_id))

    # Verify Player 1 received the card - query actual state
    assert selected_card_1_id in state.players[1].bird_hand
    assert len(state.players[1].bird_hand) == hand_size_p1_before_power + 1

    # Should advance to Player 2
    assert state.current_player_index == 2
    current_exec = state.action_data.execution_stack[-1]
    remaining_ids = current_exec.context.get("available_cards", [])
    assert len(remaining_ids) == 2

    # Player 2 selects a card
    actions = get_actions(state)
    assert len(actions) == 2
    selected_card_2_id = remaining_ids[0]
    state = transition_state(state, IdAction("select_card", selected_card_2_id))

    # Verify Player 2 received the card - query actual state
    assert selected_card_2_id in state.players[2].bird_hand
    assert len(state.players[2].bird_hand) == hand_size_p2_before_power + 1

    # Should cycle back to Player 0 for second selection
    assert state.current_player_index == 0
    current_exec = state.action_data.execution_stack[-1]
    remaining_ids = current_exec.context.get("available_cards", [])
    assert len(remaining_ids) == 1

    # Player 0 selects the last card
    actions = get_actions(state)
    assert len(actions) == 1
    selected_card_0_second_id = remaining_ids[0]
    state = transition_state(state, IdAction("select_card", selected_card_0_second_id))

    # Verify Player 0 received the second card - query actual state
    assert selected_card_0_second_id in state.players[0].bird_hand
    assert (
        len(state.players[0].bird_hand) == hand_size_p0_before_power + 2
    ), "Activator should have gained 2 cards total from power"

    # Verify all cards were distributed - execution stack should be empty now
    assert len(state.action_data.execution_stack) == 0

    # Should transition back to MAIN_TURN
    assert state.game_phase == GamePhase.MAIN_TURN

    # Verify action cube was consumed
    assert state.players[0].action_cubes == 4

    # Verify final hand sizes - query actual final state
    final_hand_size_p0 = len(state.players[0].bird_hand)
    final_hand_size_p1 = len(state.players[1].bird_hand)
    final_hand_size_p2 = len(state.players[2].bird_hand)

    assert (
        final_hand_size_p0 == hand_size_p0_before_power + 2
    ), "P0 gained 2 cards from power"
    assert (
        final_hand_size_p1 == hand_size_p1_before_power + 1
    ), "P1 gained 1 card from power"
    assert (
        final_hand_size_p2 == hand_size_p2_before_power + 1
    ), "P2 gained 1 card from power"

    # Verify all 4 drawn cards are distributed (bird_hand contains IDs)
    player_0_cards = set(state.players[0].bird_hand)
    player_1_cards = set(state.players[1].bird_hand)
    player_2_cards = set(state.players[2].bird_hand)

    assert selected_card_0_first_id in player_0_cards
    assert selected_card_0_second_id in player_0_cards
    assert selected_card_1_id in player_1_cards
    assert selected_card_2_id in player_2_cards

    # Verify deck size
    assert len(state.bird_deck) == initial_deck_size - 4


def test_power_6_with_2_players():
    """Test Power 6 with 2 players (minimum case)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place bird with power 6 on board
    power_6_bird_id = 8
    place_bird_on_board(state, 0, 2, 0, power_6_bird_id)

    initial_hand_sizes = [len(p.bird_hand) for p in state.players]
    initial_deck_size = len(state.bird_deck)

    # Setup power activation
    activating_spot = state.players[0].board[2][0]
    setup_power_execution(state, 6, power_6_bird_id, activating_spot, 0)

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Should draw 3 cards (2 players + 1)
    current_exec = state.action_data.execution_stack[-1]
    available_ids = current_exec.context.get("available_cards", [])
    assert len(available_ids) == 3

    # Player order should be [0, 1, 0]
    awaiting_players = current_exec.context.get("awaiting_players", [])
    assert awaiting_players == [0, 1, 0]

    # All players select cards (available_cards contains IDs now)
    for i in range(3):
        current_exec = state.action_data.execution_stack[-1]
        available = current_exec.context["available_cards"]
        selected_id = available[0]
        state = transition_state(state, IdAction("select_card", selected_id))

    # Verify final distribution
    assert len(state.players[0].bird_hand) == initial_hand_sizes[0] + 2
    assert len(state.players[1].bird_hand) == initial_hand_sizes[1] + 1
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.bird_deck) == initial_deck_size - 3


def test_power_6_with_5_players():
    """Test Power 6 with 5 players (maximum case)."""
    state = initiate_state(5)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 2  # Player 2 activates

    # Place bird with power 6
    power_6_bird_id = 8
    place_bird_on_board(state, 2, 2, 0, power_6_bird_id)

    initial_hand_sizes = [len(p.bird_hand) for p in state.players]
    initial_deck_size = len(state.bird_deck)

    # Setup power activation
    activating_spot = state.players[2].board[2][0]
    setup_power_execution(state, 6, power_6_bird_id, activating_spot, 2)

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Should draw 6 cards (5 players + 1)
    current_exec = state.action_data.execution_stack[-1]
    available_ids = current_exec.context.get("available_cards", [])
    assert len(available_ids) == 6

    # Player order should be [2, 3, 4, 0, 1, 2] (clockwise from activator)
    awaiting_players = current_exec.context.get("awaiting_players", [])
    assert awaiting_players == [2, 3, 4, 0, 1, 2]

    # Track selections
    selections_by_player = {i: [] for i in range(5)}

    # All players select cards (available_cards contains IDs now)
    for i in range(6):
        current_player = state.current_player_index
        current_exec = state.action_data.execution_stack[-1]
        available = current_exec.context["available_cards"]
        selected_id = available[0]
        selections_by_player[current_player].append(selected_id)
        state = transition_state(state, IdAction("select_card", selected_id))

    # Verify final distribution
    assert (
        len(state.players[2].bird_hand) == initial_hand_sizes[2] + 2
    ), "Player 2 (activator) should get 2 cards"
    for i in [0, 1, 3, 4]:
        assert (
            len(state.players[i].bird_hand) == initial_hand_sizes[i] + 1
        ), f"Player {i} should get 1 card"

    # Verify Player 2 selected twice
    assert len(selections_by_player[2]) == 2

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.bird_deck) == initial_deck_size - 6
    # Next player determined by get_current_player_index based on action cubes


if __name__ == "__main__":
    test_power_6_full_game_scenario_with_3_players()
    test_power_6_with_2_players()
    test_power_6_with_5_players()
    print("\nAll Power 6 tests passed! ✓")
