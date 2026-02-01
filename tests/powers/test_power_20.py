"""Tests for Power 20: Pink power triggered when opponent lays eggs."""

from game.core import (
    GameState,
    GamePhase,
    Player,
    PlacedBird,
    BirdState,
    Spot,
    PinkTrigger,
    BIRD_REGISTRY,
)
from game.engine import transition_state
from game.actions import get_actions
from conftest import setup_power_execution
from game.utils import get_triggered_pink_powers
from game.power import can_execute_power


def find_bird_by_nest(nest_type: str, exclude_ids: set = set()) -> int:
    """Find a bird ID with the specified nest type."""
    exclude_ids = exclude_ids or set()
    for bird_id, card in BIRD_REGISTRY.items():
        if card.nest == nest_type and bird_id not in exclude_ids:
            return bird_id
    raise ValueError(f"No bird with nest type {nest_type}")


def create_placed_bird(bird_id: int, eggs: int = 0) -> PlacedBird:
    """Create a PlacedBird for placing on board."""
    return PlacedBird(card_id=bird_id, state=BirdState(eggs=eggs))


def create_power_20_data(nest_type: str) -> dict:
    """Create power_data dict for Power 20."""
    return {
        "color": "pink",
        "data": {"id": 20, "details": {"type": nest_type}},
    }


def create_power_20_entry(
    player_index: int, bird_id: int, spot: Spot, nest_type: str
) -> dict:
    """Create a power entry for Power 20."""
    return {
        "player_index": player_index,
        "bird_id": bird_id,
        "power_id": 20,
        "power_data": create_power_20_data(nest_type),
        "spot": spot,
    }


class TestPower20SingleBird:
    """Tests for Power 20 when there's only one valid bird."""

    def test_power_20_single_valid_bird_lays_egg(self):
        """When only one valid bird exists, egg is laid automatically."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (cavity nest, not bowl)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird that can receive eggs
        bowl_bird_id = find_bird_by_nest("bowl")
        bowl_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[1][0].bird = bowl_bird

        initial_eggs = state.players[1].board[1][0].bird.state.eggs

        setup_power_execution(
            state, 20, cavity_bird_id, spot, 1, create_power_20_data("bowl")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs + 1


class TestPower20MultipleBirds:
    """Tests for Power 20 when multiple valid birds exist."""

    def test_power_20_multiple_birds_enters_sub_phase(self):
        """When multiple valid birds exist, enters sub_phase for selection."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (cavity nest, not bowl)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird_id_1 = find_bird_by_nest("bowl")
        bowl_bird_id_2 = find_bird_by_nest("bowl", exclude_ids={bowl_bird_id_1})
        bowl_bird1 = create_placed_bird(bowl_bird_id_1)
        bowl_bird2 = create_placed_bird(bowl_bird_id_2)
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        setup_power_execution(
            state, 20, cavity_bird_id, spot, 1, create_power_20_data("bowl")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")

        # Should be in select_bird phase
        assert len(state.action_data.execution_stack) == 1
        assert state.action_data.execution_stack[0].phase == "select_bird"

    def test_power_20_generates_select_bird_actions(self):
        """Action generator produces select_bird actions for each valid bird."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use cavity so it doesn't match bowl)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird_id_1 = find_bird_by_nest("bowl")
        bowl_bird_id_2 = find_bird_by_nest("bowl", exclude_ids={bowl_bird_id_1})
        bowl_bird1 = create_placed_bird(bowl_bird_id_1)
        bowl_bird2 = create_placed_bird(bowl_bird_id_2)
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        setup_power_execution(
            state, 20, cavity_bird_id, spot, 1, create_power_20_data("bowl")
        )
        state.current_player_index = 1

        # Activate to enter select_bird phase
        state = transition_state(state, "activate_power")

        actions = get_actions(state)

        assert f"select_bird_{bowl_bird_id_1}" in actions
        assert f"select_bird_{bowl_bird_id_2}" in actions
        assert len(actions) == 2

    def test_power_20_select_bird_lays_egg(self):
        """Selecting a bird lays an egg on that bird."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use cavity so it doesn't match bowl)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Two bowl nest birds
        bowl_bird_id_1 = find_bird_by_nest("bowl")
        bowl_bird_id_2 = find_bird_by_nest("bowl", exclude_ids={bowl_bird_id_1})
        bowl_bird1 = create_placed_bird(bowl_bird_id_1)
        bowl_bird2 = create_placed_bird(bowl_bird_id_2)
        state.players[1].board[1][0].bird = bowl_bird1
        state.players[1].board[1][1].bird = bowl_bird2

        initial_eggs_1 = state.players[1].board[1][0].bird.state.eggs
        initial_eggs_2 = state.players[1].board[1][1].bird.state.eggs

        setup_power_execution(
            state, 20, cavity_bird_id, spot, 1, create_power_20_data("bowl")
        )
        state.current_player_index = 1

        # Activate then select bird
        state = transition_state(state, "activate_power")
        state = transition_state(state, f"select_bird_{bowl_bird_id_1}")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][1].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs_1 + 1
        assert state.players[1].board[1][1].bird.state.eggs == initial_eggs_2


class TestPower20TriggerMatching:
    """Tests for Power 20 trigger matching logic."""

    def test_power_20_triggers_on_lay_eggs(self):
        """Power 20 triggers when opponent takes lay eggs action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Use a real bird ID for the placed bird
        bird_id = find_bird_by_nest("bowl")
        bird = create_placed_bird(bird_id)
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
        assert triggered[0]["bird_id"] == bird_id

    def test_power_20_no_trigger_on_gain_food(self):
        """Power 20 does NOT trigger on gain food action."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        bird_id = find_bird_by_nest("bowl")
        bird = create_placed_bird(bird_id)
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

        bird_id = find_bird_by_nest("bowl")
        bird = create_placed_bird(bird_id)
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

        bird_id = find_bird_by_nest("bowl")
        bird = create_placed_bird(bird_id)
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

        bird_id = find_bird_by_nest("bowl")
        bird = create_placed_bird(bird_id)
        state.players[1].board[0][0].bird = bird
        state.players[1].used_pink_powers.add(bird_id)

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

        # Pink power bird (use cavity)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird with capacity
        bowl_bird_id = find_bird_by_nest("bowl")
        bowl_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[1][0].bird = bowl_bird

        power_entry = create_power_20_entry(1, cavity_bird_id, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is True

    def test_power_20_invalid_no_matching_nest(self):
        """Power 20 is invalid when player has no bird with matching nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird (ground nest)
        ground_bird_id = find_bird_by_nest("ground")
        pink_bird = create_placed_bird(ground_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Cavity nest bird (not bowl)
        cavity_bird_id = find_bird_by_nest("cavity")
        cavity_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[1][0].bird = cavity_bird

        power_entry = create_power_20_entry(1, ground_bird_id, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is False

    def test_power_20_invalid_bird_at_egg_limit(self):
        """Power 20 is invalid when matching nest bird is at egg limit."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird (use cavity)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird at egg limit
        bowl_bird_id = find_bird_by_nest("bowl")
        egg_limit = BIRD_REGISTRY[bowl_bird_id].egg_limit
        bowl_bird = create_placed_bird(bowl_bird_id, eggs=egg_limit)  # At capacity
        state.players[1].board[1][0].bird = bowl_bird

        power_entry = create_power_20_entry(1, cavity_bird_id, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        assert can_execute is False

    def test_power_20_invalid_only_pink_bird_has_nest_type(self):
        """Power 20 is invalid when only the pink power bird itself has the matching nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]

        # Pink power bird with bowl nest - same type as power targets
        bowl_bird_id = find_bird_by_nest("bowl")
        pink_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # No other bowl nest birds
        power_entry = create_power_20_entry(1, bowl_bird_id, spot, "bowl")

        can_execute = can_execute_power(state, power_entry)

        # Should be False because we exclude the pink bird itself from targets
        assert can_execute is False

    def test_power_20_skip_power(self):
        """Player can choose to skip activating Power 20."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use cavity)
        cavity_bird_id = find_bird_by_nest("cavity")
        pink_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        # Bowl nest bird
        bowl_bird_id = find_bird_by_nest("bowl")
        bowl_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[1][0].bird = bowl_bird

        initial_eggs = state.players[1].board[1][0].bird.state.eggs

        setup_power_execution(
            state, 20, cavity_bird_id, spot, 1, create_power_20_data("bowl")
        )
        state.current_player_index = 1

        actions = get_actions(state)
        assert "skip_power" in actions

        state = transition_state(state, "skip_power")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs


class TestPower20NestTypes:
    """Tests for Power 20 with different nest types."""

    def test_power_20_cavity_nest(self):
        """Power 20 works correctly with cavity nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use bowl so it doesn't match cavity)
        bowl_bird_id = find_bird_by_nest("bowl")
        pink_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        cavity_bird_id = find_bird_by_nest("cavity")
        cavity_bird = create_placed_bird(cavity_bird_id)
        state.players[1].board[1][0].bird = cavity_bird

        initial_eggs = state.players[1].board[1][0].bird.state.eggs

        setup_power_execution(
            state, 20, bowl_bird_id, spot, 1, create_power_20_data("cavity")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs + 1

    def test_power_20_ground_nest(self):
        """Power 20 works correctly with ground nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use bowl so it doesn't match ground)
        bowl_bird_id = find_bird_by_nest("bowl")
        pink_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        ground_bird_id = find_bird_by_nest("ground")
        ground_bird = create_placed_bird(ground_bird_id)
        state.players[1].board[1][0].bird = ground_bird

        initial_eggs = state.players[1].board[1][0].bird.state.eggs

        setup_power_execution(
            state, 20, bowl_bird_id, spot, 1, create_power_20_data("ground")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs + 1

    def test_power_20_platform_nest(self):
        """Power 20 works correctly with platform nest type."""
        state = GameState()
        state.players = [Player(1), Player(2)]
        state.players[0].first_player = True
        state.game_phase = GamePhase.ACTIVATE_POWERS

        # Pink power bird (use bowl so it doesn't match platform)
        bowl_bird_id = find_bird_by_nest("bowl")
        pink_bird = create_placed_bird(bowl_bird_id)
        state.players[1].board[0][0].bird = pink_bird
        spot = state.players[1].board[0][0]

        platform_bird_id = find_bird_by_nest("platform")
        platform_bird = create_placed_bird(platform_bird_id)
        state.players[1].board[1][0].bird = platform_bird

        initial_eggs = state.players[1].board[1][0].bird.state.eggs

        setup_power_execution(
            state, 20, bowl_bird_id, spot, 1, create_power_20_data("platform")
        )
        state.current_player_index = 1

        state = transition_state(state, "activate_power")
        assert state.players[1].board[1][0].bird
        assert state.players[1].board[1][0].bird.state.eggs == initial_eggs + 1
