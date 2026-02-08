"""Tests for Power 15: Roll dice not in birdfeeder."""

import random

from game.core import (
    initiate_state,
    GamePhase,
    get_bird_power,
    init_registries,
)
from game.engine import transition_state
from game.power import can_execute_power
from conftest import place_bird_on_board, setup_power_execution

DICE_FACES = [
    ["fish"],
    ["fruit"],
    ["rodent"],
    ["invertebrate"],
    ["seed"],
    ["invertebrate", "seed"],
]


def get_all_bird_ids(state):
    """Get all bird IDs from game state."""
    return (
        list(state.bird_deck)
        + list(state.bird_tray)
        + list(state.players[0].bird_hand)
        + list(state.players[1].bird_hand)
    )


def find_power_15_bird_id(state):
    """Find a bird ID with Power 15."""
    init_registries()
    for bird_id in get_all_bird_ids(state):
        power = get_bird_power(bird_id)
        if power and power.get("data") and power["data"].get("id") == 15:
            return bird_id, power
    return None, None


def find_seed_for_roll(food_type: str, should_match: bool, n_dice: int = 5) -> int:
    """Find a seed that produces a roll matching (or not matching) the food type."""
    for seed in range(1000):
        rng = random.Random(seed)
        rolls = [rng.choice(DICE_FACES) for _ in range(n_dice)]
        has_match = any(food_type in face for face in rolls)
        if has_match == should_match:
            return seed
    raise ValueError(f"Could not find seed for {food_type} match={should_match}")


def test_power_15_cannot_execute_when_feeder_full():
    """Test Power 15 cannot execute when birdfeeder is full (5 dice)."""
    state = initiate_state(2, seed=42)
    power_15_bird_id, power_15_data = find_power_15_bird_id(state)
    assert power_15_bird_id, "Should find Power 15 bird"

    state.current_player_index = 0
    place_bird_on_board(state, 0, 0, 0, power_15_bird_id)
    spot = state.players[0].board[0][0]

    state.feeder = {
        0: ["seed"],
        1: ["fish"],
        2: ["fruit"],
        3: ["rodent"],
        4: ["invertebrate"],
    }

    power_entry = {
        "power_data": power_15_data,
        "spot": spot,
        "bird_id": power_15_bird_id,
    }
    assert not can_execute_power(state, power_entry)


def test_power_15_caches_food_on_match():
    """Test Power 15 caches food when rolled dice matches food type."""
    state = initiate_state(2, seed=42)
    power_15_bird_id, power_15_data = find_power_15_bird_id(state)
    assert power_15_bird_id, "Should find Power 15 bird"
    assert power_15_data
    food_type = power_15_data["data"]["details"]["type"]

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    placed = place_bird_on_board(state, 0, 0, 0, power_15_bird_id)
    spot = state.players[0].board[0][0]

    state.feeder = {}
    placed.state.stashed_food = 0

    setup_power_execution(
        state, 15, power_15_bird_id, spot, state.current_player_index, power_15_data
    )

    # Set RNG to a seed that produces a matching roll
    matching_seed = find_seed_for_roll(food_type, should_match=True, n_dice=5)
    state.rng = random.Random(matching_seed)

    state = transition_state(state, "activate_power")

    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird
    assert updated_bird.state.stashed_food == 1


def test_power_15_no_cache_on_no_match():
    """Test Power 15 does not cache food when rolled dice don't match."""
    state = initiate_state(2, seed=42)
    power_15_bird_id, power_15_data = find_power_15_bird_id(state)
    assert power_15_bird_id, "Should find Power 15 bird"
    assert power_15_data
    food_type = power_15_data["data"]["details"]["type"]

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    placed = place_bird_on_board(state, 0, 0, 0, power_15_bird_id)
    spot = state.players[0].board[0][0]

    state.feeder = {}
    placed.state.stashed_food = 0

    setup_power_execution(
        state, 15, power_15_bird_id, spot, state.current_player_index, power_15_data
    )

    # Set RNG to a seed that produces NO matching roll
    non_matching_seed = find_seed_for_roll(food_type, should_match=False, n_dice=5)
    state.rng = random.Random(non_matching_seed)

    state = transition_state(state, "activate_power")

    updated_bird = state.players[0].board[0][0].bird
    assert updated_bird
    assert updated_bird.state.stashed_food == 0


if __name__ == "__main__":
    print("Running Power 15 tests...")

    test_power_15_cannot_execute_when_feeder_full()
    print("✓ test_power_15_cannot_execute_when_feeder_full passed")

    test_power_15_caches_food_on_match()
    print("✓ test_power_15_caches_food_on_match passed")

    test_power_15_no_cache_on_no_match()
    print("✓ test_power_15_no_cache_on_no_match passed")

    print("\n✅ All Power 15 tests passed!")
