"""Tests for Power 20: Pink power triggered when opponent lays eggs."""

import pytest
from game.data import GameState, GamePhase, Player, Bird, Spot, PinkTrigger
from game.engine import transition_state, _execute_power_20
from game.actions import get_actions
from game.utils import get_triggered_pink_powers
from game.powers import can_execute_power


def create_test_bird(bird_id: int, habitats: list, nest: str = "bowl") -> Bird:
    """Create a test bird with minimal required attributes."""
    bird = Bird(
        id=bird_id,
        name=f"Test Bird {bird_id}",
        habitats=habitats,
        cost=[],
        points=1,
        nest=nest,
        egg_limit=2,
        wingspan=50,
    )
    return bird


def create_power_20_entry(
    player_index: int, bird_id: int, spot: Spot, nest_type: str
) -> dict:
    """Create a power entry for Power 20."""
    return {
        "player_index": player_index,
        "bird_id": bird_id,
        "power_id": 20,
        "power_data": {
            "color": "pink",
            "data": {"id": 20, "details": {"type": nest_type}},
        },
        "spot": spot,
    }


class TestPower20SingleBird:
    """Tests for Power 20 when there's only one valid bird."""

    def test_power_20_single_valid_bird_lays_egg(self):
        """When only one valid bird exists, egg is laid automatically."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (cavity nest, not bowl)
        pink_bird = create_test_bird(100, ["forest"], nest="cavity")
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird that can receive eggs
        bowl_bird = create_test_bird(200, ["grassland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird

        initial_eggs = state.players[1].board[1][0].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "bowl")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        state = _execute_power_20(state, power_entry)

        assert state.players[1].board[1][0].bird.eggs == initial_eggs + 1
        assert state.action_data.get("sub_phase") is None


class TestPower20MultipleBirds:
    """Tests for Power 20 when multiple valid birds exist."""

    def test_power_20_multiple_birds_enters_sub_phase(self):
        """When multiple valid birds exist, enters sub_phase for selection."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (cavity nest, not bowl)
        pink_bird = create_test_bird(100, ["forest"], nest="cavity")
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird1 = create_test_bird(200, ["grassland"], nest="bowl")
        bowl_bird2 = create_test_bird(201, ["wetland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        power_entry = create_power_20_entry(1, 100, spot, "bowl")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        state = _execute_power_20(state, power_entry)

        assert state.action_data.get("sub_phase") == "power_20_select_bird"
        assert set(state.action_data.get("power_20_valid_bird_ids")) == {200, 201}

    def test_power_20_generates_select_bird_actions(self):
        """Action generator produces select_bird actions for each valid bird."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird1 = create_test_bird(200, ["grassland"], nest="bowl")
        bowl_bird2 = create_test_bird(201, ["wetland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        power_entry = create_power_20_entry(1, 100, spot, "bowl")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
            "sub_phase": "power_20_select_bird",
            "power_20_valid_bird_ids": [200, 201],
            "power_20_player_index": 1,
        }
        state.current_player_index = 1

        actions = get_actions(state)

        assert "select_bird_200" in actions
        assert "select_bird_201" in actions
        assert len(actions) == 2

    def test_power_20_select_bird_lays_egg(self):
        """Selecting a bird lays an egg on that bird."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird1 = create_test_bird(200, ["grassland"], nest="bowl")
        bowl_bird2 = create_test_bird(201, ["wetland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        initial_eggs_200 = state.players[1].board[1][0].bird.eggs
        initial_eggs_201 = state.players[1].board[1][1].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "bowl")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
            "sub_phase": "power_20_select_bird",
            "power_20_valid_bird_ids": [200, 201],
            "power_20_player_index": 1,
        }
        state.current_player_index = 1

        state = transition_state(state, "select_bird_200")

        assert state.players[1].board[1][0].bird.eggs == initial_eggs_200 + 1
        assert state.players[1].board[1][1].bird.eggs == initial_eggs_201
        assert state.action_data.get("sub_phase") is None


class TestPower20TriggerMatching:
    """Tests for Power 20 trigger matching logic."""

    def test_power_20_triggers_on_lay_eggs(self):
        """Power 20 triggers when opponent takes lay eggs action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 20, "details": {"type": "bowl"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.LAY_EGGS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 1
        assert triggered[0]["player_index"] == 1
        assert triggered[0]["bird_id"] == 100

    def test_power_20_no_trigger_on_gain_food(self):
        """Power 20 does NOT trigger on gain food action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 20, "details": {"type": "bowl"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "rodent"},
            )

        assert len(triggered) == 0

    def test_power_20_no_trigger_on_bird_played(self):
        """Power 20 does NOT trigger on bird played action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 20, "details": {"type": "bowl"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 0

    def test_power_20_no_trigger_own_action(self):
        """Power 20 does NOT trigger on player's own lay eggs action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[0].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 20, "details": {"type": "bowl"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.LAY_EGGS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 0

    def test_power_20_already_used_no_trigger(self):
        """Power 20 does NOT trigger if already used this rotation."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        state.players[1].used_pink_powers.add(100)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 20, "details": {"type": "bowl"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.LAY_EGGS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 0


class TestPower20Validation:
    """Tests for Power 20 validation."""

    def test_power_20_valid_with_matching_nest_bird(self):
        """Power 20 is valid when player has a bird with matching nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird with capacity
        bowl_bird = create_test_bird(200, ["grassland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird

        power_entry = create_power_20_entry(1, 100, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_20_invalid_no_matching_nest(self):
        """Power 20 is invalid when player has no bird with matching nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Cavity nest bird (not bowl)
        cavity_bird = create_test_bird(200, ["grassland"], nest="cavity")
        state.players[1].board[1][0].bird = cavity_bird

        power_entry = create_power_20_entry(1, 100, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is False

    def test_power_20_invalid_bird_at_egg_limit(self):
        """Power 20 is invalid when matching nest bird is at egg limit."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird at egg limit
        bowl_bird = create_test_bird(200, ["grassland"], nest="bowl")
        bowl_bird.eggs = bowl_bird.egg_limit  # At capacity
        state.players[1].board[1][0].bird = bowl_bird

        power_entry = create_power_20_entry(1, 100, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is False

    def test_power_20_invalid_only_pink_bird_has_nest_type(self):
        """Power 20 is invalid when only the pink power bird itself has the matching nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird with bowl nest - same type as power targets
        pink_bird = create_test_bird(100, ["forest"], nest="bowl")
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # No other bowl nest birds
        power_entry = create_power_20_entry(1, 100, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        # Should be False because we exclude the pink bird itself from targets
        assert can_execute is False

    def test_power_20_skip_power(self):
        """Player can choose to skip activating Power 20."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird
        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird
        bowl_bird = create_test_bird(200, ["grassland"], nest="bowl")
        state.players[1].board[1][0].bird = bowl_bird

        initial_eggs = state.players[1].board[1][0].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "bowl")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        actions = get_actions(state)
        assert "skip_power" in actions

        state = transition_state(state, "skip_power")

        assert state.players[1].board[1][0].bird.eggs == initial_eggs


class TestPower20NestTypes:
    """Tests for Power 20 with different nest types."""

    def test_power_20_cavity_nest(self):
        """Power 20 works correctly with cavity nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        cavity_bird = create_test_bird(200, ["grassland"], nest="cavity")
        state.players[1].board[1][0].bird = cavity_bird

        initial_eggs = state.players[1].board[1][0].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "cavity")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        state = _execute_power_20(state, power_entry)

        assert state.players[1].board[1][0].bird.eggs == initial_eggs + 1

    def test_power_20_ground_nest(self):
        """Power 20 works correctly with ground nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        ground_bird = create_test_bird(200, ["grassland"], nest="ground")
        state.players[1].board[1][0].bird = ground_bird

        initial_eggs = state.players[1].board[1][0].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "ground")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        state = _execute_power_20(state, power_entry)

        assert state.players[1].board[1][0].bird.eggs == initial_eggs + 1

    def test_power_20_platform_nest(self):
        """Power 20 works correctly with platform nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        pink_bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        platform_bird = create_test_bird(200, ["grassland"], nest="platform")
        state.players[1].board[1][0].bird = platform_bird

        initial_eggs = state.players[1].board[1][0].bird.eggs

        power_entry = create_power_20_entry(1, 100, spot, "platform")
        state.action_data = {
            "powers_queue": [power_entry],
            "current_power_index": 0,
            "action_player_index": 0,
        }
        state.current_player_index = 1

        state = _execute_power_20(state, power_entry)

        assert state.players[1].board[1][0].bird.eggs == initial_eggs + 1
