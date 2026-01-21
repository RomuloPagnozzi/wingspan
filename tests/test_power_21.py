"""Tests for Power 21: Pink power triggered when opponent's predator succeeds."""

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


def create_power_21_entry(player_index: int, bird_id: int, spot: Spot) -> dict:
    """Create a power entry for Power 21."""
    return {
        "player_index": player_index,
        "bird_id": bird_id,
        "power_id": 21,
        "power_data": {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        },
        "spot": spot,
    }


def setup_power_21_execution(state, player_index, bird_id, spot):
    """Set up Power 21 execution with new ActionData structure."""
    power_data = {
        "color": "pink",
        "data": {"id": 21, "details": {"resource": "die"}},
    }
    state.action_data = ActionData()
    state.action_data.powers_queue = [
        QueuedPower(
            power_id=21,
            bird_id=bird_id,
            spot_row=spot.row,
            spot_col=spot.col,
            player_index=player_index,
            power_data=power_data,
        )
    ]
    state.action_data.current_power_index = 0


class TestPower21Execution:
    """Tests for Power 21 executor."""

    def test_power_21_enters_sub_phase_for_die_selection(self):
        """Power 21 enters sub_phase for die selection."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        state = transition_state(state, "activate_power")

        # Should be in select_die phase
        assert len(state.action_data.execution_stack) == 1
        assert state.action_data.execution_stack[0].phase == "select_die"

    def test_power_21_generates_die_selection_actions(self):
        """Action generator produces select_die actions for each die in feeder."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        # Set up feeder with specific dice
        state.feeder = {
            0: {"invertebrate", "seed"},
            1: {"fish"},
            2: {"rodent", "fruit"},
        }

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        # Activate to enter select_die phase
        state = transition_state(state, "activate_power")

        actions = get_actions(state)

        # Should have actions for each food type on each die
        assert "select_die_0_invertebrate" in actions
        assert "select_die_0_seed" in actions
        assert "select_die_1_fish" in actions
        assert "select_die_2_rodent" in actions
        assert "select_die_2_fruit" in actions

    def test_power_21_select_die_gains_food(self):
        """Selecting a die removes it from feeder and gains food."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        state.feeder = {
            0: {"invertebrate"},
            1: {"fish"},
        }

        initial_invertebrate = state.players[1].food.get("invertebrate", 0)

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        # Activate then select die
        state = transition_state(state, "activate_power")
        state = transition_state(state, "select_die_0_invertebrate")

        assert state.players[1].food.get("invertebrate", 0) == initial_invertebrate + 1
        assert 0 not in state.feeder  # Die was removed

    def test_power_21_reroll_all_option(self):
        """Player can reroll all dice when all show same face."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        # All dice show same food type
        state.feeder = {
            0: {"fish"},
            1: {"fish"},
            2: {"fish"},
            3: {"fish"},
            4: {"fish"},
        }

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        # Activate to enter select_die phase
        state = transition_state(state, "activate_power")

        actions = get_actions(state)
        assert "reroll_all" in actions

    def test_power_21_reroll_all_rerolls_feeder(self):
        """Reroll all action rerolls the feeder but stays in sub_phase."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        # All dice show same food type
        state.feeder = {
            0: {"fish"},
            1: {"fish"},
            2: {"fish"},
            3: {"fish"},
            4: {"fish"},
        }

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        # Activate to enter select_die phase
        state = transition_state(state, "activate_power")
        state = transition_state(state, "reroll_all")

        # Should still be in select_die phase, feeder has been rerolled
        assert len(state.action_data.execution_stack) == 1
        assert state.action_data.execution_stack[0].phase == "select_die"
        assert len(state.feeder) == 5


class TestPower21TriggerMatching:
    """Tests for Power 21 trigger matching logic."""

    def test_power_21_triggers_on_predator_success(self):
        """Power 21 triggers when opponent's predator succeeds."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.PREDATOR_SUCCESS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 1
        assert triggered[0]["player_index"] == 1
        assert triggered[0]["bird_id"] == 100

    def test_power_21_no_trigger_on_lay_eggs(self):
        """Power 21 does NOT trigger on lay eggs action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.LAY_EGGS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 0

    def test_power_21_no_trigger_on_bird_played(self):
        """Power 21 does NOT trigger on bird played action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.BIRD_PLAYED,
                triggering_player_index=0,
                context={"habitat": "forest"},
            )

        assert len(triggered) == 0

    def test_power_21_no_trigger_on_gain_food(self):
        """Power 21 does NOT trigger on gain food action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.GAIN_FOOD,
                triggering_player_index=0,
                context={"food_type": "rodent"},
            )

        assert len(triggered) == 0

    def test_power_21_no_trigger_own_predator(self):
        """Power 21 does NOT trigger on player's own predator success."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[0].board[0][0].bird = bird

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.PREDATOR_SUCCESS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 0

    def test_power_21_already_used_no_trigger(self):
        """Power 21 does NOT trigger if already used this rotation."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        state.players[1].used_pink_powers.add(100)

        from unittest.mock import patch

        mock_power = {
            "color": "pink",
            "data": {"id": 21, "details": {"resource": "die"}},
        }

        with patch("game.utils.get_bird_power", return_value=mock_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.PREDATOR_SUCCESS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 0


class TestPower21Validation:
    """Tests for Power 21 validation."""

    def test_power_21_always_valid(self):
        """Power 21 is always valid (feeder auto-refills)."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        power_entry = create_power_21_entry(1, 100, spot)

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_21_skip_power(self):
        """Player can choose to skip activating Power 21."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        bird = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird
        spot = state.players[1].board[0][0]

        initial_food = dict(state.players[1].food)

        setup_power_21_execution(state, 1, 100, spot)
        state.current_player_index = 1

        actions = get_actions(state)
        assert "skip_power" in actions

        state = transition_state(state, "skip_power")

        assert state.players[1].food == initial_food


class TestPower21MultiPlayer:
    """Tests for Power 21 in multi-player scenarios."""

    def test_power_21_multiple_opponents_trigger(self):
        """Multiple opponents with Power 21 all trigger on predator success."""
        state = GameState()
        state.players = [Player(1), Player(2), Player(3)]

        bird1 = create_test_bird(100, ["forest"])
        state.players[1].board[0][0].bird = bird1

        bird2 = create_test_bird(101, ["forest"])
        state.players[2].board[0][0].bird = bird2

        from unittest.mock import patch

        def mock_get_power(bird_id):
            if bird_id in [100, 101]:
                return {
                    "color": "pink",
                    "data": {"id": 21, "details": {"resource": "die"}},
                }
            return {}

        with patch("game.utils.get_bird_power", side_effect=mock_get_power):
            triggered = get_triggered_pink_powers(
                state,
                PinkTrigger.PREDATOR_SUCCESS,
                triggering_player_index=0,
                context={},
            )

        assert len(triggered) == 2
        player_indices = {t["player_index"] for t in triggered}
        assert player_indices == {1, 2}
