"""Tests for Power 19: Pink power triggered when opponent gains rodent."""

import sys

sys.path.append(".")

import pytest
from game.data import (
    GameState,
    GamePhase,
    Player,
    Bird,
    Spot,
    PinkTrigger,
    ActionData,
    QueuedPower,
)
from game.engine import transition_state
from game.actions import get_actions
from game.utils import get_triggered_pink_powers
from game.powers_validators import can_execute_power


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


def setup_power_19_execution(state, player_index, bird_id, spot):
    """Set up Power 19 execution with new ActionData structure."""
    power_data = {
        "color": "pink",
        "data": {"id": 19, "details": {"type": "rodent"}},
    }
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=19,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


class TestPower19Execution:
    """Tests for Power 19 executor."""

    def test_power_19_caches_food_on_bird(self):
        """When activated, the activating bird's stashed_food increments by 1."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        initial_stashed = spot.bird.stashed_food

        setup_power_19_execution(state, 1, 100, spot)
        state.current_player_index = 1

        state = transition_state(state, "activate_power")

        assert state.players[1].board[0][0].bird.stashed_food == initial_stashed + 1


class TestPower19TriggerMatching:
    """Tests for Power 19 trigger matching logic."""

    def test_power_19_triggers_on_rodent_gain(self):
        """Power 19 triggers when opponent gains rodent."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

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
        assert triggered[0]["bird_id"] == 100

    def test_power_19_no_trigger_on_invertebrate(self):
        """Power 19 does NOT trigger when opponent gains invertebrate."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

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

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

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

        bird = create_test_bird(100, ["forest"])
        state.players[0].board[0][0].bird = bird

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

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        state.players[1].used_pink_powers.add(100)

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

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        power_entry = create_power_19_entry(1, 100, spot)

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_19_skip_power(self):
        """Player can choose to skip activating Power 19."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        initial_stashed = spot.bird.stashed_food

        setup_power_19_execution(state, 1, 100, spot)
        state.current_player_index = 1

        actions = get_actions(state)
        assert "skip_power" in actions

        state = transition_state(state, "skip_power")

        assert state.players[1].board[0][0].bird.stashed_food == initial_stashed
