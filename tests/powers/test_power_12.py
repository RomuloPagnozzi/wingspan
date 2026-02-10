"""Comprehensive end-to-end tests for Power 12: Play additional bird in habitat."""

from game.core import (
    initiate_state,
    GamePhase,
    get_bird_power,
    BIRD_REGISTRY,
    init_registries,
    SimpleAction,
    PlayBirdAction,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import place_bird_on_board, setup_power_execution


def find_birds_with_power_12():
    """Find all birds with Power 12 grouped by habitat variant."""
    init_registries()
    variants = {
        "forest": [],
        "grassland": [],
        "wetland": [],
        "this": [],
    }

    for bird_id in BIRD_REGISTRY:
        power_data = get_bird_power(bird_id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 12:
            details = power_data["data"].get("details", {})
            habitat = details.get("habitat", "")

            if habitat in variants:
                variants[habitat].append((bird_id, power_data))

    return variants


def find_bird_id_by_habitats(
    habitats_include: list[str] | None = None,
    habitats_exclude: list[str] | None = None,
    habitats_exact: list[str] | None = None,
) -> int:
    """Find a bird ID matching habitat criteria."""
    init_registries()
    for bird_id, card in BIRD_REGISTRY.items():
        if habitats_exact is not None and set(card.habitats) != set(habitats_exact):
            continue
        if habitats_include is not None:
            if not all(h in card.habitats for h in habitats_include):
                continue
        if habitats_exclude is not None:
            if any(h in card.habitats for h in habitats_exclude):
                continue
        return bird_id
    raise ValueError(
        f"No bird found with habitats_include={habitats_include}, habitats_exclude={habitats_exclude}, habitats_exact={habitats_exact}"
    )


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

    # Place power 12 bird on board with eggs
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=5)
    activating_spot = state.players[0].board[0][0]

    # Find a bird that can be played in forest and add to hand
    forest_bird_id = find_bird_id_by_habitats(habitats_include=["forest"])
    state.players[0].bird_hand.append(forest_bird_id)

    # Setup power activation
    setup_power_execution(
        state, 12, bird_id, activating_spot, state.current_player_index, power_data
    )

    initial_cubes = state.players[0].action_cubes

    # Verify can activate
    actions = get_actions(state)
    assert SimpleAction("activate_power") in actions, "Should be able to activate power"

    # Execute activation - should transition to PLAY_BIRD phase
    state = transition_state(state, SimpleAction("activate_power"))
    assert (
        state.game_phase == GamePhase.PLAY_BIRD
    ), "Should transition to PLAY_BIRD phase"

    # Verify only forest birds at forest spots appear in actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if isinstance(a, PlayBirdAction)]
    assert len(play_bird_actions) > 0, "Should have at least one play_bird action"

    # All actions should be for forest row (row 0)
    for action in play_bird_actions:
        assert (
            action.row == 0
        ), f"Action {action} should be for forest row (0), got row {action.row}"

    # Select first valid action and execute
    selected_action = play_bird_actions[0]
    state = transition_state(state, selected_action)

    # Get bird_id and position from the action
    placed_bird_id = selected_action.bird_id
    row = selected_action.row
    col = selected_action.col

    # Handle egg cost payment if needed
    if state.game_phase == GamePhase.PAY_EGG_COST:
        egg_actions = get_actions(state)
        state = transition_state(state, egg_actions[0])

    # Handle food cost payment if needed
    if state.game_phase == GamePhase.PAY_FOOD_COST:
        food_actions = get_actions(state)
        state = transition_state(state, food_actions[0])

    # Verify bird is on board at correct position
    placed_bird = state.players[0].board[row][col].bird
    assert placed_bird is not None, "Bird should be placed on board"
    assert placed_bird.id == placed_bird_id, "Correct bird should be placed"
    assert row == 0, "Bird should be in forest row"

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

    # Place power 12 bird on board with eggs
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=5)
    activating_spot = state.players[0].board[0][0]

    # Find birds with different habitat combinations
    init_registries()
    bird_a_id = None  # Forest only
    bird_b_id = None  # Grassland only
    bird_c_id = None  # Forest+wetland
    bird_d_id = None  # Grassland+wetland

    for bid, card in BIRD_REGISTRY.items():
        if bird_a_id is None and list(card.habitats) == ["forest"]:
            bird_a_id = bid
        elif bird_b_id is None and list(card.habitats) == ["grassland"]:
            bird_b_id = bid
        elif bird_c_id is None and set(card.habitats) == {"forest", "wetland"}:
            bird_c_id = bid
        elif bird_d_id is None and set(card.habitats) == {"grassland", "wetland"}:
            bird_d_id = bid

    # Clear hand and add test birds (as IDs)
    state.players[0].bird_hand = []

    if bird_a_id:
        state.players[0].bird_hand.append(bird_a_id)
    if bird_b_id:
        state.players[0].bird_hand.append(bird_b_id)
    if bird_c_id:
        state.players[0].bird_hand.append(bird_c_id)
    if bird_d_id:
        state.players[0].bird_hand.append(bird_d_id)

    # Setup power activation
    setup_power_execution(
        state, 12, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))
    assert state.game_phase == GamePhase.PLAY_BIRD

    # Get play_bird actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if isinstance(a, PlayBirdAction)]

    # Parse bird IDs from actions
    bird_ids_in_actions = set()
    for action in play_bird_actions:
        bird_ids_in_actions.add(action.bird_id)
        # Verify all actions are for forest row (row 0)
        assert (
            action.row == 0
        ), f"All actions should be for forest row, got {action.row}"

    # Verify only forest-compatible birds appear
    if bird_a_id:
        assert bird_a_id in bird_ids_in_actions, "Forest-only bird should appear"
    if bird_b_id:
        assert (
            bird_b_id not in bird_ids_in_actions
        ), "Grassland-only bird should NOT appear"
    if bird_c_id:
        assert bird_c_id in bird_ids_in_actions, "Forest+wetland bird should appear"
    if bird_d_id:
        assert (
            bird_d_id not in bird_ids_in_actions
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

    # Place power 12 bird in grassland row (row 1) with eggs
    place_bird_on_board(state, 0, 1, 0, bird_id, eggs=5)
    activating_spot = state.players[0].board[1][0]

    # Find a bird that can be played in grassland
    grassland_bird_id = find_bird_id_by_habitats(habitats_include=["grassland"])
    state.players[0].bird_hand.append(grassland_bird_id)

    # Setup power activation
    setup_power_execution(
        state, 12, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))
    assert state.game_phase == GamePhase.PLAY_BIRD

    # Get play_bird actions
    actions = get_actions(state)
    play_bird_actions = [a for a in actions if isinstance(a, PlayBirdAction)]
    assert len(play_bird_actions) > 0, "Should have grassland play actions"

    # Verify all actions are for grassland row (row 1)
    for action in play_bird_actions:
        assert (
            action.row == 1
        ), f"'this' should resolve to grassland (row 1), got row {action.row}"


def test_power_12_no_valid_birds():
    """Test Power 12 cannot activate when no valid birds available."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_12()
    assert len(variants["forest"]) > 0, "Should find bird with power 12 (forest)"

    bird_id, power_data = variants["forest"][0]

    # Place power 12 bird on board with eggs
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=5)
    activating_spot = state.players[0].board[0][0]

    # Add only non-forest birds to hand (grassland only, not forest)
    init_registries()
    grassland_bird_ids = []
    for bid, card in BIRD_REGISTRY.items():
        if "grassland" in card.habitats and "forest" not in card.habitats:
            grassland_bird_ids.append(bid)
            if len(grassland_bird_ids) >= 2:
                break

    state.players[0].bird_hand = grassland_bird_ids

    # Setup power activation
    setup_power_execution(
        state, 12, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate
    actions = get_actions(state)
    assert (
        SimpleAction("activate_power") not in actions
    ), "Should not be able to activate power"
    assert SimpleAction("skip_power") in actions, "Should be able to skip power"


def test_power_12_validation():
    """Test can_execute_power validator for Power 12."""
    from game.power import can_execute_power

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

        # Place bird on board with eggs
        place_bird_on_board(state, 0, 0, 0, bird_id, eggs=5)
        activating_spot = state.players[0].board[0][0]

        # Add forest-compatible bird to hand
        forest_bird_id = find_bird_id_by_habitats(habitats_include=["forest"])
        state.players[0].bird_hand.append(forest_bird_id)

        power_entry = {
            "power_data": power_data,
            "spot": activating_spot,
        }

        # Should validate when forest bird available
        assert can_execute_power(
            state, power_entry
        ), "Should validate when forest-compatible bird is available"

        # Remove forest birds from hand by filtering to non-forest birds
        init_registries()
        state.players[0].bird_hand = [
            bid
            for bid in state.players[0].bird_hand
            if "forest" not in BIRD_REGISTRY[bid].habitats
        ]

        # Should not validate when no forest birds
        assert not can_execute_power(
            state, power_entry
        ), "Should not validate when no forest-compatible birds available"


if __name__ == "__main__":
    print("Running Power 12 tests...")

    test_power_12_forest_basic()
    print("+ test_power_12_forest_basic passed")

    test_power_12_habitat_filtering()
    print("+ test_power_12_habitat_filtering passed")

    test_power_12_this_variant()
    print("+ test_power_12_this_variant passed")

    test_power_12_no_valid_birds()
    print("+ test_power_12_no_valid_birds passed")

    test_power_12_validation()
    print("+ test_power_12_validation passed")

    print("\n+ All Power 12 tests passed!")
