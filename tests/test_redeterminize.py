"""Tests for redeterminize(): perspective-player invariants, card conservation,
randomization across seeds, and mid-power-execution context handling."""

import random

from game.core import (
    BIRD_REGISTRY,
    BONUS_REGISTRY,
    PowerExecution,
    initiate_state,
    redeterminize,
)
from conftest import place_bird_on_board


def _all_bird_locations(state, perspective: int) -> list[int]:
    """Sum all currently-tracked bird IDs across every location.

    Tucked-card slots are intentionally not counted here — those IDs are lost.
    """
    ids: list[int] = []
    ids += list(state.bird_tray)
    ids += list(state.discarded_birds)
    ids += list(state.bird_deck)
    for p in state.players:
        ids += list(p.bird_hand)
    for p in state.players:
        for row in p.board:
            for spot in row:
                if spot.bird is not None:
                    ids.append(spot.bird.id)
    for execution in state.action_data.execution_stack:
        for key in ("available_cards", "bonus_options"):
            value = execution.context.get(key)
            if value:
                ids += list(value)
    return ids


def _all_bonus_locations(state) -> list[int]:
    ids: list[int] = []
    ids += list(state.bonus_deck)
    ids += list(state.discarded_bonuses)
    for p in state.players:
        ids += list(p.bonus_hand)
    for execution in state.action_data.execution_stack:
        value = execution.context.get("bonus_options")
        if value:
            ids += list(value)
    return ids


def _tucked_total(state) -> int:
    return sum(
        spot.bird.state.tucked_cards
        for p in state.players
        for row in p.board
        for spot in row
        if spot.bird is not None
    )


# =============================================================================
# Perspective-player invariants
# =============================================================================


def test_perspective_player_preserved():
    """Perspective player's hand, board, food, score, action_cubes unchanged."""
    state = initiate_state(2, seed=42)
    rng = random.Random(123)

    perspective = 0
    p_before = state.players[perspective]
    bird_hand_before = list(p_before.bird_hand)
    bonus_hand_before = list(p_before.bonus_hand)
    food_before = dict(p_before.food)

    new_state = redeterminize(state, perspective, rng)

    p_after = new_state.players[perspective]
    assert p_after.bird_hand == bird_hand_before
    assert p_after.bonus_hand == bonus_hand_before
    assert p_after.food == food_before
    assert p_after.action_cubes == p_before.action_cubes
    assert p_after.first_player == p_before.first_player


def test_public_state_preserved():
    """Tray, discards, feeder, round_goal_config, phase, round preserved."""
    state = initiate_state(3, seed=7)
    state.discarded_birds.append(state.bird_deck.pop())
    state.discarded_bonuses.append(state.bonus_deck.pop())
    rng = random.Random(0)

    new_state = redeterminize(state, perspective_player=1, rng=rng)

    assert new_state.bird_tray == state.bird_tray
    assert new_state.discarded_birds == state.discarded_birds
    assert new_state.discarded_bonuses == state.discarded_bonuses
    assert new_state.feeder == state.feeder
    assert new_state.round_goal_config == state.round_goal_config
    assert new_state.game_phase == state.game_phase
    assert new_state.round == state.round
    assert new_state.current_player_index == state.current_player_index


def test_opponent_hand_sizes_preserved():
    state = initiate_state(3, seed=99)
    sizes_before = [len(p.bird_hand) for p in state.players]
    bonus_sizes_before = [len(p.bonus_hand) for p in state.players]

    new_state = redeterminize(state, perspective_player=0, rng=random.Random(1))

    assert [len(p.bird_hand) for p in new_state.players] == sizes_before
    assert [len(p.bonus_hand) for p in new_state.players] == bonus_sizes_before


# =============================================================================
# Conservation
# =============================================================================


def test_bird_conservation_fresh_game():
    """Fresh game has no lost cards; sum of all bird locations == |BIRD_REGISTRY|."""
    state = initiate_state(2, seed=5)
    new_state = redeterminize(state, perspective_player=0, rng=random.Random(0))

    locations = _all_bird_locations(new_state, perspective=0)
    assert len(locations) == len(
        set(locations)
    ), "duplicate bird IDs after redeterminize"
    assert sorted(locations) == sorted(BIRD_REGISTRY.keys())


def test_bonus_conservation_fresh_game():
    state = initiate_state(2, seed=5)
    new_state = redeterminize(state, perspective_player=0, rng=random.Random(0))

    locations = _all_bonus_locations(new_state)
    assert len(locations) == len(set(locations))
    assert sorted(locations) == sorted(BONUS_REGISTRY.keys())


def test_bird_conservation_with_tucked_cards():
    """Tucked cards are removed-from-game; conservation holds modulo tucked count."""
    state = initiate_state(2, seed=5)
    bird_id = state.players[0].bird_hand[0]
    placed = place_bird_on_board(state, player_index=0, row=0, col=0, bird_id=bird_id)
    # Simulate tucking N cards by popping deck and incrementing the count, same
    # mechanism as tuck_cards_effect.
    for _ in range(3):
        state.bird_deck.pop()
    placed.state.tucked_cards = 3

    new_state = redeterminize(state, perspective_player=0, rng=random.Random(0))

    locations = _all_bird_locations(new_state, perspective=0)
    assert len(locations) == len(BIRD_REGISTRY) - _tucked_total(new_state)
    assert len(set(locations)) == len(locations)


# =============================================================================
# Randomization
# =============================================================================


def test_different_seeds_yield_different_opponent_hands():
    state = initiate_state(2, seed=42)

    s_a = redeterminize(state, perspective_player=0, rng=random.Random(1))
    s_b = redeterminize(state, perspective_player=0, rng=random.Random(2))

    # Opponent (index 1) should have different hand identities under different seeds.
    assert s_a.players[1].bird_hand != s_b.players[1].bird_hand


def test_same_seed_yields_deterministic_result():
    state = initiate_state(2, seed=42)

    s_a = redeterminize(state, perspective_player=0, rng=random.Random(99))
    s_b = redeterminize(state, perspective_player=0, rng=random.Random(99))

    assert s_a.players[1].bird_hand == s_b.players[1].bird_hand
    assert s_a.bird_deck == s_b.bird_deck
    assert s_a.players[1].bonus_hand == s_b.players[1].bonus_hand
    assert s_a.bonus_deck == s_b.bonus_deck


def test_opponent_hand_drawn_from_unknown_pool_only():
    """Opponent hand can't contain cards the perspective player can see."""
    state = initiate_state(2, seed=42)
    perspective_known = set(state.players[0].bird_hand) | set(state.bird_tray)

    for seed in range(10):
        new_state = redeterminize(state, perspective_player=0, rng=random.Random(seed))
        assert perspective_known.isdisjoint(set(new_state.players[1].bird_hand))


# =============================================================================
# RNG reseed
# =============================================================================


def test_state_rng_reseeded():
    """state.rng should be a fresh Random instance, not the original."""
    state = initiate_state(2, seed=42)
    original_rng_state = state.rng.getstate()

    new_state = redeterminize(state, perspective_player=0, rng=random.Random(123))

    assert new_state.rng.getstate() != original_rng_state


# =============================================================================
# In-flight power execution context
# =============================================================================


def test_in_flight_bonus_options_preserved_and_excluded_from_pool():
    """Cards in Power 5's bonus_options stay in context and don't leak into opponent hands."""
    state = initiate_state(2, seed=42)
    drawn = [state.bonus_deck.pop(), state.bonus_deck.pop()]
    state.action_data.execution_stack.append(
        PowerExecution(
            power_id=5,
            bird_id=0,
            spot_row=0,
            spot_col=0,
            player_index=0,
            phase="select_bonus",
            context={"bonus_options": list(drawn)},
        )
    )

    new_state = redeterminize(state, perspective_player=0, rng=random.Random(0))

    new_ctx = new_state.action_data.execution_stack[0].context["bonus_options"]
    assert new_ctx == drawn

    locations = _all_bonus_locations(new_state)
    assert sorted(locations) == sorted(BONUS_REGISTRY.keys())
    # Opponent must not receive a card that's currently in flight.
    assert set(drawn).isdisjoint(set(new_state.players[1].bonus_hand))


def test_in_flight_available_cards_excluded_from_bird_pool():
    """Power 6's available_cards (in-flight bird draws) don't leak into opponent hands or deck."""
    state = initiate_state(2, seed=42)
    drawn = [state.bird_deck.pop() for _ in range(3)]
    state.action_data.execution_stack.append(
        PowerExecution(
            power_id=6,
            bird_id=0,
            spot_row=0,
            spot_col=0,
            player_index=0,
            phase="select_card",
            context={
                "available_cards": list(drawn),
                "awaiting_players": [0, 1],
                "activator": 0,
            },
        )
    )

    new_state = redeterminize(state, perspective_player=0, rng=random.Random(0))

    assert new_state.action_data.execution_stack[0].context["available_cards"] == drawn
    assert set(drawn).isdisjoint(set(new_state.players[1].bird_hand))
    assert set(drawn).isdisjoint(set(new_state.bird_deck))

    locations = _all_bird_locations(new_state, perspective=0)
    assert sorted(locations) == sorted(BIRD_REGISTRY.keys())
