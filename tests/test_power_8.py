"""Comprehensive end-to-end tests for Power 8: Gain food with optional caching."""

import sys

sys.path.append(".")

from game.data import (
    initiate_state,
    GamePhase,
    load_deck,
    get_bird_power,
    ActionData,
    QueuedPower,
)
from game.engine import transition_state
from game.actions import get_actions


def setup_power_8_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 8 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 8}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=8,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def find_bird_with_power_8(source, food_types, quantity, can_cache):
    """Find a bird ID with specific Power 8 configuration."""
    birds = load_deck("birds")
    for bird in birds:
        power_data = get_bird_power(bird.id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 8:
            details = power_data["data"].get("details", {})
            if (
                details.get("source") == source
                and details.get("food_types") == food_types
                and details.get("quantity") == quantity
                and details.get("can_cache") == can_cache
            ):
                return bird.id, power_data
    return None, None


def test_power_8_supply_single_food_no_cache():
    """Test simplest case - immediate gain from supply, no sub-phases."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with this Power 8 config
    bird_id, power_data = find_bird_with_power_8(
        source="supply", food_types=["fruit"], quantity=1, can_cache=False
    )
    assert bird_id is not None, "Should find bird with supply/fruit/qty=1/no cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should complete immediately
    state = transition_state(state, "activate_power")

    # Verify food gained
    expected_fruit = initial_food.get("fruit", 0) + 1
    assert state.players[0].food.get("fruit", 0) == expected_fruit

    # Verify no sub-phases
    assert len(state.action_data.execution_stack) == 0

    # Verify cleanup and completion
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_8_supply_multiple_quantity():
    """Test gaining 3 food from supply immediately."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with qty=3 config
    bird_id, power_data = find_bird_with_power_8(
        source="supply", food_types=["seed"], quantity=3, can_cache=False
    )
    assert bird_id is not None, "Should find bird with supply/seed/qty=3/no cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should gain 3 food immediately
    state = transition_state(state, "activate_power")

    # Verify 3 food gained
    expected_seed = initial_food.get("seed", 0) + 3
    assert state.players[0].food.get("seed", 0) == expected_seed

    # Verify no sub-phases
    assert len(state.action_data.execution_stack) == 0

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_8_birdfeeder_all_dice():
    """Test taking all matching dice from feeder without choices."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup feeder with 3 fish dice and 2 other food dice
    state.feeder = {
        0: ["fish"],
        1: ["fish"],
        2: ["fish"],
        3: ["seed"],
        4: ["invertebrate"],
    }

    # Find bird with quantity="all" config
    bird_id, power_data = find_bird_with_power_8(
        source="birdfeeder", food_types=["fish"], quantity="all", can_cache=False
    )
    assert bird_id is not None, "Should find bird with birdfeeder/fish/qty=all/no cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)
    initial_feeder_size = len(state.feeder)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should take all 3 fish dice immediately
    state = transition_state(state, "activate_power")

    # Verify 3 fish gained
    expected_fish = initial_food.get("fish", 0) + 3
    assert state.players[0].food.get("fish", 0) == expected_fish

    # Verify feeder reduced from 5 to 2 dice
    assert len(state.feeder) == 2

    # Verify no sub-phases
    assert len(state.action_data.execution_stack) == 0

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


def test_power_8_birdfeeder_die_selection_then_cache():
    """Test complete 2-stage flow: die selection → cache choice."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup feeder with 2 seed dice
    state.feeder = {
        0: ["seed"],
        1: ["seed"],
        2: ["fish"],
    }

    # Find bird with can_cache=True config
    bird_id, power_data = find_bird_with_power_8(
        source="birdfeeder", food_types=["seed"], quantity=1, can_cache=True
    )
    assert bird_id is not None, "Should find bird with birdfeeder/seed/qty=1/cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)
    initial_stashed = power_8_bird.stashed_food

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should transition to die selection
    state = transition_state(state, "activate_power")

    # Verify sub-phase: die selection
    assert state.action_data.execution_stack[-1].phase == "select_die"

    # Verify 2 die selection actions available
    actions = get_actions(state)
    die_actions = [a for a in actions if a.startswith("select_die_")]
    assert len(die_actions) == 2
    assert "select_die_0_seed" in actions
    assert "select_die_1_seed" in actions

    # Select die 0
    state = transition_state(state, "select_die_0_seed")

    # Verify food gained in supply
    expected_seed = initial_food.get("seed", 0) + 1
    assert state.players[0].food.get("seed", 0) == expected_seed

    # Verify die removed from feeder
    assert 0 not in state.feeder
    assert len(state.feeder) == 2

    # Verify transitions to cache choice sub-phase
    assert state.action_data.execution_stack[-1].phase == "choose_cache"

    # Verify cache actions available
    actions = get_actions(state)
    assert "cache_food" in actions
    assert "supply_food" in actions

    # Choose to cache the food
    state = transition_state(state, "cache_food")

    # Verify food moved from supply to bird.stashed_food
    assert state.players[0].food.get("seed", 0) == initial_food.get("seed", 0)
    assert power_8_bird.stashed_food == initial_stashed + 1

    # Verify cleanup and completion
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0
    assert len(state.action_data.execution_stack) == 0


def test_power_8_food_type_then_die_selection():
    """Test 2-stage selection: choose food type first, then choose die."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup feeder with 2 invertebrate dice and 2 fruit dice
    state.feeder = {
        0: ["invertebrate"],
        1: ["invertebrate"],
        2: ["fruit"],
        3: ["fruit"],
    }

    # Find bird with multi-food config
    bird_id, power_data = find_bird_with_power_8(
        source="birdfeeder",
        food_types=["invertebrate", "fruit"],
        quantity=1,
        can_cache=False,
    )
    assert (
        bird_id is not None
    ), "Should find bird with birdfeeder/[invertebrate,fruit]/qty=1/no cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should transition to food type selection
    state = transition_state(state, "activate_power")

    # Verify sub-phase: food type selection
    assert state.action_data.execution_stack[-1].phase == "select_food_type"

    # Verify food type actions available
    actions = get_actions(state)
    assert "select_food_type_fruit" in actions
    assert "select_food_type_invertebrate" in actions

    # Choose fruit
    state = transition_state(state, "select_food_type_fruit")

    # Verify transitions to die selection
    assert state.action_data.execution_stack[-1].phase == "select_die"

    # Verify food type stored
    assert state.action_data.execution_stack[-1].context.get("food_type") == "fruit"

    # Verify only fruit dice options available
    actions = get_actions(state)
    die_actions = [a for a in actions if a.startswith("select_die_")]
    assert len(die_actions) == 2
    assert "select_die_2_fruit" in actions
    assert "select_die_3_fruit" in actions

    # Select fruit die
    state = transition_state(state, "select_die_2_fruit")

    # Verify fruit food gained
    expected_fruit = initial_food.get("fruit", 0) + 1
    assert state.players[0].food.get("fruit", 0) == expected_fruit

    # Verify die removed
    assert 2 not in state.feeder

    # Verify cleanup and completion
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0
    assert len(state.action_data.execution_stack) == 0


def test_power_8_wild_dice_display_format():
    """Test that wild dice (multi-food dice) show complete state in action string."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup feeder with wild die and single-food dice
    state.feeder = {
        0: ["invertebrate"],
        1: ["invertebrate", "seed"],  # Wild die
        2: ["fruit"],
    }

    # Find bird that accepts invertebrate
    bird_id, power_data = find_bird_with_power_8(
        source="birdfeeder", food_types=["invertebrate"], quantity=1, can_cache=False
    )
    assert (
        bird_id is not None
    ), "Should find bird with birdfeeder/invertebrate/qty=1/no cache"

    # Get bird and place on board
    from game.data import get_bird

    power_8_bird = get_bird(bird_id)
    state.players[0].board[0][0].bird = power_8_bird
    if power_8_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_8_bird)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_8_execution(
        state, state.current_player_index, bird_id, activating_spot, power_data
    )

    # Record initial state
    initial_food = dict(state.players[0].food)

    # Verify can activate
    actions = get_actions(state)
    assert "activate_power" in actions

    # Execute activation - should transition to die selection
    state = transition_state(state, "activate_power")

    # Verify sub-phase: die selection
    assert state.action_data.execution_stack[-1].phase == "select_die"

    # Verify action format - only dice with selected food type appear
    actions = get_actions(state)
    assert "select_die_0_invertebrate" in actions  # Single food die with invertebrate
    assert "select_die_1_invertebrate" in actions  # Wild die has invertebrate
    assert (
        "select_die_1_seed" not in actions
    )  # Seed option filtered out (player chose invertebrate)
    assert "select_die_2_fruit" not in actions  # Fruit die filtered out

    # Select wild die - choose invertebrate from the wild die
    state = transition_state(state, "select_die_1_invertebrate")

    # Verify only "invertebrate" food gained (not both foods from die)
    expected_invertebrate = initial_food.get("invertebrate", 0) + 1
    assert state.players[0].food.get("invertebrate", 0) == expected_invertebrate
    assert state.players[0].food.get("seed", 0) == initial_food.get("seed", 0)

    # Verify die removed
    assert 1 not in state.feeder

    # Verify cleanup
    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0
    assert len(state.action_data.execution_stack) == 0
