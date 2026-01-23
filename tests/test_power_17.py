"""Tests for Power 17: Tuck 1 card from hand behind bird for bonus."""

import sys

sys.path.append(".")

from game.data import initiate_state, GamePhase, ActionData, QueuedPower
from game.engine import transition_state
from game.actions import get_actions
from game.power_validators import can_execute_power


def setup_power_17_execution(state, player_index, bird_id, spot, power_data=None):
    """Set up Power 17 execution with new ActionData structure."""
    if power_data is None:
        power_data = {"data": {"id": 17}}
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=17,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


def create_power_17_data(types):
    """Create Power 17 data structure."""
    return {
        "color": "brown",
        "data": {
            "id": 17,
            "details": {"types": types},
        },
    }


def setup_power_17_state(state, types):
    """Setup state with Power 17 activation."""
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    bird = state.bird_deck.pop()
    spot = state.players[0].board[0][0]
    spot.bird = bird

    power_data = create_power_17_data(types)

    setup_power_17_execution(
        state, state.current_player_index, bird.id, spot, power_data
    )

    return state


def test_power_17_cannot_execute_when_no_cards():
    """Test Power 17 cannot execute when player has no cards in hand."""
    state = initiate_state(2)
    state.current_player_index = 0
    state.players[0].bird_hand = []

    power_data = create_power_17_data(["fruit"])
    power_entry = {
        "power_data": power_data,
        "spot": state.players[0].board[0][0],
        "bird_id": 9999,
    }

    assert not can_execute_power(state, power_entry)


def test_power_17_can_execute_when_has_cards():
    """Test Power 17 can execute when player has cards in hand."""
    state = initiate_state(2)
    state.current_player_index = 0

    power_data = create_power_17_data(["fruit"])
    power_entry = {
        "power_data": power_data,
        "spot": state.players[0].board[0][0],
        "bird_id": 9999,
    }

    assert can_execute_power(state, power_entry)


def test_power_17_generates_tuck_actions():
    """Test Power 17 generates tuck actions for each card in hand."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["fruit"])

    card_ids = [card.id for card in state.players[0].bird_hand]

    state = transition_state(state, "activate_power")

    assert state.action_data.execution_stack[-1].phase == "select_card"

    actions = get_actions(state)
    expected = [f"tuck_card_{cid}" for cid in card_ids]

    assert len(actions) == len(expected)
    for exp in expected:
        assert exp in actions


def test_power_17_two_food_types_generates_food_actions():
    """Test Power 17 generates food selection actions for two-food-type variant."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["invertebrate", "seed"])

    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    assert state.action_data.execution_stack[-1].phase == "select_food"

    actions = get_actions(state)

    assert len(actions) == 2
    assert "select_food_invertebrate" in actions
    assert "select_food_seed" in actions


def test_power_17_tuck_removes_card_and_increments_tucked():
    """Test tucking removes card from hand and increments bird.tucked_cards."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["fruit"])

    # Get spot from board where bird was placed in setup_power_17_state
    spot = state.players[0].board[0][0]
    initial_tucked = spot.bird.tucked_cards
    initial_hand_size = len(state.players[0].bird_hand)
    card_to_tuck = state.players[0].bird_hand[0]

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_to_tuck.id}")

    assert len(state.players[0].bird_hand) == initial_hand_size - 1
    assert card_to_tuck not in state.players[0].bird_hand
    # Get bird from new state after transitions
    assert state.players[0].board[0][0].bird.tucked_cards == initial_tucked + 1


def test_power_17_bonus_card():
    """Test Power 17 with card bonus draws one card."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["card"])

    initial_hand_size = len(state.players[0].bird_hand)
    initial_deck_size = len(state.bird_deck)
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    assert len(state.players[0].bird_hand) == initial_hand_size
    assert len(state.bird_deck) == initial_deck_size - 1


def test_power_17_bonus_egg():
    """Test Power 17 with egg bonus lays egg on activating bird."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["egg"])

    # Get spot from board where bird was placed in setup_power_17_state
    spot = state.players[0].board[0][0]
    initial_eggs = spot.bird.eggs
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    # Get bird from new state after transitions
    assert state.players[0].board[0][0].bird.eggs == initial_eggs + 1


def test_power_17_bonus_fruit():
    """Test Power 17 with fruit bonus gains fruit."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["fruit"])

    initial_fruit = state.players[0].food.get("fruit", 0)
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    assert state.players[0].food.get("fruit", 0) == initial_fruit + 1


def test_power_17_bonus_seed():
    """Test Power 17 with seed bonus gains seed."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["seed"])

    initial_seed = state.players[0].food.get("seed", 0)
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    assert state.players[0].food.get("seed", 0) == initial_seed + 1


def test_power_17_select_invertebrate():
    """Test Power 17 two-step flow selecting invertebrate."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["invertebrate", "seed"])

    initial_invertebrate = state.players[0].food.get("invertebrate", 0)
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")
    state = transition_state(state, "select_food_invertebrate")

    assert state.players[0].food.get("invertebrate", 0) == initial_invertebrate + 1


def test_power_17_select_seed():
    """Test Power 17 two-step flow selecting seed."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["invertebrate", "seed"])

    initial_seed = state.players[0].food.get("seed", 0)
    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")
    state = transition_state(state, "select_food_seed")

    assert state.players[0].food.get("seed", 0) == initial_seed + 1


def test_power_17_transitions_to_main_turn():
    """Test Power 17 cleans up and transitions to main turn."""
    state = initiate_state(2)
    state = setup_power_17_state(state, ["fruit"])

    card_id = state.players[0].bird_hand[0].id

    state = transition_state(state, "activate_power")
    state = transition_state(state, f"tuck_card_{card_id}")

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.action_data.execution_stack) == 0


if __name__ == "__main__":
    print("Running Power 17 tests...")

    test_power_17_cannot_execute_when_no_cards()
    print("✓ test_power_17_cannot_execute_when_no_cards passed")

    test_power_17_can_execute_when_has_cards()
    print("✓ test_power_17_can_execute_when_has_cards passed")

    test_power_17_generates_tuck_actions()
    print("✓ test_power_17_generates_tuck_actions passed")

    test_power_17_two_food_types_generates_food_actions()
    print("✓ test_power_17_two_food_types_generates_food_actions passed")

    test_power_17_tuck_removes_card_and_increments_tucked()
    print("✓ test_power_17_tuck_removes_card_and_increments_tucked passed")

    test_power_17_bonus_card()
    print("✓ test_power_17_bonus_card passed")

    test_power_17_bonus_egg()
    print("✓ test_power_17_bonus_egg passed")

    test_power_17_bonus_fruit()
    print("✓ test_power_17_bonus_fruit passed")

    test_power_17_bonus_seed()
    print("✓ test_power_17_bonus_seed passed")

    test_power_17_select_invertebrate()
    print("✓ test_power_17_select_invertebrate passed")

    test_power_17_select_seed()
    print("✓ test_power_17_select_seed passed")

    test_power_17_transitions_to_main_turn()
    print("✓ test_power_17_transitions_to_main_turn passed")

    print("\n✅ All Power 17 tests passed!")
