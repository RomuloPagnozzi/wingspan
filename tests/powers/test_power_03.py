"""Tests for Power 3: Cache seed on activating bird."""

from game.core import initiate_state, GamePhase, SimpleAction
from game.engine import transition_state
from conftest import place_bird_on_board, setup_power_queue


def test_power_3_caches_seed_on_activating_bird_end_to_end():
    """End-to-end test: Power 3 caches 1 seed on the specific bird that activated it."""
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Get bird IDs from hands (bird_hand now contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    bird_id2 = state.players[0].bird_hand[1]
    bird_id3 = state.players[0].bird_hand[2]
    other_bird_id = state.players[1].bird_hand[0]

    # Place three birds on player 0's board in different spots
    place_bird_on_board(state, 0, 0, 0, bird_id1, stashed_food=0)  # Forest row, spot 0
    place_bird_on_board(
        state, 0, 0, 1, bird_id2, stashed_food=2
    )  # Forest row, spot 1 (already has some cached food)
    place_bird_on_board(state, 0, 1, 0, bird_id3, stashed_food=0)  # Grassland row

    # Place birds on other players to verify they're unaffected
    place_bird_on_board(state, 1, 0, 0, other_bird_id, stashed_food=0)

    # Power 3 is activated by bird2 (spot [0][1])
    activating_spot = state.players[0].board[0][1]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id2,  # Use bird_id2 (already an ID)
                "power_id": 3,
                "power_data": {"data": {"id": 3}},
                "spot": activating_spot,
            }
        ],
    )

    state = transition_state(state, SimpleAction("activate_power"))

    # Verify only the activating bird (bird2) gained 1 seed
    assert state.players[0].board[0][0].bird
    assert state.players[0].board[0][1].bird
    assert state.players[0].board[1][0].bird
    assert state.players[1].board[0][0].bird
    assert state.players[0].board[0][0].bird.state.stashed_food == 0, "Bird1 unchanged"
    assert (
        state.players[0].board[0][1].bird.state.stashed_food == 3
    ), "Bird2 gained 1 (2->3)"
    assert state.players[0].board[1][0].bird.state.stashed_food == 0, "Bird3 unchanged"
    assert (
        state.players[1].board[0][0].bird.state.stashed_food == 0
    ), "Other player unchanged"
    assert state.game_phase == GamePhase.MAIN_TURN
