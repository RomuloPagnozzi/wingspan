"""Tests for Power ID 13: Give resources to players with fewest birds in habitat."""

import sys

sys.path.append(".")

from game.data import (
    initiate_state,
    get_bird,
    get_bird_power,
    GamePhase,
    ActionData,
    QueuedPower,
)
from game.actions import get_actions
from game.engine import transition_state


def setup_power_13_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 13 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 13}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=13,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def test_power_13_card_single_player():
    """Test Power 13 card variant with one player having fewest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Use Bird 3 (American Coot): Wetland habitat, Card reward
    bird_id = 3
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 0's board
    state.players[0].board[0][0].bird = power_bird
    if power_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_bird)

    # Give Player 1 some wetland birds (wetland = row 2)
    wetland_birds = [b for b in state.bird_deck if "wetland" in b.habitats][:2]
    state.players[1].board[2][0].bird = wetland_birds[0]
    state.players[1].board[2][1].bird = wetland_birds[1]

    # Player 0 has 0 wetland birds, Player 1 has 2
    # Player 0 should receive 1 card

    initial_hand_size = len(state.players[0].bird_hand)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should complete immediately for card variant)
    state = transition_state(state, "activate_power")

    # Verify Player 0 gained 1 card
    assert (
        len(state.players[0].bird_hand) == initial_hand_size + 1
    ), "Player 0 should have received 1 card"

    # Verify no sub_phase created (card variant completes immediately)
    assert (
        len(state.action_data.execution_stack) == 0
    ), "Card variant should not create sub_phase"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN, "Should return to MAIN_TURN"


def test_power_13_card_multiple_tied():
    """Test Power 13 card variant with multiple players tied for fewest."""
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Use Bird 60 (Common Merganser): Wetland habitat, Card reward
    bird_id = 60
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 0's board
    state.players[0].board[0][0].bird = power_bird
    if power_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_bird)

    # All players have 0 wetland birds (all tied for fewest)
    # All should receive 1 card

    initial_hand_sizes = [
        len(state.players[0].bird_hand),
        len(state.players[1].bird_hand),
        len(state.players[2].bird_hand),
    ]

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation
    state = transition_state(state, "activate_power")

    # Verify all players gained 1 card
    assert (
        len(state.players[0].bird_hand) == initial_hand_sizes[0] + 1
    ), "Player 0 should have received 1 card"
    assert (
        len(state.players[1].bird_hand) == initial_hand_sizes[1] + 1
    ), "Player 1 should have received 1 card"
    assert (
        len(state.players[2].bird_hand) == initial_hand_sizes[2] + 1
    ), "Player 2 should have received 1 card"

    # Verify no sub_phase created
    assert (
        len(state.action_data.execution_stack) == 0
    ), "Card variant should not create sub_phase"

    # Verify power completed
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_13_die_single_player():
    """Test Power 13 die variant with single player selecting die."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Use Bird 88 (Hooded Merganser): Forest habitat, Die reward
    bird_id = 88
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 0's board
    state.players[0].board[0][0].bird = power_bird
    if power_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_bird)

    # Give Player 1 some forest birds (forest = row 0)
    forest_birds = [b for b in state.bird_deck if "forest" in b.habitats][:3]
    state.players[1].board[0][0].bird = forest_birds[0]
    state.players[1].board[0][1].bird = forest_birds[1]
    state.players[1].board[0][2].bird = forest_birds[2]

    # Player 0 has 1 forest bird (the activating bird), Player 1 has 3
    # Actually, let's place the activating bird in grassland to make P0 have 0 forest
    state.players[0].board[0][0].bird = None
    state.players[0].board[1][0].bird = power_bird  # Place in grassland

    # Set up known feeder
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    initial_food = dict(state.players[0].food)

    activating_spot = state.players[0].board[1][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation (should enter sub_phase for die selection)
    state = transition_state(state, "activate_power")

    # Verify sub_phase created
    assert (
        state.action_data.execution_stack[-1].phase == "select_die"
    ), "Should create power_13_select_die sub_phase"
    assert state.action_data.execution_stack[-1].context.get("awaiting_players") == [
        0
    ], "Player 0 should be awaiting"

    # Verify die selection actions available
    actions = get_actions(state)
    assert "select_die_0_fish" in actions, "Should have die 0 (fish) option"
    assert "select_die_1_seed" in actions, "Should have die 1 (seed) option"

    # Select die 1 (seed)
    state = transition_state(state, "select_die_1_seed")

    # Verify Player 0 gained seed
    assert (
        state.players[0].food.get("seed", 0) == initial_food.get("seed", 0) + 1
    ), "Player 0 should have gained 1 seed"

    # Verify die removed from feeder
    assert 1 not in state.feeder, "Die 1 should be removed from feeder"

    # Verify power completed
    assert state.game_phase == GamePhase.MAIN_TURN, "Should return to MAIN_TURN"
    assert len(state.action_data.execution_stack) == 0, "sub_phase should be cleaned up"


def test_power_13_die_multiple_players():
    """Test Power 13 die variant with multiple players selecting dice."""
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 1

    # Use Bird 88 (Hooded Merganser): Forest habitat, Die reward
    bird_id = 88
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 1's board (in grassland to not count as forest)
    state.players[1].board[1][0].bird = power_bird
    if power_bird in state.players[1].bird_hand:
        state.players[1].bird_hand.remove(power_bird)

    # All players have 0 forest birds (all tied for fewest)
    # Set up known feeder
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    initial_food = [
        dict(state.players[0].food),
        dict(state.players[1].food),
        dict(state.players[2].food),
    ]

    activating_spot = state.players[1].board[1][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation
    state = transition_state(state, "activate_power")

    # Verify awaiting_players includes all 3 players
    assert sorted(
        state.action_data.execution_stack[-1].context.get("awaiting_players", [])
    ) == [
        0,
        1,
        2,
    ], "All players should be awaiting"

    # Player 0 selects die 0 (fish)
    assert state.current_player_index == 0, "Should start with Player 0"
    state = transition_state(state, "select_die_0_fish")
    assert (
        state.players[0].food.get("fish", 0) == initial_food[0].get("fish", 0) + 1
    ), "Player 0 should have gained fish"
    assert 0 not in state.feeder, "Die 0 should be removed"

    # Player 1 selects die 1 (seed)
    assert state.current_player_index == 1, "Should be Player 1's turn"
    state = transition_state(state, "select_die_1_seed")
    assert (
        state.players[1].food.get("seed", 0) == initial_food[1].get("seed", 0) + 1
    ), "Player 1 should have gained seed"
    assert 1 not in state.feeder, "Die 1 should be removed"

    # Player 2 selects die 2 (invertebrate)
    assert state.current_player_index == 2, "Should be Player 2's turn"
    state = transition_state(state, "select_die_2_invertebrate")
    assert (
        state.players[2].food.get("invertebrate", 0)
        == initial_food[2].get("invertebrate", 0) + 1
    ), "Player 2 should have gained invertebrate"
    assert 2 not in state.feeder, "Die 2 should be removed"

    # Verify power completed and cleanup done
    assert state.game_phase == GamePhase.MAIN_TURN, "Should return to MAIN_TURN"
    assert (
        len(state.action_data.execution_stack) == 0
    ), "Execution stack should be cleaned up"


def test_power_13_reroll_all_dice():
    """Test Power 13 allows reroll when all dice show same face."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Use Bird 88 (Hooded Merganser): Forest habitat, Die reward
    bird_id = 88
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 0's board (in grassland)
    state.players[0].board[1][0].bird = power_bird
    if power_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_bird)

    # Give Player 1 some forest birds
    forest_birds = [b for b in state.bird_deck if "forest" in b.habitats][:2]
    state.players[1].board[0][0].bird = forest_birds[0]
    state.players[1].board[0][1].bird = forest_birds[1]

    # Set up feeder with all same face
    state.feeder = {0: ["fish"], 1: ["fish"], 2: ["fish"], 3: ["fish"], 4: ["fish"]}

    activating_spot = state.players[0].board[1][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation
    state = transition_state(state, "activate_power")

    # Verify reroll option available
    actions = get_actions(state)
    assert "reroll_all" in actions, "Should have reroll_all option when all dice match"
    assert "select_die_0_fish" in actions, "Should still have fish selection option"

    # Choose to reroll
    state = transition_state(state, "reroll_all")

    # Verify feeder rerolled
    assert len(state.feeder) == 5, "Feeder should still have 5 dice"
    assert (
        state.action_data.execution_stack[-1].phase == "select_die"
    ), "Should still be in die selection sub_phase"
    assert state.current_player_index == 0, "Same player should continue"

    # Get new actions (should have different die options now, likely)
    actions = get_actions(state)
    # Can't assert specific dice since random, but should have selection actions
    select_actions = [a for a in actions if a.startswith("select_die_")]
    assert len(select_actions) > 0, "Should have die selection actions after reroll"

    # Select a die to complete the power
    state = transition_state(state, select_actions[0])

    # Verify power completed
    assert state.game_phase == GamePhase.MAIN_TURN, "Should complete after selection"


def test_power_13_feeder_empties_during_power():
    """Test Power 13 handles feeder emptying during multi-player selection."""
    state = initiate_state(5)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Use Bird 88 (Hooded Merganser): Forest habitat, Die reward
    bird_id = 88
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Place activating bird on Player 0's board (in grassland)
    state.players[0].board[1][0].bird = power_bird
    if power_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_bird)

    # All players have 0 forest birds
    # Set up feeder with 5 different dice
    state.feeder = {
        0: ["fish"],
        1: ["seed"],
        2: ["invertebrate"],
        3: ["fruit"],
        4: ["rodent"],
    }

    activating_spot = state.players[0].board[1][0]

    # Setup power activation
    setup_power_13_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Execute activation
    state = transition_state(state, "activate_power")

    # Players select dice sequentially
    state = transition_state(state, "select_die_0_fish")  # Player 0
    assert len(state.feeder) == 4, "Should have 4 dice after first selection"

    state = transition_state(state, "select_die_1_seed")  # Player 1
    assert len(state.feeder) == 3, "Should have 3 dice after second selection"

    state = transition_state(state, "select_die_2_invertebrate")  # Player 2
    assert len(state.feeder) == 2, "Should have 2 dice after third selection"

    state = transition_state(state, "select_die_3_fruit")  # Player 3
    assert len(state.feeder) == 1, "Should have 1 die after fourth selection"

    state = transition_state(state, "select_die_4_rodent")  # Player 4 (last)

    # After last die selected, feeder should auto-refill
    assert len(state.feeder) == 5, "Feeder should auto-refill after emptying"

    # Verify power completed
    assert state.game_phase == GamePhase.MAIN_TURN, "Should return to MAIN_TURN"


def test_power_13_validation():
    """Test Power 13 validation always returns True (no preconditions)."""
    from game.powers_validators import can_execute_power

    state = initiate_state(2)
    state.current_player_index = 0

    # Use Bird 88 (Hooded Merganser): Forest habitat, Die reward
    bird_id = 88
    power_data = get_bird_power(bird_id)
    power_bird = get_bird(bird_id)
    assert power_bird

    # Test with empty board
    state.players[0].board[1][0].bird = power_bird
    spot = state.players[0].board[1][0]

    power_entry = {"power_data": power_data, "spot": spot}

    assert can_execute_power(
        state, power_entry
    ), "Power 13 should always validate (empty board)"

    # Test with partial board
    forest_birds = [b for b in state.bird_deck if "forest" in b.habitats][:3]
    state.players[0].board[0][0].bird = forest_birds[0]
    state.players[0].board[0][1].bird = forest_birds[1]
    assert can_execute_power(
        state, power_entry
    ), "Power 13 should always validate (partial board)"

    # Test with different player having more birds
    state.players[1].board[0][0].bird = forest_birds[2]
    assert can_execute_power(
        state, power_entry
    ), "Power 13 should always validate (different distribution)"

    # Power 13 has no preconditions, validator is lambda True
