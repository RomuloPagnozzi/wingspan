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


def test_power_3_caches_seed_on_activating_bird_end_to_end():
    """End-to-end test: Power 3 caches 1 seed on the specific bird that activated it."""
    state = initiate_state(3)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Place three birds on player 0's board in different spots
    bird1 = state.players[0].bird_hand[0]
    bird1.stashed_food = 0
    state.players[0].board[0][0].bird = bird1  # Forest row, spot 0
    state.players[0].bird_hand.remove(bird1)

    bird2 = state.players[0].bird_hand[0]
    bird2.stashed_food = 2  # Already has some cached food
    state.players[0].board[0][1].bird = bird2  # Forest row, spot 1
    state.players[0].bird_hand.remove(bird2)

    bird3 = state.players[0].bird_hand[0]
    bird3.stashed_food = 0
    state.players[0].board[1][0].bird = bird3  # Grassland row
    state.players[0].bird_hand.remove(bird3)

    # Place birds on other players to verify they're unaffected
    other_bird = state.players[1].bird_hand[0]
    other_bird.stashed_food = 0
    state.players[1].board[0][0].bird = other_bird
    state.players[1].bird_hand.remove(other_bird)

    # Power 3 is activated by bird2 (spot [0][1])
    activating_spot = state.players[0].board[0][1]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird2.id,
                "power_id": 3,
                "power_data": {"data": {"id": 3}},
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    state = transition_state(state, "activate_power")

    # Verify only the activating bird (bird2) gained 1 seed
    assert state.players[0].board[0][0].bird
    assert state.players[0].board[0][1].bird
    assert state.players[0].board[1][0].bird
    assert state.players[1].board[0][0].bird
    assert state.players[0].board[0][0].bird.stashed_food == 0, "Bird1 unchanged"
    assert state.players[0].board[0][1].bird.stashed_food == 3, "Bird2 gained 1 (2→3)"
    assert state.players[0].board[1][0].bird.stashed_food == 0, "Bird3 unchanged"
    assert state.players[1].board[0][0].bird.stashed_food == 0, "Other player unchanged"
    assert state.game_phase == GamePhase.MAIN_TURN


def test_power_4_discard_egg_gain_wild_food_end_to_end():
    """End-to-end test: Power 4 - Discard egg to gain wild food (single and multiple)."""
    # Test 1: Discard egg, gain 1 wild food
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has two birds with eggs
    bird1 = state.players[0].bird_hand[0]
    bird1.eggs = 2
    bird1.egg_limit = 3
    state.players[0].board[0][0].bird = bird1  # Activating bird
    state.players[0].bird_hand.remove(bird1)

    bird2 = state.players[0].bird_hand[0]
    bird2.eggs = 1
    bird2.egg_limit = 2
    state.players[0].board[0][1].bird = bird2  # Other bird
    state.players[0].bird_hand.remove(bird2)

    # Player starts with 1 seed
    state.players[0].food = {"seed": 1}

    # Power 4: discard egg, gain 1 wild
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird1.id,
                "power_id": 4,
                "power_data": {
                    "data": {
                        "id": 4,
                        "details": {
                            "discard": "egg",
                            "gain": "wild",
                            "gain_qty": 1,
                            "action": "gain",
                        },
                    }
                },
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Should be in discard selection phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.get("sub_phase") == "power_4_select_discard"

    # Player must discard from bird2 (not activating bird)
    actions = get_actions(state)
    assert f"discard_egg_from_{bird2.id}" in actions
    assert (
        f"discard_egg_from_{bird1.id}" not in actions
    ), "Cannot discard from activating bird"

    # Discard egg from bird2
    state = transition_state(state, f"discard_egg_from_{bird2.id}")

    # Should now be in gain selection phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.get("sub_phase") == "power_4_select_gain"

    # Get available food choices
    actions = get_actions(state)
    assert f'gain_{json.dumps({"invertebrate": 1})}' in actions
    assert f'gain_{json.dumps({"fish": 1})}' in actions

    # Choose to gain 1 fish
    state = transition_state(state, f'gain_{json.dumps({"fish": 1})}')

    # Verify results
    assert state.game_phase == GamePhase.MAIN_TURN
    assert bird2.eggs == 0, "Egg was discarded from bird2"
    assert bird1.eggs == 2, "Activating bird unchanged"
    assert state.players[0].food == {"seed": 1, "fish": 1}, "Gained 1 fish"

    # Test 2: Discard egg, gain 2 wild foods
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has two birds with eggs
    bird1 = state.players[0].bird_hand[0]
    bird1.eggs = 1
    bird1.egg_limit = 3
    state.players[0].board[0][0].bird = bird1  # Activating bird
    state.players[0].bird_hand.remove(bird1)

    bird2 = state.players[0].bird_hand[0]
    bird2.eggs = 2
    bird2.egg_limit = 3
    state.players[0].board[0][1].bird = bird2  # Other bird
    state.players[0].bird_hand.remove(bird2)

    state.players[0].food = {}

    # Power 4: discard egg, gain 2 wild
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird1.id,
                "power_id": 4,
                "power_data": {
                    "data": {
                        "id": 4,
                        "details": {
                            "discard": "egg",
                            "gain": "wild",
                            "gain_qty": 2,
                            "action": "gain",
                        },
                    }
                },
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate and discard
    state = transition_state(state, "activate_power")
    state = transition_state(state, f"discard_egg_from_{bird2.id}")

    # Get available combinations for 2 foods
    actions = get_actions(state)
    assert f'gain_{json.dumps({"seed": 2})}' in actions
    assert f'gain_{json.dumps({"seed": 1, "fish": 1})}' in actions

    # Choose 2 seeds
    state = transition_state(state, f'gain_{json.dumps({"seed": 2})}')

    # Verify results
    assert state.game_phase == GamePhase.MAIN_TURN
    assert bird2.eggs == 1, "Egg was discarded from bird2"
    assert state.players[0].food == {"seed": 2}, "Gained 2 seeds"


def test_power_4_discard_egg_draw_cards_end_to_end():
    """End-to-end test: Power 4 - Discard egg to draw cards."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird with eggs
    bird1 = state.players[0].bird_hand[0]
    bird1.eggs = 1
    bird1.egg_limit = 3
    state.players[0].board[0][0].bird = bird1
    state.players[0].bird_hand.remove(bird1)

    initial_hand_size = len(state.players[0].bird_hand)
    initial_deck_size = len(state.bird_deck)

    # Power 4: discard egg, draw 2 cards
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird1.id,
                "power_id": 4,
                "power_data": {
                    "data": {
                        "id": 4,
                        "details": {
                            "discard": "egg",
                            "gain": "card",
                            "gain_qty": 2,
                            "action": "draw",
                        },
                    }
                },
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Discard egg (can discard from activating bird since gain != "wild")
    state = transition_state(state, f"discard_egg_from_{bird1.id}")

    # Verify results
    assert state.game_phase == GamePhase.MAIN_TURN
    assert bird1.eggs == 0, "Egg was discarded"
    assert len(state.players[0].bird_hand) == initial_hand_size + 2, "Drew 2 cards"
    assert len(state.bird_deck) == initial_deck_size - 2, "2 cards removed from deck"


def test_power_4_discard_food_tuck_cards_end_to_end():
    """End-to-end test: Power 4 - Discard food to tuck cards."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird and fish food
    bird1 = state.players[0].bird_hand[0]
    bird1.tucked_cards = 1
    state.players[0].board[0][0].bird = bird1
    state.players[0].bird_hand.remove(bird1)

    state.players[0].food = {"fish": 2, "seed": 1}
    initial_deck_size = len(state.bird_deck)

    # Power 4: discard fish, tuck 2 cards
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird1.id,
                "power_id": 4,
                "power_data": {
                    "data": {
                        "id": 4,
                        "details": {
                            "discard": "fish",
                            "gain": "card",
                            "gain_qty": 2,
                            "action": "tuck",
                        },
                    }
                },
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Should be in discard selection phase
    assert state.action_data.get("sub_phase") == "power_4_select_discard"

    # Verify fish discard action is available
    actions = get_actions(state)
    assert "discard_food_fish" in actions, "Fish discard should be available"

    # Discard fish
    state = transition_state(state, "discard_food_fish")

    # Verify results
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].food == {"fish": 1, "seed": 1}, "1 fish discarded"
    assert bird1.tucked_cards == 3, "Tucked 2 cards (1→3)"
    assert len(state.bird_deck) == initial_deck_size - 2, "2 cards removed from deck"


def test_power_4_discard_food_gain_specific_food_end_to_end():
    """End-to-end test: Power 4 - Discard food to gain specific food."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird and seed food
    bird1 = state.players[0].bird_hand[0]
    state.players[0].board[0][0].bird = bird1
    state.players[0].bird_hand.remove(bird1)

    state.players[0].food = {"seed": 3}

    # Power 4: discard seed, gain rodent (specific, not wild)
    activating_spot = state.players[0].board[0][0]
    state.action_data = {
        "powers_queue": [
            {
                "bird_id": bird1.id,
                "power_id": 4,
                "power_data": {
                    "data": {
                        "id": 4,
                        "details": {
                            "discard": "seed",
                            "gain": "rodent",
                            "gain_qty": 1,
                            "action": "gain",
                        },
                    }
                },
                "spot": activating_spot,
            }
        ],
        "current_power_index": 0,
    }

    # Activate power
    state = transition_state(state, "activate_power")

    # Should be in discard selection phase
    assert state.action_data.get("sub_phase") == "power_4_select_discard"

    # Verify seed discard action is available
    actions = get_actions(state)
    assert "discard_food_seed" in actions, "Seed discard should be available"

    # Discard seed
    state = transition_state(state, "discard_food_seed")

    # Verify results - should auto-gain rodent without choice
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].food == {
        "seed": 2,
        "rodent": 1,
    }, "Discarded 1 seed, gained 1 rodent"
