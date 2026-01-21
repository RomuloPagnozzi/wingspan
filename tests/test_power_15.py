"""Tests for Power 15: Roll dice not in birdfeeder."""

import sys
from unittest.mock import patch

sys.path.append(".")

from game.data import (
    initiate_state,
    GamePhase,
    get_bird,
    get_bird_power,
    ActionData,
    QueuedPower,
)
from game.engine import transition_state
from game.powers_validators import can_execute_power


def setup_power_15_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 15 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 15}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=15,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def get_all_birds(state):
    """Get all birds from game state."""
    return (
        list(state.bird_deck)
        + list(state.bird_tray)
        + list(state.players[0].bird_hand)
        + list(state.players[1].bird_hand)
    )


def find_power_15_bird(state):
    """Find a bird with Power 15."""
    for bird in get_all_birds(state):
        power = get_bird_power(bird.id)
        if power and power.get("data") and power["data"].get("id") == 15:
            return bird, power
    return None, None


def test_power_15_cannot_execute_when_feeder_full():
    """Test Power 15 cannot execute when birdfeeder is full (5 dice)."""
    state = initiate_state(2)
    power_15_bird, power_15_data = find_power_15_bird(state)
    assert power_15_bird, "Should find Power 15 bird"

    state.current_player_index = 0
    state.players[0].board[0][0].bird = power_15_bird
    spot = state.players[0].board[0][0]

    state.feeder = ["seed", "fish", "fruit", "rodent", "invertebrate"]

    power_entry = {
        "power_data": power_15_data,
        "spot": spot,
        "bird_id": power_15_bird.id,
    }
    assert not can_execute_power(state, power_entry)


def test_power_15_caches_food_on_match():
    """Test Power 15 caches food when rolled dice matches food type."""
    state = initiate_state(2)
    power_15_bird, power_15_data = find_power_15_bird(state)
    assert power_15_bird, "Should find Power 15 bird"

    food_type = power_15_data["data"]["details"]["type"]

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    state.players[0].board[0][0].bird = power_15_bird
    spot = state.players[0].board[0][0]

    state.feeder = []
    power_15_bird.stashed_food = 0

    setup_power_15_execution(
        state, state.current_player_index, power_15_bird.id, spot, power_15_data
    )

    with patch("game.power_handlers.random.choice", return_value=[food_type]):
        state = transition_state(state, "activate_power")

    assert power_15_bird.stashed_food == 1


def test_power_15_no_cache_on_no_match():
    """Test Power 15 does not cache food when rolled dice don't match."""
    state = initiate_state(2)
    power_15_bird, power_15_data = find_power_15_bird(state)
    assert power_15_bird, "Should find Power 15 bird"

    food_type = power_15_data["data"]["details"]["type"]
    non_matching = [
        f for f in ["fish", "fruit", "rodent", "seed", "invertebrate"] if f != food_type
    ][0]

    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    state.players[0].board[0][0].bird = power_15_bird
    spot = state.players[0].board[0][0]

    state.feeder = []
    power_15_bird.stashed_food = 0

    setup_power_15_execution(
        state, state.current_player_index, power_15_bird.id, spot, power_15_data
    )

    with patch("game.power_handlers.random.choice", return_value=[non_matching]):
        state = transition_state(state, "activate_power")

    assert power_15_bird.stashed_food == 0


if __name__ == "__main__":
    print("Running Power 15 tests...")

    test_power_15_cannot_execute_when_feeder_full()
    print("✓ test_power_15_cannot_execute_when_feeder_full passed")

    test_power_15_caches_food_on_match()
    print("✓ test_power_15_caches_food_on_match passed")

    test_power_15_no_cache_on_no_match()
    print("✓ test_power_15_no_cache_on_no_match passed")

    print("\n✅ All Power 15 tests passed!")
