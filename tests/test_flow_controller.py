"""Test flow control and power activation."""

import sys

sys.path.append(".")

import json
from game.data import initiate_state, GamePhase
from game.engine import (
    _finish_main_action,
    _finish_main_action_no_powers,
    _check_powers_done,
    transition_state,
)
from game.actions import get_actions


def test_finish_main_action_no_powers():
    """Main action with no triggered powers goes to MAIN_TURN."""
    state = initiate_state(2)
    first_player_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    state.current_player_index = first_player_idx
    state.players[first_player_idx].action_cubes = 5

    state = _finish_main_action(state, "forest")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.current_player_index == (first_player_idx + 1) % 2
    assert state.action_data == {}
    assert state.players[first_player_idx].action_cubes == 4


def test_finish_main_action_no_powers_explicit():
    """Main action that never triggers powers (play bird)."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].action_cubes = 5

    state = _finish_main_action_no_powers(state)

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].action_cubes == 4


def test_check_powers_done_transitions():
    """When power queue exhausted, transition to MAIN_TURN."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [{"bird_id": 1, "power_data": {}}],
        "current_power_index": 1,  # Past end of queue
    }

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.action_data == {}


def test_check_powers_done_continues():
    """When powers remain, stay in ACTIVATE_POWERS."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [
            {"bird_id": 1, "power_data": {}},
            {"bird_id": 2, "power_data": {}},
        ],
        "current_power_index": 0,
    }

    state = _check_powers_done(state)

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert "powers_queue" in state.action_data


def test_power_activation_skip():
    """Skipping a power advances the index."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            },
            {
                "bird_id": 2,
                "power_data": {"data": {"id": 1, "details": {"type": "fish"}}},
            },
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "skip_power")

    assert state.action_data["current_power_index"] == 1


def test_power_1_execution():
    """Power type 1 gives all players a resource."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    initial_p0 = state.players[0].food.get("seed", 0)
    initial_p1 = state.players[1].food.get("seed", 0)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 1, "details": {"type": "seed"}}},
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert state.players[0].food.get("seed", 0) == initial_p0 + 1
    assert state.players[1].food.get("seed", 0) == initial_p1 + 1
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_2_sets_up_multi_player():
    """Power type 2 sets up multi-player state for sequential choices."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Give both players bowl nest birds
    bird0 = state.players[0].bird_hand[0]
    bird0.nest = "bowl"
    bird0.egg_limit = 3
    state.players[0].board[0][0].bird = bird0
    state.players[0].bird_hand.remove(bird0)

    bird1 = state.players[1].bird_hand[0]
    bird1.nest = "bowl"
    bird1.egg_limit = 3
    state.players[1].board[0][0].bird = bird1
    state.players[1].bird_hand.remove(bird1)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    assert state.action_data["sub_phase"] == "power_2_choices"
    assert state.action_data["activator"] == 0
    assert state.action_data["awaiting_players"] == [0, 1]
    assert state.action_data["nest_type"] == "bowl"
    assert state.current_player_index == 0  # Activator goes first


def test_multi_player_actions_generated():
    """Multi-player power generates correct choice actions."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    bird0 = state.players[0].bird_hand[0]
    bird0.nest = "bowl"
    bird0.egg_limit = 3
    state.players[0].board[0][0].bird = bird0
    state.players[0].bird_hand.remove(bird0)

    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
        "current_power_index": 0,
        "sub_phase": "power_2_choices",
        "nest_type": "bowl",
        "activator": 0,
        "awaiting_players": [0],
    }

    actions = get_actions(state)

    assert len(actions) > 0
    assert all(a.startswith("activate_") for a in actions)


def test_power_1_all_players_gain_cards_end_to_end():
    """End-to-end test: Power 1 gives all players exactly 1 card."""
    # Test with varying player counts
    for num_players in [2, 3, 4, 5]:
        state = initiate_state(num_players)
        state.game_phase = GamePhase.ACTIVATE_POWERS
        state.current_player_index = 0

        # Record initial card counts for all players
        initial_cards = [len(p.bird_hand) for p in state.players]

        state.action_data = {
            "powers_queue": [
                {
                    "bird_id": 112,  # Northern Shoveler with power 1 (card)
                    "power_data": {"data": {"id": 1, "details": {"type": "card"}}},
                }
            ],
            "current_power_index": 0,
        }

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

            state.action_data = {
                "powers_queue": [
                    {
                        "bird_id": 1,
                        "power_data": {
                            "data": {"id": 1, "details": {"type": food_type}}
                        },
                    }
                ],
                "current_power_index": 0,
            }

            state = transition_state(state, "activate_power")

            # Verify all players got exactly 1 food
            for i, player in enumerate(state.players):
                assert player.food.get(food_type, 0) == initial_food[i] + 1, (
                    f"Player {i} in {num_players}-player game should have gained "
                    f"exactly 1 {food_type}"
                )


def test_power_2_all_players_lay_eggs_end_to_end():
    """End-to-end test: Power 2 allows all players to lay 1 egg on matching nest types."""
    for num_players in [2, 3, 4, 5]:
        for nest_type in ["bowl", "cavity", "ground", "platform"]:
            state = initiate_state(num_players)
            state.game_phase = GamePhase.ACTIVATE_POWERS
            state.current_player_index = 0

            # Give each player a bird with the matching nest type
            placed_birds = []
            for i, player in enumerate(state.players):
                bird = state.players[i].bird_hand[0]
                bird.nest = nest_type
                bird.egg_limit = 3
                bird.eggs = 0
                state.players[i].board[0][0].bird = bird
                state.players[i].bird_hand.remove(bird)
                placed_birds.append(bird.id)

            state.action_data = {
                "powers_queue": [
                    {
                        "bird_id": 1,
                        "power_data": {
                            "data": {"id": 2, "details": {"type": nest_type}}
                        },
                    }
                ],
                "current_power_index": 0,
            }

            # Activate the power (sets up multi-player state)
            state = transition_state(state, "activate_power")

            # Each player makes their egg-laying choice
            while state.game_phase == GamePhase.ACTIVATE_POWERS:
                current_player = state.current_player_index
                bird_id = placed_birds[current_player]

                # Have each player lay 1 egg on their bird
                action = f"activate_{json.dumps({str(bird_id): 1})}"
                state = transition_state(state, action)

            # Verify all players laid exactly 1 egg
            for i, player in enumerate(state.players):
                assert player.board[0][0].bird
                assert player.board[0][0].bird.eggs == 1, (
                    f"Player {i} in {num_players}-player game with {nest_type} nest "
                    f"should have laid exactly 1 egg"
                )

            # Verify we're back to main turn
            assert state.game_phase == GamePhase.MAIN_TURN


def test_power_2_with_mixed_eligibility():
    """Test power 2 when only some players have matching nest types."""
    state = initiate_state(4)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Players 0 and 2 have bowl nests, players 1 and 3 have cavity nests
    bowl_bird_ids = []
    for i in [0, 2]:
        bird = state.players[i].bird_hand[0]
        bird.nest = "bowl"
        bird.egg_limit = 3
        bird.eggs = 0
        state.players[i].board[0][0].bird = bird
        state.players[i].bird_hand.remove(bird)
        bowl_bird_ids.append(bird.id)

    for i in [1, 3]:
        bird = state.players[i].bird_hand[0]
        bird.nest = "cavity"
        bird.egg_limit = 3
        bird.eggs = 0
        state.players[i].board[0][0].bird = bird
        state.players[i].bird_hand.remove(bird)

    # Activate power 2 for bowl nests
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    # Only players 0 and 2 should be in awaiting list
    assert set(state.action_data["awaiting_players"]) == {0, 2}

    # Players 0 and 2 make their choices
    for player_index, bird_id in zip([0, 2], bowl_bird_ids):
        assert state.current_player_index == player_index
        action = f"activate_{json.dumps({str(bird_id): 1})}"
        state = transition_state(state, action)

    # Verify only players 0 and 2 laid eggs
    assert state.players[0].board[0][0].bird
    assert state.players[2].board[0][0].bird
    assert state.players[0].board[0][0].bird.eggs == 1
    assert state.players[2].board[0][0].bird.eggs == 1

    # Players 1 and 3 should have no eggs (cavity nests don't match bowl power)
    assert state.players[1].board[0][0].bird
    assert state.players[3].board[0][0].bird
    assert state.players[1].board[0][0].bird.eggs == 0
    assert state.players[3].board[0][0].bird.eggs == 0

    # Verify we're back to main turn
    assert state.game_phase == GamePhase.MAIN_TURN
