"""Tests for Power 5: Draw cards (bonus or bird cards with optional discard)."""

from game.core import initiate_state, GamePhase, SimpleAction, IdAction
from game.engine import transition_state
from game.actions import get_actions
from conftest import place_bird_on_board, setup_power_queue


def test_power_5_draw_2_bonus_keep_1_end_to_end():
    """End-to-end test: Power 5 - Draw 2 bonus cards, keep 1."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # bird_hand contains IDs now
    bird_id1 = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, 0, 0, bird_id1)

    initial_bonus_hand_size = len(state.players[0].bonus_hand)
    initial_bonus_deck_size = len(state.bonus_deck)

    # bonus_deck contains IDs now
    bonus_id_1 = state.bonus_deck[-1]
    bonus_id_2 = state.bonus_deck[-2]

    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
                "power_id": 5,
                "power_data": {
                    "data": {
                        "id": 5,
                        "details": {
                            "amount": 2,
                            "bonus": True,
                        },
                    }
                },
                "spot": state.players[0].board[0][0],
            }
        ],
    )

    state = transition_state(state, SimpleAction("activate_power"))

    assert state.game_phase == GamePhase.ACTIVATE_POWERS
    # Stack-based: check execution stack
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "select_bonus"
    ctx = state.action_data.execution_stack[0].context
    assert len(ctx.get("bonus_options", [])) == 2

    # bonus_options contains IDs now
    drawn_ids = ctx["bonus_options"]
    assert bonus_id_1 in drawn_ids
    assert bonus_id_2 in drawn_ids
    assert len(state.bonus_deck) == initial_bonus_deck_size - 2

    actions = get_actions(state)
    expected_action_1 = IdAction("power_5_bonus", bonus_id_1)
    expected_action_2 = IdAction("power_5_bonus", bonus_id_2)
    assert expected_action_1 in actions
    assert expected_action_2 in actions
    assert len(actions) == 2

    selected_bonus_id = bonus_id_1
    state = transition_state(state, IdAction("power_5_bonus", selected_bonus_id))

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.players[0].bonus_hand) == initial_bonus_hand_size + 1
    assert selected_bonus_id in state.players[0].bonus_hand
    assert bonus_id_2 not in state.players[0].bonus_hand
    assert bonus_id_2 not in state.bonus_deck
    assert len(state.bonus_deck) == initial_bonus_deck_size - 2


def test_power_5_draw_cards_discard_at_end_of_turn():
    """End-to-end test: Power 5 - Draw cards, discard 1 at end of turn."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # bird_hand contains IDs now
    bird_id1 = state.players[0].bird_hand[0]
    place_bird_on_board(state, 0, 0, 0, bird_id1)

    initial_hand_size = len(state.players[0].bird_hand)
    initial_deck_size = len(state.bird_deck)

    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
                "power_id": 5,
                "power_data": {
                    "data": {
                        "id": 5,
                        "details": {
                            "amount": 2,
                            "bonus": False,
                            "discard": True,
                        },
                    }
                },
                "spot": state.players[0].board[0][0],
            }
        ],
    )

    state = transition_state(state, SimpleAction("activate_power"))

    assert state.game_phase == GamePhase.END_TURN
    assert len(state.players[0].bird_hand) == initial_hand_size + 2
    assert len(state.bird_deck) == initial_deck_size - 2
    assert len(state.action_data.end_turn_effects) == 1
    assert state.action_data.end_turn_effects[0].effect_type == "discard_cards"

    actions = get_actions(state)
    assert len(actions) == initial_hand_size + 2
    assert all(
        isinstance(action, IdAction) and action.type == "discard_card"
        for action in actions
    )

    # bird_hand contains IDs directly now
    id_to_discard = state.players[0].bird_hand[0]
    state = transition_state(state, IdAction("discard_card", id_to_discard))

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.players[0].bird_hand) == initial_hand_size + 1
    assert id_to_discard not in state.players[0].bird_hand
    assert id_to_discard in state.discarded_birds


def test_power_5_multiple_discards_at_end_of_turn():
    """Test multiple Power 5 birds each requiring discard at end of turn.

    This reproduces a bug where after the first discard, the game gets stuck
    because sub_phase is cleared but effects remain, leaving no valid actions.
    """
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Setup two birds on the board (bird_hand contains IDs now)
    bird_id1 = state.players[0].bird_hand[0]
    bird_id2 = state.players[0].bird_hand[1]
    place_bird_on_board(state, 0, 2, 0, bird_id1)
    place_bird_on_board(state, 0, 2, 1, bird_id2)

    # Ensure player has enough cards to discard
    while len(state.players[0].bird_hand) < 4:
        if state.bird_deck:
            state.players[0].bird_hand.append(state.bird_deck.pop())

    initial_hand_size = len(state.players[0].bird_hand)

    # Setup powers queue with two Power 5 birds (both with discard=True)
    setup_power_queue(
        state,
        [
            {
                "bird_id": bird_id1,
                "power_id": 5,
                "power_data": {
                    "data": {
                        "id": 5,
                        "details": {"amount": 1, "bonus": False, "discard": True},
                    }
                },
                "spot": state.players[0].board[2][0],
            },
            {
                "bird_id": bird_id2,
                "power_id": 5,
                "power_data": {
                    "data": {
                        "id": 5,
                        "details": {"amount": 1, "bonus": False, "discard": True},
                    }
                },
                "spot": state.players[0].board[2][1],
            },
        ],
    )

    # Activate first Power 5 - draws 1 card, queues discard effect
    state = transition_state(state, SimpleAction("activate_power"))
    assert len(state.action_data.end_turn_effects) == 1

    # Activate second Power 5 - draws 1 card, queues another discard effect
    state = transition_state(state, SimpleAction("activate_power"))
    assert len(state.action_data.end_turn_effects) == 2

    # Now we're in END_TURN phase with 2 discard effects
    assert state.game_phase == GamePhase.END_TURN

    # First discard should work
    actions = get_actions(state)
    assert len(actions) > 0, "Should have discard actions for first effect"
    assert any(isinstance(a, IdAction) and a.type == "discard_card" for a in actions)

    # bird_hand contains IDs directly now
    first_id = state.players[0].bird_hand[0]
    state = transition_state(state, IdAction("discard_card", first_id))

    # BUG: After first discard, should still have actions for second discard
    # The bug causes get_actions to return [] because sub_phase is cleared
    # but end_turn_effects still has one effect remaining
    actions = get_actions(state)
    assert len(actions) > 0, (
        "Should have discard actions for second effect, but got empty. "
        f"end_turn_effects={state.action_data.end_turn_effects if state.action_data else None}"
    )
    assert any(isinstance(a, IdAction) and a.type == "discard_card" for a in actions)

    # Second discard
    second_id = state.players[0].bird_hand[0]
    state = transition_state(state, IdAction("discard_card", second_id))

    # Now should have finalized turn
    assert state.game_phase == GamePhase.MAIN_TURN
    # Drew 2 cards (1 each), discarded 2 cards = net 0
    assert len(state.players[0].bird_hand) == initial_hand_size
