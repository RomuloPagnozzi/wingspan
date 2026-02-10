"""Tests for Power 19: Pink power triggered when opponent gains rodent."""

from game.core import (
    GameState,
    GamePhase,
    Player,
    Spot,
    PinkTrigger,
    BIRD_REGISTRY,
    SimpleAction,
)
from game.engine import transition_state
from game.actions import get_actions
from game.utils import get_triggered_pink_powers
from game.power import can_execute_power
from conftest import place_bird_on_board, setup_power_execution


def get_any_bird_id() -> int:
    """Get any valid bird ID from the registry."""
    return next(iter(BIRD_REGISTRY.keys()))


def create_power_19_entry(player_index: int, bird_id: int, spot: Spot) -> dict:
    """Create a power entry for Power 19."""
    return {
        "player_index": player_index,
        "bird_id": bird_id,
        "power_id": 19,
        "power_data": {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        },
        "spot": spot,
    }


class TestPower19Execution:
    """Tests for Power 19 executor."""

    def test_power_19_caches_food_on_bird(self):
        """When activated, the activating bird's stashed_food increments by 1."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]
        assert spot.bird
        initial_stashed = spot.bird.state.stashed_food

        setup_power_execution(state, 19, bird_id, spot, 1)
        state.current_player_index = 1

        state = transition_state(state, SimpleAction("activate_power"))
        assert state.players[1].board[0][0].bird
        assert (
            state.players[1].board[0][0].bird.state.stashed_food == initial_stashed + 1
        )


class TestPower19TriggerMatching:
    """Tests for Power 19 trigger matching logic."""

    def test_power_19_triggers_on_rodent_gain(self):
        """Power 19 triggers when opponent gains rodent."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "rodent"},
            )

        assert len(triggered) == 1
        assert triggered[0]["player_index"] == 1
        assert triggered[0]["bird_id"] == bird_id

    def test_power_19_no_trigger_on_invertebrate(self):
        """Power 19 does NOT trigger when opponent gains invertebrate."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "invertebrate"},
            )

        assert len(triggered) == 0

    def test_power_19_no_trigger_on_seed(self):
        """Power 19 does NOT trigger when opponent gains seed."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "seed"},
            )

        assert len(triggered) == 0

    def test_power_19_no_trigger_own_action(self):
        """Power 19 does NOT trigger on player's own rodent gain."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 0, 0, 0, bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "rodent"},
            )

        assert len(triggered) == 0

    def test_power_19_already_used_no_trigger(self):
        """Power 19 does NOT trigger if already used this rotation."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        state.players[1].used_pink_powers.add(bird_id)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 19, "details": {"type": "rodent"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "rodent"},
            )

        assert len(triggered) == 0


class TestPower19Validation:
    """Tests for Power 19 validation."""

    def test_power_19_always_valid(self):
        """Power 19 can always be activated (caches from supply)."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]

        power_entry = create_power_19_entry(1, bird_id, spot)

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_19_skip_power(self):
        """Player can choose to skip activating Power 19."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird_id = get_any_bird_id()
        place_bird_on_board(state, 1, 0, 0, bird_id)
        spot = state.players[1].board[0][0]
        assert spot.bird
        initial_stashed = spot.bird.state.stashed_food

        setup_power_execution(state, 19, bird_id, spot, 1)
        state.current_player_index = 1

        actions = get_actions(state)
        assert SimpleAction("skip_power") in actions

        state = transition_state(state, SimpleAction("skip_power"))
        assert state.players[1].board[0][0].bird
        assert state.players[1].board[0][0].bird.state.stashed_food == initial_stashed
