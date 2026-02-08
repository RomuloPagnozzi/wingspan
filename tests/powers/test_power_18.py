"""Tests for Power 18: Pink power triggered when opponent plays bird in habitat."""

from game.core import (
    GameState,
    GamePhase,
    Player,
    Spot,
    PinkTrigger,
    BIRD_REGISTRY,
)
from game.engine import transition_state
from game.actions import get_actions
from game.utils import get_triggered_pink_powers
from game.power import can_execute_power
from conftest import (
    place_bird_on_board,
    setup_power_execution,
)


def get_any_bird_id() -> int:
    """Get any valid bird ID from the registry."""
    return next(iter(BIRD_REGISTRY.keys()))


def create_power_18_data(habitat: str, resource: str) -> dict:
    """Create power_data dict for Power 18."""
    return {
        "color": "pink",
        "data": {"id": 18, "details": {"habitat": habitat, "resource": resource}},
    }


def create_power_18_entry(
    player_index: int, bird_id: int, spot: Spot, habitat: str, resource: str
) -> dict:
    """Create a power entry for Power 18."""
    return {
        "player_index": player_index,
        "bird_id": bird_id,
        "power_id": 18,
        "power_data": create_power_18_data(habitat, resource),
        "spot": spot,
    }


class TestPower18ForestInvertebrate:
    """Tests for Power 18 forest variant (gain invertebrate)."""

    def test_power_18_forest_invertebrate_gains_food(self):
        """When activated, player gains 1 invertebrate from supply."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]

        initial_invertebrate = state.players[1].food.get("invertebrate", 0)

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("forest", "invertebrate")
        )
        state.current_player_index = 1

        # Activate the power
        state = transition_state(state, "activate_power")

        assert state.players[1].food.get("invertebrate", 0) == initial_invertebrate + 1


class TestPower18WetlandFish:
    """Tests for Power 18 wetland variant (gain fish)."""

    def test_power_18_wetland_fish_gains_food(self):
        """When activated, player gains 1 fish from supply."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 2, 0, bird_id)
        spot = state.players[1].board[2][0]

        initial_fish = state.players[1].food.get("fish", 0)

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("wetland", "fish")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")

        assert state.players[1].food.get("fish", 0) == initial_fish + 1


class TestPower18GrasslandCard:
    """Tests for Power 18 grassland variant (tuck card)."""

    def test_power_18_grassland_tuck_enters_sub_phase(self):
        """When resource is card, enters sub_phase for card selection."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 1, 0, bird_id)
        spot = state.players[1].board[1][0]

        # bird_hand contains IDs
        all_bird_ids = list(BIRD_REGISTRY.keys())
        state.players[1].bird_hand = [all_bird_ids[1], all_bird_ids[2]]

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("grassland", "card")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")

        # Should be in select_card phase
        assert len(state.action_data.execution_stack) == 1
        assert state.action_data.execution_stack[0].phase == "select_card"

    def test_power_18_generates_tuck_card_actions(self):
        """Action generator produces tuck_card actions for each card in hand."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Use real bird IDs from registry
        all_bird_ids = list(BIRD_REGISTRY.keys())
        bird_id = all_bird_ids[0]
        hand_ids = all_bird_ids[1:4]  # Get 3 different IDs for hand

        place_bird_on_board(state, 1, 1, 0, bird_id)
        spot = state.players[1].board[1][0]

        # bird_hand now contains IDs
        state.players[1].bird_hand = hand_ids

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("grassland", "card")
        )
        state.current_player_index = 1

        # Activate to enter select_card phase
        state = transition_state(state, "activate_power")

        actions = get_actions(state)

        assert f"tuck_card_{hand_ids[0]}" in actions
        assert f"tuck_card_{hand_ids[1]}" in actions
        assert f"tuck_card_{hand_ids[2]}" in actions
        assert len(actions) == 3

    def test_power_18_tuck_card_removes_from_hand(self):
        """Selecting a card removes it from hand and increments tucked_cards."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Use real bird IDs from registry
        all_bird_ids = list(BIRD_REGISTRY.keys())
        bird_id = all_bird_ids[0]
        hand_id_1 = all_bird_ids[1]
        hand_id_2 = all_bird_ids[2]

        place_bird_on_board(state, 1, 1, 0, bird_id)
        spot = state.players[1].board[1][0]

        # bird_hand now contains IDs
        state.players[1].bird_hand = [hand_id_1, hand_id_2]

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("grassland", "card")
        )
        state.current_player_index = 1
        assert spot.bird
        initial_tucked = spot.bird.state.tucked_cards

        # Activate then tuck the first card
        state = transition_state(state, "activate_power")
        state = transition_state(state, f"tuck_card_{hand_id_1}")

        assert len(state.players[1].bird_hand) == 1
        # bird_hand contains IDs directly now
        assert state.players[1].bird_hand[0] == hand_id_2
        assert state.players[1].board[1][0].bird
        assert (
            state.players[1].board[1][0].bird.state.tucked_cards == initial_tucked + 1
        )


class TestPower18TriggerMatching:
    """Tests for Power 18 trigger matching logic."""

    def test_power_18_wrong_habitat_no_trigger(self):
        """Power 18 (forest) does NOT trigger when bird played in wetland."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)

        # Manually set up power data for forest variant
        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {
                "id": 18,
                "details": {"habitat": "forest", "resource": "invertebrate"},
            },
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "wetland"},
            )

        assert len(triggered) == 0

    def test_power_18_correct_habitat_triggers(self):
        """Power 18 (forest) triggers when bird played in forest."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {
                "id": 18,
                "details": {"habitat": "forest", "resource": "invertebrate"},
            },
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 1
        assert triggered[0]["player_index"] == 1
        assert triggered[0]["bird_id"] == bird_id

    def test_power_18_own_action_no_trigger(self):
        """Power 18 does NOT trigger on player's own bird-playing action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 0, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {
                "id": 18,
                "details": {"habitat": "forest", "resource": "invertebrate"},
            },
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 0

    def test_power_18_already_used_no_trigger(self):
        """Power 18 does NOT trigger if already used this rotation."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        state.players[1].used_pink_powers.add(bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {
                "id": 18,
                "details": {"habitat": "forest", "resource": "invertebrate"},
            },
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 0


class TestPower18SkipAndValidation:
    """Tests for skipping Power 18 and validation."""

    def test_power_18_skip_power(self):
        """Player can skip activating Power 18."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]

        initial_food = dict(state.players[1].food)

        setup_power_execution(
            state, 18, bird_id, spot, 1, create_power_18_data("forest", "invertebrate")
        )
        state.current_player_index = 1

        actions = get_actions(state)
        assert "skip_power" in actions

        state = transition_state(state, "skip_power")

        assert state.players[1].food == initial_food

    def test_power_18_validation_card_no_cards(self):
        """Power 18 (card variant) cannot execute when player has no cards."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 1, 0, bird_id)
        spot = state.players[1].board[1][0]

        state.players[1].bird_hand = []

        power_entry = create_power_18_entry(1, bird_id, spot, "grassland", "card")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is False

    def test_power_18_validation_card_with_cards(self):
        """Power 18 (card variant) can execute when player has cards."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 1, 0, bird_id)
        spot = state.players[1].board[1][0]

        # bird_hand now contains IDs
        all_bird_ids = list(BIRD_REGISTRY.keys())
        state.players[1].bird_hand = [all_bird_ids[1]]

        power_entry = create_power_18_entry(1, bird_id, spot, "grassland", "card")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_18_validation_food_always_valid(self):
        """Power 18 (food variants) are always valid."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]

        power_entry = create_power_18_entry(1, bird_id, spot, "forest", "invertebrate")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True


class TestPower18MultiPlayer:
    """Tests for Power 18 in multi-player scenarios."""

    def test_power_18_multiple_opponents_trigger(self):
        """Multiple opponents with Power 18 for same habitat all trigger."""
        state = GameState()
        state.players = [Player(1), Player(2), Player(3)]

        all_bird_ids = list(BIRD_REGISTRY.keys())
        bird_id_1 = all_bird_ids[0]
        bird_id_2 = all_bird_ids[1]

        place_bird_on_board(state, 1, 0, 0, bird_id_1)
        place_bird_on_board(state, 2, 0, 0, bird_id_2)

        from unittest.mock import patch

        def mock_get_power(bird_id):
            if bird_id in [bird_id_1, bird_id_2]:
                return {
                    "color": "pink",
                    "data": {
                        "id": 18,
                        "details": {"habitat": "forest", "resource": "invertebrate"},
                    },
                }
            return {}

        with patch("game.utils.get_bird_power", side_effect=mock_get_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 2
        player_indices = {t["player_index"] for t in triggered}
        assert player_indices == {1, 2}
