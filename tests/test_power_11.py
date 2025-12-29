"""Comprehensive end-to-end tests for Power 11: Draw and tuck based on wingspan."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase, load_deck, get_bird_power, get_bird
from game.engine import transition_state
from game.actions import get_actions


def find_birds_with_power_11():
    """Find all birds with Power 11 and return them grouped by wingspan threshold."""
    birds = load_deck("birds")
    variants = {
        "wingspan_50": [],
        "wingspan_75": [],
        "wingspan_100": [],
    }

    for bird in birds:
        power_data = get_bird_power(bird.id)
        if power_data and power_data.get("data") and power_data["data"].get("id") == 11:
            details = power_data["data"].get("details", {})
            wingspan_threshold = details.get("wingspan", 0)

            if wingspan_threshold == 50:
                variants["wingspan_50"].append((bird.id, power_data))
            elif wingspan_threshold == 75:
                variants["wingspan_75"].append((bird.id, power_data))
            elif wingspan_threshold == 100:
                variants["wingspan_100"].append((bird.id, power_data))

    return variants


def test_power_11_tuck_card():
    """Test Power 11: Draw card below threshold and tuck it."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]
    power_11_bird = get_bird(bird_id)

    state.players[0].board[0][0].bird = power_11_bird
    if power_11_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_11_bird)

    activating_spot = state.players[0].board[0][0]

    birds = load_deck("birds")
    small_bird = [b for b in birds if b.wingspan < 75][0]
    state.bird_deck = [small_bird]

    initial_tucked = power_11_bird.tucked_cards

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird_id,
                "power_id": 11,
                "power_data": power_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert power_11_bird.tucked_cards == initial_tucked + 1
    assert len(state.bird_deck) == 0
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_11_discard_card():
    """Test Power 11: Draw card at/above threshold and discard it."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]
    power_11_bird = get_bird(bird_id)

    state.players[0].board[0][0].bird = power_11_bird
    if power_11_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_11_bird)

    activating_spot = state.players[0].board[0][0]

    birds = load_deck("birds")
    large_bird = [b for b in birds if b.wingspan >= 75][0]
    state.bird_deck = [large_bird]

    initial_tucked = power_11_bird.tucked_cards

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird_id,
                "power_id": 11,
                "power_data": power_data,
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert power_11_bird.tucked_cards == initial_tucked
    assert len(state.discarded_birds) == 1
    assert state.discarded_birds[0] == large_bird
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_11_multiple_activations():
    """Test Power 11 activated multiple times handles both tuck and discard."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    variants = find_birds_with_power_11()
    bird_id, power_data = variants["wingspan_75"][0]
    power_11_bird = get_bird(bird_id)

    state.players[0].board[0][0].bird = power_11_bird
    if power_11_bird in state.players[0].bird_hand:
        state.players[0].bird_hand.remove(power_11_bird)

    activating_spot = state.players[0].board[0][0]

    birds = load_deck("birds")
    small_bird = [b for b in birds if b.wingspan < 75][0]
    large_bird = [b for b in birds if b.wingspan >= 75][0]

    state.bird_deck = [large_bird, small_bird]

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird_id,
                "power_id": 11,
                "power_data": power_data,
                "spot": activating_spot,
            },
            {
                "bird_id": bird_id,
                "power_id": 11,
                "power_data": power_data,
                "spot": activating_spot,
            },
        ],
        "current_power_index": 0,
    }

    initial_tucked = power_11_bird.tucked_cards

    state = transition_state(state, "activate_power")
    assert power_11_bird.tucked_cards == initial_tucked + 1

    state = transition_state(state, "activate_power")
    assert power_11_bird.tucked_cards == initial_tucked + 1
    assert len(state.discarded_birds) == 1
    assert state.discarded_birds[0] == large_bird
    assert state.game_phase == GamePhase.MAIN_TURN


if __name__ == "__main__":
    print("Running Power 11 tests...")

    test_power_11_tuck_card()
    print("✓ test_power_11_tuck_card passed")

    test_power_11_discard_card()
    print("✓ test_power_11_discard_card passed")

    test_power_11_multiple_activations()
    print("✓ test_power_11_multiple_activations passed")

    print("\n✅ All Power 11 tests passed!")
