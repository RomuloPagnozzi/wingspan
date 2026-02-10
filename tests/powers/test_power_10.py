"""Comprehensive end-to-end tests for Power 10: Lay eggs on birds."""

from game.core import (
    initiate_state,
    GamePhase,
    get_bird_power,
    get_bird_card,
    BIRD_REGISTRY,
    init_registries,
    SimpleAction,
    IdAction,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import (
    place_bird_on_board,
    filter_bird_ids_by_nest,
    filter_bird_ids_with_capacity,
    get_bird_egg_limit,
    setup_power_execution,
)


def find_birds_with_power_10():
    """Find all birds with Power 10 and return them grouped by variant."""
    init_registries()
    variants = {
        "this_true": [],
        "type_any": [],
        "type_bowl": [],
        "type_cavity": [],
        "type_ground": [],
        "type_platform": [],
    }

    for bird_id in BIRD_REGISTRY:
        power_data = get_bird_power(bird_id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 10:
            details = power_data["data"].get("details", {})
            is_this = details.get("this", False)
            nest_type = details.get("type", "")

            if is_this:
                variants["this_true"].append((bird_id, power_data))
            elif nest_type == "any":
                variants["type_any"].append((bird_id, power_data))
            elif nest_type == "bowl":
                variants["type_bowl"].append((bird_id, power_data))
            elif nest_type == "cavity":
                variants["type_cavity"].append((bird_id, power_data))
            elif nest_type == "ground":
                variants["type_ground"].append((bird_id, power_data))
            elif nest_type == "platform":
                variants["type_platform"].append((bird_id, power_data))

    return variants


def test_power_10_this_true():
    """Test Power 10: Lay egg on activating bird (this: True)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (this: True)
    variants = find_birds_with_power_10()
    assert len(variants["this_true"]) > 0, "Should find bird with power 10 (this: True)"

    bird_id, power_data = variants["this_true"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place bird on board (forest row, col 0)
    placed = place_bird_on_board(state, 0, 0, 0, bird_id)
    activating_spot = state.players[0].board[0][0]

    # Verify bird has egg capacity
    assert placed.state.eggs < bird_card.egg_limit, "Bird should have egg capacity"
    initial_eggs = placed.state.eggs

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify can activate
    actions = get_actions(state)
    assert SimpleAction("activate_power") in actions, "Should be able to activate power"

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify egg was added to activating bird (get from returned state after deepcopy)
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird
    assert updated_bird.state.eggs == initial_eggs + 1, "Bird should have one more egg"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_this_true_at_limit():
    """Test Power 10 cannot execute when activating bird is at egg limit."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (this: True)
    variants = find_birds_with_power_10()
    assert len(variants["this_true"]) > 0, "Should find bird with power 10 (this: True)"

    bird_id, power_data = variants["this_true"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place bird on board and fill to egg limit
    placed = place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)
    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert (
        SimpleAction("activate_power") not in actions
    ), "Should not be able to activate power"
    assert SimpleAction("skip_power") in actions, "Should be able to skip power"


def test_power_10_type_bowl():
    """Test Power 10: Lay eggs on all bowl nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: bowl)
    variants = find_birds_with_power_10()
    assert len(variants["type_bowl"]) > 0, "Should find bird with power 10 (type: bowl)"

    bird_id, power_data = variants["type_bowl"][0]

    # Place activating bird on board
    place_bird_on_board(state, 0, 0, 0, bird_id)

    # Add bowl nest birds from state's own bird deck (excluding the activating bird)
    bowl_bird_ids = filter_bird_ids_by_nest(
        state.bird_deck, "bowl", min_egg_limit=0, exclude_ids={bird_id}
    )[:3]
    assert len(bowl_bird_ids) >= 3, "Need at least 3 bowl birds in deck"

    # Place bowl birds on board
    place_bird_on_board(state, 0, 1, 0, bowl_bird_ids[0])
    place_bird_on_board(state, 0, 1, 1, bowl_bird_ids[1])
    # Set third bird at egg limit
    bird2_limit = get_bird_egg_limit(bowl_bird_ids[2])
    place_bird_on_board(state, 0, 2, 0, bowl_bird_ids[2], eggs=bird2_limit)

    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_1_1 is not None and bird_2_0 is not None
    initial_eggs_0 = bird_1_0.state.eggs
    initial_eggs_1 = bird_1_1.state.eggs
    initial_eggs_2 = bird_2_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify eggs added to bowl birds with capacity
    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_1_1 is not None and bird_2_0 is not None
    assert (
        bird_1_0.state.eggs == initial_eggs_0 + 1
    ), "Bowl bird 0 should have one more egg"
    assert (
        bird_1_1.state.eggs == initial_eggs_1 + 1
    ), "Bowl bird 1 should have one more egg"
    assert (
        bird_2_0.state.eggs == initial_eggs_2
    ), "Bowl bird 2 at limit should be unchanged"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_cavity():
    """Test Power 10: Lay eggs on all cavity nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: cavity)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_cavity"]) > 0
    ), "Should find bird with power 10 (type: cavity)"

    bird_id, power_data = variants["type_cavity"][0]

    # Place activating bird on board
    place_bird_on_board(state, 0, 0, 0, bird_id)

    # Add cavity nest birds from state's own bird deck
    cavity_bird_ids = filter_bird_ids_by_nest(
        state.bird_deck, "cavity", min_egg_limit=0
    )[:2]
    assert len(cavity_bird_ids) >= 2, "Need at least 2 cavity birds in deck"

    # Place cavity birds on board
    place_bird_on_board(state, 0, 1, 0, cavity_bird_ids[0])
    place_bird_on_board(state, 0, 2, 0, cavity_bird_ids[1])

    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    initial_eggs_0 = bird_1_0.state.eggs
    initial_eggs_1 = bird_2_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify eggs added to cavity birds
    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    assert (
        bird_1_0.state.eggs == initial_eggs_0 + 1
    ), "Cavity bird 0 should have one more egg"
    assert (
        bird_2_0.state.eggs == initial_eggs_1 + 1
    ), "Cavity bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_ground():
    """Test Power 10: Lay eggs on all ground nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: ground)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_ground"]) > 0
    ), "Should find bird with power 10 (type: ground)"

    bird_id, power_data = variants["type_ground"][0]

    # Place activating bird on board
    place_bird_on_board(state, 0, 0, 0, bird_id)

    # Add ground nest birds from state's own bird deck
    ground_bird_ids = filter_bird_ids_by_nest(
        state.bird_deck, "ground", min_egg_limit=0
    )[:2]
    assert len(ground_bird_ids) >= 2, "Need at least 2 ground birds in deck"

    # Place ground birds on board
    place_bird_on_board(state, 0, 1, 0, ground_bird_ids[0])
    place_bird_on_board(state, 0, 2, 0, ground_bird_ids[1])

    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    initial_eggs_0 = bird_1_0.state.eggs
    initial_eggs_1 = bird_2_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify eggs added to ground birds
    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    assert (
        bird_1_0.state.eggs == initial_eggs_0 + 1
    ), "Ground bird 0 should have one more egg"
    assert (
        bird_2_0.state.eggs == initial_eggs_1 + 1
    ), "Ground bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_platform():
    """Test Power 10: Lay eggs on all platform nest birds."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: platform)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_platform"]) > 0
    ), "Should find bird with power 10 (type: platform)"

    bird_id, power_data = variants["type_platform"][0]

    # Place activating bird on board
    place_bird_on_board(state, 0, 0, 0, bird_id)

    # Add platform nest birds from state's own bird deck
    platform_bird_ids = filter_bird_ids_by_nest(
        state.bird_deck, "platform", min_egg_limit=0
    )[:2]
    assert len(platform_bird_ids) >= 2, "Need at least 2 platform birds in deck"

    # Place platform birds on board
    place_bird_on_board(state, 0, 1, 0, platform_bird_ids[0])
    place_bird_on_board(state, 0, 2, 0, platform_bird_ids[1])

    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    initial_eggs_0 = bird_1_0.state.eggs
    initial_eggs_1 = bird_2_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify eggs added to platform birds
    bird_1_0 = state.players[0].board[1][0].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_2_0 is not None
    assert (
        bird_1_0.state.eggs == initial_eggs_0 + 1
    ), "Platform bird 0 should have one more egg"
    assert (
        bird_2_0.state.eggs == initial_eggs_1 + 1
    ), "Platform bird 1 should have one more egg"

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_any_single_bird():
    """Test Power 10: Lay egg on any bird when only one valid bird exists (auto-complete)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place activating bird on board at egg limit
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)

    # Add only ONE other bird with egg capacity
    other_bird_ids = filter_bird_ids_with_capacity(
        state.bird_deck, exclude_ids={bird_id}
    )
    assert len(other_bird_ids) >= 1, "Need at least 1 bird with egg capacity in deck"
    other_bird_id = other_bird_ids[0]
    place_bird_on_board(state, 0, 1, 0, other_bird_id)

    bird_1_0 = state.players[0].board[1][0].bird
    assert bird_1_0 is not None
    initial_eggs = bird_1_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify egg was added to the only bird
    bird_1_0 = state.players[0].board[1][0].bird
    assert bird_1_0 is not None
    assert (
        bird_1_0.state.eggs == initial_eggs + 1
    ), "Only valid bird should have one more egg"

    # Verify no sub-phase was created (auto-completed)
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_type_any_multiple_birds():
    """Test Power 10: Lay egg on any bird when multiple valid birds exist (requires choice)."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place activating bird on board at egg limit
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)

    # Add multiple birds with egg capacity
    other_bird_ids = filter_bird_ids_with_capacity(
        state.bird_deck, exclude_ids={bird_id}
    )[:3]
    assert len(other_bird_ids) >= 3, "Need at least 3 birds with egg capacity in deck"

    place_bird_on_board(state, 0, 1, 0, other_bird_ids[0])
    place_bird_on_board(state, 0, 1, 1, other_bird_ids[1])
    place_bird_on_board(state, 0, 2, 0, other_bird_ids[2])

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should enter sub-phase)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify sub-phase created
    assert state.action_data.execution_stack[-1].phase == "select_bird"

    # Verify bird selection actions available
    actions = get_actions(state)
    bird_actions = [
        a for a in actions if isinstance(a, IdAction) and a.type == "select_bird"
    ]
    assert len(bird_actions) == 3, "Should have 3 bird selection actions"

    # Verify valid bird IDs stored
    valid_bird_ids = state.action_data.execution_stack[-1].context.get(
        "valid_bird_ids", []
    )
    assert len(valid_bird_ids) == 3
    assert other_bird_ids[0] in valid_bird_ids
    assert other_bird_ids[1] in valid_bird_ids
    assert other_bird_ids[2] in valid_bird_ids


def test_power_10_type_any_selection():
    """Test Power 10: Verify correct bird receives egg after selection."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place activating bird on board at egg limit
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)

    # Add multiple birds with egg capacity
    other_bird_ids = filter_bird_ids_with_capacity(
        state.bird_deck, exclude_ids={bird_id}
    )[:3]
    assert len(other_bird_ids) >= 3, "Need at least 3 birds with egg capacity in deck"

    place_bird_on_board(state, 0, 1, 0, other_bird_ids[0])
    place_bird_on_board(state, 0, 1, 1, other_bird_ids[1])
    place_bird_on_board(state, 0, 2, 0, other_bird_ids[2])

    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_1_1 is not None and bird_2_0 is not None
    initial_eggs_0 = bird_1_0.state.eggs
    initial_eggs_1 = bird_1_1.state.eggs
    initial_eggs_2 = bird_2_0.state.eggs

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should enter sub-phase)
    state = transition_state(state, SimpleAction("activate_power"))

    # Select bird 1 (middle bird)
    state = transition_state(state, IdAction("select_bird", other_bird_ids[1]))

    # Verify only selected bird received egg
    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    assert bird_1_0 is not None and bird_1_1 is not None and bird_2_0 is not None
    assert bird_1_0.state.eggs == initial_eggs_0, "Bird 0 should be unchanged"
    assert bird_1_1.state.eggs == initial_eggs_1 + 1, "Bird 1 should have one more egg"
    assert bird_2_0.state.eggs == initial_eggs_2, "Bird 2 should be unchanged"

    # Verify cleanup
    assert len(state.action_data.execution_stack) == 0

    # Verify power completed (transitioned to MAIN_TURN)
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_10_no_valid_birds_specific_type():
    """Test Power 10 cannot execute when no birds match specific nest type."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: cavity)
    variants = find_birds_with_power_10()
    assert (
        len(variants["type_cavity"]) > 0
    ), "Should find bird with power 10 (type: cavity)"

    bird_id, power_data = variants["type_cavity"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place activating bird on board at egg limit
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)

    # Add ONLY bowl nest birds (not cavity)
    bowl_bird_ids = filter_bird_ids_by_nest(state.bird_deck, "bowl", min_egg_limit=0)[
        :2
    ]
    assert len(bowl_bird_ids) >= 2, "Need at least 2 bowl birds in deck"

    place_bird_on_board(state, 0, 1, 0, bowl_bird_ids[0])
    place_bird_on_board(state, 0, 2, 0, bowl_bird_ids[1])

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert (
        SimpleAction("activate_power") not in actions
    ), "Should not be able to activate power"
    assert SimpleAction("skip_power") in actions, "Should be able to skip power"


def test_power_10_all_birds_at_limit():
    """Test Power 10 cannot execute when all birds are at egg limit."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: any)
    variants = find_birds_with_power_10()
    assert len(variants["type_any"]) > 0, "Should find bird with power 10 (type: any)"

    bird_id, power_data = variants["type_any"][0]
    bird_card = get_bird_card(bird_id)
    assert bird_card

    # Place activating bird on board at egg limit
    place_bird_on_board(state, 0, 0, 0, bird_id, eggs=bird_card.egg_limit)

    # Add other birds all at egg limit
    other_bird_ids = filter_bird_ids_with_capacity(
        state.bird_deck, exclude_ids={bird_id}
    )[:2]
    assert len(other_bird_ids) >= 2, "Need at least 2 birds with egg capacity in deck"

    bird1_limit = get_bird_egg_limit(other_bird_ids[0])
    bird2_limit = get_bird_egg_limit(other_bird_ids[1])

    place_bird_on_board(state, 0, 1, 0, other_bird_ids[0], eggs=bird1_limit)
    place_bird_on_board(state, 0, 2, 0, other_bird_ids[1], eggs=bird2_limit)

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Verify cannot activate (only skip available)
    actions = get_actions(state)
    assert (
        SimpleAction("activate_power") not in actions
    ), "Should not be able to activate power"
    assert SimpleAction("skip_power") in actions, "Should be able to skip power"


def test_power_10_mixed_capacity_birds():
    """Test Power 10 only lays eggs on birds with capacity."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find bird with Power 10 (type: bowl)
    variants = find_birds_with_power_10()
    assert len(variants["type_bowl"]) > 0, "Should find bird with power 10 (type: bowl)"

    bird_id, power_data = variants["type_bowl"][0]

    # Place activating bird on board
    place_bird_on_board(state, 0, 0, 0, bird_id)

    # Add bowl nest birds from state's own bird deck (excluding the activating bird)
    bowl_bird_ids = filter_bird_ids_by_nest(
        state.bird_deck, "bowl", min_egg_limit=0, exclude_ids={bird_id}
    )[:4]
    assert len(bowl_bird_ids) >= 4, "Need at least 4 bowl birds in deck"

    bird1_limit = get_bird_egg_limit(bowl_bird_ids[1])
    bird3_limit = get_bird_egg_limit(bowl_bird_ids[3])

    place_bird_on_board(state, 0, 1, 0, bowl_bird_ids[0])  # Has capacity
    place_bird_on_board(state, 0, 1, 1, bowl_bird_ids[1], eggs=bird1_limit)  # At limit
    place_bird_on_board(state, 0, 2, 0, bowl_bird_ids[2])  # Has capacity
    place_bird_on_board(state, 0, 2, 1, bowl_bird_ids[3], eggs=bird3_limit)  # At limit

    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    bird_2_1 = state.players[0].board[2][1].bird
    assert bird_1_0 and bird_1_1 and bird_2_0 and bird_2_1
    initial_eggs = [
        bird_1_0.state.eggs,
        bird_1_1.state.eggs,
        bird_2_0.state.eggs,
        bird_2_1.state.eggs,
    ]

    activating_spot = state.players[0].board[0][0]

    # Setup power activation
    setup_power_execution(
        state, 10, bird_id, activating_spot, state.current_player_index, power_data
    )

    # Execute activation (should auto-complete)
    state = transition_state(state, SimpleAction("activate_power"))

    # Verify only birds with capacity received eggs
    bird_1_0 = state.players[0].board[1][0].bird
    bird_1_1 = state.players[0].board[1][1].bird
    bird_2_0 = state.players[0].board[2][0].bird
    bird_2_1 = state.players[0].board[2][1].bird
    assert bird_1_0 and bird_1_1 and bird_2_0 and bird_2_1
    assert (
        bird_1_0.state.eggs == initial_eggs[0] + 1
    ), "Bird 0 with capacity should gain egg"
    assert bird_1_1.state.eggs == initial_eggs[1], "Bird 1 at limit should be unchanged"
    assert (
        bird_2_0.state.eggs == initial_eggs[2] + 1
    ), "Bird 2 with capacity should gain egg"
    assert bird_2_1.state.eggs == initial_eggs[3], "Bird 3 at limit should be unchanged"


def test_power_10_validation():
    """Test Power 10 validation works correctly for all variants."""
    from game.power import can_execute_power

    state = initiate_state(2)
    state.current_player_index = 0

    variants = find_birds_with_power_10()

    # Test this: True validation
    if variants["this_true"]:
        bird_id, power_data = variants["this_true"][0]
        bird_card = get_bird_card(bird_id)
        assert bird_card

        # Should be valid when bird has capacity (eggs = 0)
        placed = place_bird_on_board(state, 0, 0, 0, bird_id, eggs=0)
        spot = state.players[0].board[0][0]
        power_entry = {"power_data": power_data, "spot": spot}
        assert can_execute_power(
            state, power_entry
        ), "Should validate when bird has capacity"

        # Should be invalid when bird at limit
        placed.state.eggs = bird_card.egg_limit
        assert not can_execute_power(
            state, power_entry
        ), "Should not validate when bird at limit"


if __name__ == "__main__":
    print("Running Power 10 tests...")

    test_power_10_this_true()
    print("+ test_power_10_this_true passed")

    test_power_10_this_true_at_limit()
    print("+ test_power_10_this_true_at_limit passed")

    test_power_10_type_bowl()
    print("+ test_power_10_type_bowl passed")

    test_power_10_type_cavity()
    print("+ test_power_10_type_cavity passed")

    test_power_10_type_ground()
    print("+ test_power_10_type_ground passed")

    test_power_10_type_platform()
    print("+ test_power_10_type_platform passed")

    test_power_10_type_any_single_bird()
    print("+ test_power_10_type_any_single_bird passed")

    test_power_10_type_any_multiple_birds()
    print("+ test_power_10_type_any_multiple_birds passed")

    test_power_10_type_any_selection()
    print("+ test_power_10_type_any_selection passed")

    test_power_10_no_valid_birds_specific_type()
    print("+ test_power_10_no_valid_birds_specific_type passed")

    test_power_10_all_birds_at_limit()
    print("+ test_power_10_all_birds_at_limit passed")

    test_power_10_mixed_capacity_birds()
    print("+ test_power_10_mixed_capacity_birds passed")

    test_power_10_validation()
    print("+ test_power_10_validation passed")

    print("\n+ All Power 10 tests passed!")
