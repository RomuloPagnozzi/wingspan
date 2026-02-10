"""Comprehensive end-to-end tests for Power 11: Draw and tuck based on wingspan."""

from game.core import (
    initiate_state,
    GamePhase,
    ActionData,
    QueuedPower,
    get_bird_power,
    BIRD_REGISTRY,
    init_registries,
    SimpleAction,
)
from game.engine import transition_state
from conftest import place_bird_on_board, setup_power_execution


def find_birds_with_power_11():
    """Find all birds with Power 11 and return them grouped by wingspan threshold."""
    init_registries()
    variants = {
        "wingspan_50": [],
        "wingspan_75": [],
        "wingspan_100": [],
    }

    for bird_id in BIRD_REGISTRY:
        power_data = get_bird_power(bird_id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 11:
            details = power_data["data"].get("details", {})
            wingspan_threshold = details.get("wingspan", 0)

            if wingspan_threshold == 50:
                variants["wingspan_50"].append((bird_id, power_data))
            elif wingspan_threshold == 75:
                variants["wingspan_75"].append((bird_id, power_data))
            elif wingspan_threshold == 100:
                variants["wingspan_100"].append((bird_id, power_data))

    return variants


def find_bird_id_by_wingspan(
    less_than: int | None = None, at_least: int | None = None
) -> int:
    """Find a bird ID with wingspan matching criteria."""
    init_registries()
    for bird_id, card in BIRD_REGISTRY.items():
        if less_than is not None and card.wingspan >= less_than:
            continue
        if at_least is not None and card.wingspan < at_least:
            continue
        return bird_id
    raise ValueError(
        f"No bird found with wingspan less_than={less_than}, at_least={at_least}"
    )


def test_power_11_tuck_card():
    """Test Power 11: Draw card below threshold and tuck it."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]

    placed = place_bird_on_board(state, 0, 0, 0, bird_id)
    activating_spot = state.players[0].board[0][0]

    # Find a small bird (wingspan < 75) to put in deck
    small_bird_id = find_bird_id_by_wingspan(less_than=75)
    state.bird_deck = [small_bird_id]

    initial_tucked = placed.state.tucked_cards

    setup_power_execution(
        state, 11, bird_id, activating_spot, state.current_player_index, power_data
    )

    state = transition_state(state, SimpleAction("activate_power"))

    # Get bird from returned state after deepcopy
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird is not None
    assert updated_bird.state.tucked_cards == initial_tucked + 1
    assert len(state.bird_deck) == 0
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_11_discard_card():
    """Test Power 11: Draw card at/above threshold and discard it."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]

    placed = place_bird_on_board(state, 0, 0, 0, bird_id)
    activating_spot = state.players[0].board[0][0]

    # Find a large bird (wingspan >= 75) to put in deck
    large_bird_id = find_bird_id_by_wingspan(at_least=75)
    state.bird_deck = [large_bird_id]

    initial_tucked = placed.state.tucked_cards

    setup_power_execution(
        state, 11, bird_id, activating_spot, state.current_player_index, power_data
    )

    state = transition_state(state, SimpleAction("activate_power"))

    # Check the board bird after deepcopy
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird is not None
    assert updated_bird.state.tucked_cards == initial_tucked
    assert len(state.discarded_birds) == 1
    assert state.discarded_birds[0] == large_bird_id
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_11_multiple_activations():
    """Test Power 11 activated multiple times handles both tuck and discard."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]

    placed = place_bird_on_board(state, 0, 0, 0, bird_id)
    activating_spot = state.players[0].board[0][0]

    # Find birds by wingspan
    small_bird_id = find_bird_id_by_wingspan(less_than=75)
    large_bird_id = find_bird_id_by_wingspan(at_least=75)

    # Test queue processing: two Power 11 activations in sequence
    # Each activation draws exactly 1 card and processes it
    # Deck is LIFO (list.pop()), so last item in list is drawn first

    state.bird_deck = [small_bird_id, large_bird_id]  # large_bird will be popped first
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=11,
            bird_id=bird_id,
            spot_row=activating_spot.row,
            spot_col=activating_spot.col,
            player_index=state.current_player_index,
            power_data=power_data,
        ),
        QueuedPower(
            power_id=11,
            bird_id=bird_id,
            spot_row=activating_spot.row,
            spot_col=activating_spot.col,
            player_index=state.current_player_index,
            power_data=power_data,
        ),
    ]
    state.action_data.current_power_index = 0

    initial_tucked = placed.state.tucked_cards

    # First activation - draws large_bird (popped from end of list)
    state = transition_state(state, SimpleAction("activate_power"))
    # Get bird from returned state after deepcopy
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird is not None
    assert updated_bird.state.tucked_cards == initial_tucked  # No tuck (wingspan >= 75)
    assert len(state.discarded_birds) == 1
    assert state.discarded_birds[0] == large_bird_id
    assert state.game_phase == GamePhase.ACTIVATE_POWERS  # Still processing queue

    # Second activation - draws small_bird
    state = transition_state(state, SimpleAction("activate_power"))
    # Get bird from returned state after deepcopy
    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird is not None
    assert (
        updated_bird.state.tucked_cards == initial_tucked + 1
    )  # Tucked (wingspan < 75)
    assert len(state.discarded_birds) == 1  # Still only large_bird discarded
    assert state.game_phase == GamePhase.MAIN_TURN  # Queue complete


if __name__ == "__main__":
    print("Running Power 11 tests...")

    test_power_11_tuck_card()
    print("+ test_power_11_tuck_card passed")

    test_power_11_discard_card()
    print("+ test_power_11_discard_card passed")

    test_power_11_multiple_activations()
    print("+ test_power_11_multiple_activations passed")

    print("\n+ All Power 11 tests passed!")
