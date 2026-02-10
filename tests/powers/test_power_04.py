"""Tests for Power 4: Discard to gain resources (exchange powers)."""

from game.core import (
    initiate_state,
    GamePhase,
    SimpleAction,
    IdAction,
    NameAction,
    FoodMapAction,
    frozen_map,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import place_bird_on_board, setup_power_queue


def test_power_4_discard_egg_gain_wild_food_end_to_end():
    """End-to-end test: Power 4 - Discard egg to gain wild food (single and multiple)."""
    # Test 1: Discard egg, gain 1 wild food
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has two birds with eggs (bird_hand contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    bird_id2 = state.players[0].bird_hand[1]

    # Place birds using helper (with eggs)
    place_bird_on_board(state, 0, 0, 0, bird_id1, eggs=2)  # Activating bird
    place_bird_on_board(state, 0, 0, 1, bird_id2, eggs=1)  # Other bird

    # Player starts with 1 seed
    state.players[0].food = {"seed": 1}

    # Power 4: discard egg, gain 1 wild
    activating_spot = state.players[0].board[0][0]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
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
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Should be in discard selection phase (stack-based)
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "select_discard"

    # Player must discard from bird2 (not activating bird)
    actions = get_actions(state)
    assert IdAction("discard_egg_from", bird_id2) in actions
    assert (
        IdAction("discard_egg_from", bird_id1) not in actions
    ), "Cannot discard from activating bird"

    # Discard egg from bird2
    state = transition_state(state, IdAction("discard_egg_from", bird_id2))

    # Should now be in gain selection phase
    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    assert state.action_data.execution_stack[0].phase == "select_gain"

    # Get available food choices
    actions = get_actions(state)
    assert FoodMapAction("gain_food_combo", frozen_map({"invertebrate": 1})) in actions
    assert FoodMapAction("gain_food_combo", frozen_map({"fish": 1})) in actions

    # Choose to gain 1 fish
    state = transition_state(
        state, FoodMapAction("gain_food_combo", frozen_map({"fish": 1}))
    )

    # Verify results (get birds from returned state after deepcopy)
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].board[0][1].bird
    assert state.players[0].board[0][0].bird
    assert (
        state.players[0].board[0][1].bird.state.eggs == 0
    ), "Egg was discarded from bird2"
    assert (
        state.players[0].board[0][0].bird.state.eggs == 2
    ), "Activating bird unchanged"
    assert state.players[0].food == {"seed": 1, "fish": 1}, "Gained 1 fish"


def test_power_4_discard_egg_gain_2_wild_food():
    """Test Power 4: Discard egg, gain 2 wild foods."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has two birds with eggs (bird_hand contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    bird_id2 = state.players[0].bird_hand[1]

    # Place birds using helper (with eggs)
    place_bird_on_board(state, 0, 0, 0, bird_id1, eggs=1)  # Activating bird
    place_bird_on_board(state, 0, 0, 1, bird_id2, eggs=2)  # Other bird

    state.players[0].food = {}

    # Power 4: discard egg, gain 2 wild
    activating_spot = state.players[0].board[0][0]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
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
    )

    # Activate and discard
    state = transition_state(state, SimpleAction("activate_power"))
    state = transition_state(state, IdAction("discard_egg_from", bird_id2))

    # Get available combinations for 2 foods
    actions = get_actions(state)
    assert FoodMapAction("gain_food_combo", frozen_map({"seed": 2})) in actions
    assert (
        FoodMapAction("gain_food_combo", frozen_map({"seed": 1, "fish": 1})) in actions
    )

    # Choose 2 seeds
    state = transition_state(
        state, FoodMapAction("gain_food_combo", frozen_map({"seed": 2}))
    )

    # Verify results (get bird from returned state after deepcopy)
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].board[0][1].bird
    assert (
        state.players[0].board[0][1].bird.state.eggs == 1
    ), "Egg was discarded from bird2"
    assert state.players[0].food == {"seed": 2}, "Gained 2 seeds"


def test_power_4_discard_egg_draw_cards_end_to_end():
    """End-to-end test: Power 4 - Discard egg to draw cards."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird with eggs (bird_hand contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, 0, 0, bird_id1, eggs=1)

    initial_hand_size = len(state.players[0].bird_hand)
    initial_deck_size = len(state.bird_deck)

    # Power 4: discard egg, draw 2 cards
    activating_spot = state.players[0].board[0][0]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
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
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Discard egg (can discard from activating bird since gain != "wild")
    state = transition_state(state, IdAction("discard_egg_from", bird_id1))

    # Verify results (get bird from returned state after deepcopy)
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].board[0][0].bird
    assert state.players[0].board[0][0].bird.state.eggs == 0, "Egg was discarded"
    assert len(state.players[0].bird_hand) == initial_hand_size + 2, "Drew 2 cards"
    assert len(state.bird_deck) == initial_deck_size - 2, "2 cards removed from deck"


def test_power_4_discard_food_tuck_cards_end_to_end():
    """End-to-end test: Power 4 - Discard food to tuck cards."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird and fish food (bird_hand contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, 0, 0, bird_id1, tucked_cards=1)

    state.players[0].food = {"fish": 2, "seed": 1}
    initial_deck_size = len(state.bird_deck)

    # Power 4: discard fish, tuck 2 cards
    activating_spot = state.players[0].board[0][0]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
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
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Should be in discard selection phase (stack-based)
    assert state.action_data.execution_stack[0].phase == "select_discard"

    # Verify fish discard action is available
    actions = get_actions(state)
    assert (
        NameAction("discard_food", "fish") in actions
    ), "Fish discard should be available"

    # Discard fish
    state = transition_state(state, NameAction("discard_food", "fish"))

    # Verify results (get bird from returned state after deepcopy)
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].board[0][0].bird
    assert state.players[0].food == {"fish": 1, "seed": 1}, "1 fish discarded"
    assert (
        state.players[0].board[0][0].bird.state.tucked_cards == 3
    ), "Tucked 2 cards (1->3)"
    assert len(state.bird_deck) == initial_deck_size - 2, "2 cards removed from deck"


def test_power_4_discard_food_gain_specific_food_end_to_end():
    """End-to-end test: Power 4 - Discard food to gain specific food."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup: Player 0 has bird and seed food (bird_hand contains IDs)
    bird_id1 = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, 0, 0, bird_id1)

    state.players[0].food = {"seed": 3}

    # Power 4: discard seed, gain rodent (specific, not wild)
    activating_spot = state.players[0].board[0][0]
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
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
    )

    # Activate power
    state = transition_state(state, SimpleAction("activate_power"))

    # Should be in discard selection phase (stack-based)
    assert state.action_data.execution_stack[0].phase == "select_discard"

    # Verify seed discard action is available
    actions = get_actions(state)
    assert (
        NameAction("discard_food", "seed") in actions
    ), "Seed discard should be available"

    # Discard seed
    state = transition_state(state, NameAction("discard_food", "seed"))

    # Verify results - should auto-gain rodent without choice
    assert state.game_phase == GamePhase.MAIN_TURN
    assert state.players[0].food == {
        "seed": 2,
        "rodent": 1,
    }, "Discarded 1 seed, gained 1 rodent"
