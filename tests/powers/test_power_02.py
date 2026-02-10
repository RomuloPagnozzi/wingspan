"""Tests for Power 2: All players lay eggs on matching nest types."""

from game.core import initiate_state, GamePhase, SimpleAction, EggMapAction, frozen_map
from game.engine import transition_state
from game.actions import get_actions
from conftest import (
    get_registry_bird_ids_by_nest,
    place_bird_on_board,
    setup_power_queue,
)


def test_power_2_sets_up_multi_player():
    """Power type 2 sets up multi-player state for sequential choices."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find birds with bowl nest from registry
    bowl_bird_ids = get_registry_bird_ids_by_nest("bowl")
    assert len(bowl_bird_ids) >= 2, "Need at least 2 bowl nest birds in registry"

    # Give both players bowl nest birds with egg capacity
    bird_id0 = bowl_bird_ids[0]
    bird_id1 = bowl_bird_ids[1]
    place_bird_on_board(state, 0, 0, 0, bird_id0)
    place_bird_on_board(state, 1, 0, 0, bird_id1)

    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
    )

    state = transition_state(state, SimpleAction("activate_power"))

    # Stack-based: check execution stack
    assert len(state.action_data.execution_stack) == 1
    assert state.action_data.execution_stack[0].phase == "choices"
    ctx = state.action_data.execution_stack[0].context
    assert ctx["activator"] == 0
    assert ctx["awaiting_players"] == [0, 1]
    assert ctx["nest_type"] == "bowl"
    assert state.current_player_index == 0  # Activator goes first


def test_multi_player_actions_generated():
    """Multi-player power generates correct choice actions."""
    state = initiate_state(2)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find a bird with bowl nest from registry
    bowl_bird_ids = get_registry_bird_ids_by_nest("bowl")
    assert len(bowl_bird_ids) >= 1, "Need at least 1 bowl nest bird in registry"

    bird_id = bowl_bird_ids[0]
    place_bird_on_board(state, 0, 0, 0, bird_id)

    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
    )

    # Activate to enter choices phase
    state = transition_state(state, SimpleAction("activate_power"))

    actions = get_actions(state)

    assert len(actions) > 0
    assert all(isinstance(a, EggMapAction) for a in actions)


def test_power_2_all_players_lay_eggs_end_to_end():
    """End-to-end test: Power 2 allows all players to lay 1 egg on matching nest types."""
    for num_players in [2, 3, 4, 5]:
        for nest_type in ["bowl", "cavity", "ground", "platform"]:
            state = initiate_state(num_players)
            state.game_phase = GamePhase.ACTIVATE_POWERS
            state.current_player_index = 0

            # Find birds with matching nest type from registry
            nest_bird_ids = get_registry_bird_ids_by_nest(nest_type)
            if len(nest_bird_ids) < num_players:
                continue  # Skip if not enough birds of this nest type

            # Give each player a bird with the matching nest type
            placed_bird_ids = []
            for i, player in enumerate(state.players):
                bird_id = nest_bird_ids[i]
                place_bird_on_board(state, i, 0, 0, bird_id)
                placed_bird_ids.append(bird_id)

            setup_power_queue(
                state,
                [
                    {
                        "bird_id": 1,
                        "power_data": {
                            "data": {"id": 2, "details": {"type": nest_type}}
                        },
                    }
                ],
            )

            # Activate the power (sets up multi-player state)
            state = transition_state(state, SimpleAction("activate_power"))

            # Each player makes their egg-laying choice
            while state.game_phase == GamePhase.ACTIVATE_POWERS:
                current_player = state.current_player_index
                bird_id = placed_bird_ids[current_player]

                # Have each player lay 1 egg on their bird
                action = EggMapAction("activate_eggs", frozen_map({bird_id: 1}))
                state = transition_state(state, action)

            # Verify all players laid exactly 1 egg
            for i, player in enumerate(state.players):
                assert player.board[0][0].bird
                assert player.board[0][0].bird.state.eggs == 1, (
                    f"Player {i} in {num_players}-player game with {nest_type} nest "
                    "should have laid exactly 1 egg"
                )

            # Verify we're back to main turn
            assert state.game_phase == GamePhase.MAIN_TURN


def test_power_2_with_mixed_eligibility():
    """Test power 2 when only some players have matching nest types."""
    state = initiate_state(4)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0

    # Find birds with bowl and cavity nests from registry
    bowl_bird_ids = get_registry_bird_ids_by_nest("bowl")
    cavity_bird_ids = get_registry_bird_ids_by_nest("cavity")
    assert len(bowl_bird_ids) >= 2 and len(cavity_bird_ids) >= 2

    # Players 0 and 2 have bowl nests, players 1 and 3 have cavity nests
    placed_bowl_ids = []
    for idx, i in enumerate([0, 2]):
        bird_id = bowl_bird_ids[idx]
        place_bird_on_board(state, i, 0, 0, bird_id)
        placed_bowl_ids.append(bird_id)

    for idx, i in enumerate([1, 3]):
        bird_id = cavity_bird_ids[idx]
        place_bird_on_board(state, i, 0, 0, bird_id)

    # Activate power 2 for bowl nests
    setup_power_queue(
        state,
        [
            {
                "bird_id": 1,
                "power_data": {"data": {"id": 2, "details": {"type": "bowl"}}},
            }
        ],
    )

    state = transition_state(state, SimpleAction("activate_power"))

    # Only players 0 and 2 should be in awaiting list (in execution stack context)
    ctx = state.action_data.execution_stack[0].context
    assert set(ctx["awaiting_players"]) == {0, 2}

    # Players 0 and 2 make their choices
    for player_index, bird_id in zip([0, 2], placed_bowl_ids):
        assert state.current_player_index == player_index
        action = EggMapAction("activate_eggs", frozen_map({bird_id: 1}))
        state = transition_state(state, action)

    # Verify only players 0 and 2 laid eggs
    assert state.players[0].board[0][0].bird
    assert state.players[2].board[0][0].bird
    assert state.players[0].board[0][0].bird.state.eggs == 1
    assert state.players[2].board[0][0].bird.state.eggs == 1

    # Players 1 and 3 should have no eggs (cavity nests don't match bowl power)
    assert state.players[1].board[0][0].bird
    assert state.players[3].board[0][0].bird
    assert state.players[1].board[0][0].bird.state.eggs == 0
    assert state.players[3].board[0][0].bird.state.eggs == 0

    # Verify we're back to main turn
    assert state.game_phase == GamePhase.MAIN_TURN
