"""Comprehensive end-to-end test for Power 7: Each player gains 1 die from birdfeeder, starting with player of your choice."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase, get_bird
from game.engine import transition_state
from game.actions import get_actions


def test_power_7_full_game_scenario_with_3_players():
    """
    End-to-end test: Power 7 in a realistic 3-player game scenario.

    Game scenario:
    - 3 players
    - Player 0 plays bird with Power 7 (Bird ID 13)
    - Power 7: "Each player gains 1 [die] from the birdfeeder, starting with
      the player of your choice."
    - Player 0 chooses Player 1 to start
    - Selection order: Player 1 -> Player 2 -> Player 0
    - Final result: Each player gets 1 food from birdfeeder
    """
    # Setup: Create 3-player game
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Get bird with Power 7
    power_7_bird = get_bird(13)
    assert power_7_bird is not None, "Bird ID 13 should exist"

    # Place bird on board for player 0
    state.players[0].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_7_bird)

    # Setup initial feeder state with known dice
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    # Record initial food for all players
    initial_food_p0 = dict(state.players[0].food)
    initial_food_p1 = dict(state.players[1].food)
    initial_food_p2 = dict(state.players[2].food)

    # Setup power activation
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Get available actions - should be able to activate or skip
    actions = get_actions(state)
    assert "activate_power" in actions
    assert "skip_power" in actions

    # Activate Power 7
    state = transition_state(state, "activate_power")

    # Should be in power_7_choose_starting_player sub-phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.get("sub_phase") == "power_7_choose_starting_player"
    assert state.action_data.get("activator") == 0

    # Get available player selection actions
    actions = get_actions(state)
    assert len(actions) == 3, "Should have 3 players to choose from"
    assert "choose_player_0" in actions
    assert "choose_player_1" in actions
    assert "choose_player_2" in actions

    # Player 0 chooses Player 1 to start
    state = transition_state(state, "choose_player_1")

    # Should transition to die selection sub-phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.get("sub_phase") == "power_7_select_die"

    # Verify player order: [1, 2, 0] (clockwise from Player 1)
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [1, 2, 0], "Should be clockwise from Player 1"

    # Current player should be Player 1
    assert state.current_player_index == 1

    # Get available die selection actions
    actions = get_actions(state)
    assert len(actions) == 5, "Should have 5 dice to choose from"
    assert "select_die_0_fish" in actions
    assert "select_die_1_seed" in actions
    assert "select_die_2_invertebrate" in actions
    assert "select_die_3_fruit" in actions
    assert "select_die_4_rodent" in actions

    # Player 1 selects die 0 (fish)
    state = transition_state(state, "select_die_0_fish")

    # Verify Player 1 received the fish
    assert state.players[1].food.get("fish", 0) == initial_food_p1.get("fish", 0) + 1

    # Verify die 0 was removed from feeder
    assert 0 not in state.feeder
    assert len(state.feeder) == 4

    # Should advance to Player 2
    assert state.current_player_index == 2
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.get("sub_phase") == "power_7_select_die"

    # Verify awaiting_players updated
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [2, 0], "Player 1 removed from queue"

    # Player 2 selects die 1 (seed)
    actions = get_actions(state)
    assert len(actions) == 4, "Should have 4 dice remaining"
    assert "select_die_0_fish" not in actions, "Die 0 already taken"

    state = transition_state(state, "select_die_1_seed")

    # Verify Player 2 received the seed
    assert state.players[2].food.get("seed", 0) == initial_food_p2.get("seed", 0) + 1

    # Verify die 1 was removed
    assert 1 not in state.feeder
    assert len(state.feeder) == 3

    # Should advance to Player 0
    assert state.current_player_index == 0
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [0], "Only Player 0 remains"

    # Player 0 selects die 2 (invertebrate)
    actions = get_actions(state)
    assert len(actions) == 3, "Should have 3 dice remaining"

    state = transition_state(state, "select_die_2_invertebrate")

    # Verify Player 0 received the invertebrate
    assert (
        state.players[0].food.get("invertebrate", 0)
        == initial_food_p0.get("invertebrate", 0) + 1
    )

    # Verify die 2 was removed
    assert 2 not in state.feeder
    assert len(state.feeder) == 2

    # Should transition back to MAIN_TURN
    assert state.game_phase == GamePhase.MAIN_TURN

    # Verify no sub-phase data remains
    assert "sub_phase" not in state.action_data
    assert "awaiting_players" not in state.action_data
    assert "activator" not in state.action_data

    # Verify final food totals
    assert (
        state.players[0].food.get("invertebrate", 0)
        == initial_food_p0.get("invertebrate", 0) + 1
    ), "P0 gained invertebrate"
    assert (
        state.players[1].food.get("fish", 0) == initial_food_p1.get("fish", 0) + 1
    ), "P1 gained fish"
    assert (
        state.players[2].food.get("seed", 0) == initial_food_p2.get("seed", 0) + 1
    ), "P2 gained seed"

    print("✓ Power 7 end-to-end test passed (3 players)!")
    print(f"  - Player 0 chose Player 1 to start")
    print(f"  - Selection order was correct: 1 -> 2 -> 0")
    print(f"  - Each player gained exactly 1 food from birdfeeder")
    print(f"  - Game transitioned back to MAIN_TURN correctly")


def test_power_7_activator_chooses_self():
    """Test Power 7 when activator chooses themselves to start."""
    state = initiate_state(4)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 2

    # Get bird with Power 7
    power_7_bird = get_bird(136)  # Using bird ID 136
    assert power_7_bird is not None, "Bird ID 136 should exist"

    # Place bird on board for player 2
    state.players[2].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[2].bird_hand:
        state.players[2].bird_hand.remove(power_7_bird)

    # Setup feeder
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
    }

    # Record initial food
    initial_food = [dict(p.food) for p in state.players]

    # Setup power activation
    activating_spot = state.players[2].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Should be in player selection phase
    assert state.action_data.get("sub_phase") == "power_7_choose_starting_player"

    # Player 2 chooses themselves (Player 2)
    state = transition_state(state, "choose_player_2")

    # Verify player order: [2, 3, 0, 1] (clockwise from Player 2)
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [2, 3, 0, 1], "Should be clockwise from Player 2"

    # Current player should be Player 2 (activator)
    assert state.current_player_index == 2

    # All players select dice
    for expected_player in [2, 3, 0, 1]:
        assert state.current_player_index == expected_player
        available_actions = get_actions(state)
        # Select first available die
        selected_action = available_actions[0]
        state = transition_state(state, selected_action)

    # Should be back to MAIN_TURN
    assert state.game_phase == GamePhase.MAIN_TURN

    # Verify all players gained food
    for i in range(4):
        current_food_total = sum(state.players[i].food.values())
        initial_food_total = sum(initial_food[i].values())
        assert (
            current_food_total == initial_food_total + 1
        ), f"Player {i} should have gained exactly 1 food"


def test_power_7_feeder_empties_mid_power():
    """Test Power 7 when feeder empties and needs to reroll mid-power."""
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Get bird with Power 7
    power_7_bird = get_bird(13)
    assert power_7_bird
    state.players[0].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_7_bird)

    # Setup feeder with only 2 dice (will empty after 2 selections)
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
    }

    # Setup power activation
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate and choose starting player
    state = transition_state(state, "activate_power")
    state = transition_state(state, "choose_player_0")

    # Player 0 selects die 0
    state = transition_state(state, "select_die_0_fish")
    assert len(state.feeder) == 1

    # Player 1 selects die 1 (empties feeder)
    state = transition_state(state, "select_die_1_seed")

    # Feeder should have been auto-rerolled to 5 dice
    assert len(state.feeder) == 5, "Feeder should reroll when emptied"

    # Player 2 should have dice to choose from
    actions = get_actions(state)
    assert (
        len(actions) >= 5
    ), "Player 2 should have fresh dice (at least 5 actions, possibly more for wild dice)"

    # Player 2 selects from the new dice
    state = transition_state(state, actions[0])

    # Should complete successfully
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_7_with_2_players():
    """Test Power 7 with 2 players (minimum case)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Get bird with Power 7
    power_7_bird = get_bird(13)
    assert power_7_bird
    state.players[0].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_7_bird)

    # Setup feeder
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    initial_food = [dict(p.food) for p in state.players]

    # Setup power activation
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Choose Player 1 to start
    state = transition_state(state, "choose_player_1")

    # Verify player order: [1, 0]
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [1, 0]

    # Both players select dice
    for expected_player in [1, 0]:
        assert state.current_player_index == expected_player
        actions = get_actions(state)
        state = transition_state(state, actions[0])

    # Verify completion
    assert state.game_phase == GamePhase.MAIN_TURN

    # Verify both players gained food
    for i in range(2):
        current_total = sum(state.players[i].food.values())
        initial_total = sum(initial_food[i].values())
        assert current_total == initial_total + 1


def test_power_7_with_5_players():
    """Test Power 7 with 5 players (maximum case)."""
    state = initiate_state(5)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 3

    # Get bird with Power 7
    power_7_bird = get_bird(136)
    assert power_7_bird
    state.players[3].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[3].bird_hand:
        state.players[3].bird_hand.remove(power_7_bird)

    # Setup feeder
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    initial_food = [dict(p.food) for p in state.players]

    # Setup power activation
    activating_spot = state.players[3].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Player 3 chooses Player 0 to start
    state = transition_state(state, "choose_player_0")

    # Verify player order: [0, 1, 2, 3, 4] (clockwise from Player 0)
    awaiting_players = state.action_data.get("awaiting_players", [])
    assert awaiting_players == [0, 1, 2, 3, 4]

    # Track feeder state - will need to reroll once
    selections_made = 0

    # All 5 players select dice
    for expected_player in [0, 1, 2, 3, 4]:
        assert state.current_player_index == expected_player
        actions = get_actions(state)
        assert len(actions) > 0, f"Player {expected_player} should have dice to choose"
        state = transition_state(state, actions[0])
        selections_made += 1

    # Should be back to MAIN_TURN
    assert state.game_phase == GamePhase.MAIN_TURN

    # Verify all 5 players gained exactly 1 food
    for i in range(5):
        current_total = sum(state.players[i].food.values())
        initial_total = sum(initial_food[i].values())
        assert (
            current_total == initial_total + 1
        ), f"Player {i} should have gained exactly 1 food"


def test_power_7_all_dice_same_face():
    """Test Power 7 when all dice show the same face (no reroll option)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Get bird with Power 7
    power_7_bird = get_bird(13)
    assert power_7_bird
    state.players[0].board[0][0].bird = power_7_bird
    if power_7_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_7_bird)

    # Setup feeder with all dice showing the same face
    state.feeder = {
        0: ["fish"],
        1: ["fish"],
        2: ["fish"],
        3: ["fish"],
        4: ["fish"],
    }

    # Setup power activation
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": power_7_bird.id,
                "power_id": 7,
                "power_data": {"data": {"id": 7}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate and choose starting player
    state = transition_state(state, "activate_power")
    state = transition_state(state, "choose_player_0")

    # Get available actions for Player 0
    actions = get_actions(state)

    # Should NOT have "reroll_all" option (unlike COLLECT_FOOD phase)
    assert (
        "reroll_all" not in actions
    ), "Power 7 should not allow reroll, even when all dice match"

    # Should have 5 fish selections
    fish_actions = [a for a in actions if "fish" in a]
    assert len(fish_actions) == 5, "Should have 5 fish dice to choose from"

    # Players must select from available dice
    state = transition_state(state, "select_die_0_fish")
    state = transition_state(state, "select_die_1_fish")

    # Should complete successfully
    assert state.game_phase == GamePhase.MAIN_TURN

    # Both players should have gained fish
    assert state.players[0].food.get("fish", 0) >= 1
    assert state.players[1].food.get("fish", 0) >= 1


if __name__ == "__main__":
    test_power_7_full_game_scenario_with_3_players()
    test_power_7_activator_chooses_self()
    test_power_7_feeder_empties_mid_power()
    test_power_7_with_2_players()
    test_power_7_with_5_players()
    test_power_7_all_dice_same_face()
    print("\nAll Power 7 tests passed! ✓")
