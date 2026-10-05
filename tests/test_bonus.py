"""Test bonus card counting and scoring."""

from wingspan.engine.core import initiate_state, BONUS_REGISTRY
from wingspan.engine.scoring import count_bonus_birds, score_bonus_card


def test_visionary_leader_counts_hand_with_empty_board():
    """Visionary Leader counts cards in hand even before any bird is played."""
    state = initiate_state(2)
    player = state.players[0]
    player.bird_hand = list(state.bird_deck[:8])
    leader = BONUS_REGISTRY[23]

    assert count_bonus_birds(leader, player) == 8
    assert score_bonus_card(leader, player) == 7
