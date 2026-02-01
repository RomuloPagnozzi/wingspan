"""Tests for Power 1: All players gain a resource (food or card)."""

from game.core import initiate_state, GamePhase
from game.engine import transition_state
from conftest import setup_power_queue


def test_power_1_execution():
    """Power type 1 gives all players a resource."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    initial_p0 = state.players[0].food.get("seed", 0)
    initial_p1 = state.players[1].food.get("seed", 0)

    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            }
        ],
    )

    state = transition_state(state, "activate_power")

    assert state.players[0].food.get("seed", 0) == initial_p0 + 1
    assert state.players[1].food.get("seed", 0) == initial_p1 + 1
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_1_all_players_gain_cards_end_to_end():
    """End-to-end test: Power 1 gives all players exactly 1 card."""
    # Test with varying player counts
    for num_players in [2, 3, 4, 5]:
        state = initiate_state(num_players)
        state.game_phase = GamePhase.ACTIVATE_POWERS
        state.current_player_index = 0

        # Record initial card counts for all players
        initial_cards = [len(p.bird_hand) for p in state.players]

        setup_power_queue(
            state,
            [
                {
                    "bird_id": 112,
                    "power_data": {"data": {"id": 1, "details": {"type": "card"}}},
                }
            ],
        )

        state = transition_state(state, "activate_power")

        # Verify all players got exactly 1 card
        for i, player in enumerate(state.players):
            assert (
                len(player.bird_hand) == initial_cards[i] + 1
            ), f"Player {i} in {num_players}-player game should have gained exactly 1 card"


def test_power_1_all_players_gain_food_end_to_end():
    """End-to-end test: Power 1 gives all players exactly 1 food resource."""
    for num_players in [2, 3, 4, 5]:
        for food_type in ["fish", "seed", "fruit", "invertebrate"]:
            state = initiate_state(num_players)
            state.game_phase = GamePhase.ACTIVATE_POWERS
            state.current_player_index = 0

            # Record initial food counts
            initial_food = [p.food.get(food_type, 0) for p in state.players]

            setup_power_queue(
                state,
                [
                    {
                        "bird_id": 1,
                        "power_data": {
                            "data": {"id": 1, "details": {"type": food_type}}
                        },
                    }
                ],
            )

            state = transition_state(state, "activate_power")

            # Verify all players got exactly 1 food
            for i, player in enumerate(state.players):
                assert player.food.get(food_type, 0) == initial_food[i] + 1, (
                    f"Player {i} in {num_players}-player game should have gained "
                    f"exactly 1 {food_type}"
                )
