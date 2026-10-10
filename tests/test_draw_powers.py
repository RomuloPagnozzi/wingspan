"""Powers that say "draw" may take face-up tray cards or deck cards.
Powers that say "from the deck" may not."""

from wingspan.engine.core import (
    initiate_state,
    BIRD_REGISTRY,
    PlacedBird,
    get_bird_power,
    init_registries,
    GamePhase,
    SimpleAction,
    IdAction,
    DrawCardsAction,
)
from wingspan.engine.engine import transition_state
from wingspan.engine.actions import get_actions
from conftest import setup_power_queue

init_registries()
BY_NAME = {b.name: b.id for b in BIRD_REGISTRY.values()}


def activate(name: str, n_players: int = 2, actor: int = 0):
    """State where `actor` has just activated the named bird's power."""
    state = initiate_state(n_players, seed=0)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = actor
    for i, p in enumerate(state.players):
        p.first_player = i == actor
        p.action_cubes = 8
    bird_id = BY_NAME[name]
    spot = state.players[actor].board[2][0]
    spot.bird = PlacedBird(bird_id)
    setup_power_queue(
        state,
        [{"bird_id": bird_id, "power_data": get_bird_power(bird_id), "spot": spot}],
    )
    state.action_data.action_player_index = actor
    return transition_state(state, SimpleAction("activate_power"))


def test_draw_1_offers_each_tray_card_or_the_deck():
    state = activate("Mallard")
    tray = list(state.bird_tray)

    assert set(get_actions(state)) == {DrawCardsAction((), 1)} | {
        DrawCardsAction((b,), 0) for b in tray
    }


def test_tray_card_goes_to_hand_and_tray_refills_only_at_end_of_turn():
    state = activate("Mallard")
    tray, deck_size = list(state.bird_tray), len(state.bird_deck)
    state.action_data.powers_queue.append(state.action_data.powers_queue[0])

    state = transition_state(state, DrawCardsAction((tray[0],), 0))
    assert tray[0] in state.players[0].bird_hand
    assert state.bird_tray == tray[1:]  # not refilled mid-turn
    assert len(state.bird_deck) == deck_size

    # A second draw power this turn only sees the 2 remaining tray cards
    state = transition_state(state, SimpleAction("activate_power"))
    assert DrawCardsAction((tray[0],), 0) not in get_actions(state)
    state = transition_state(state, DrawCardsAction((), 1))

    assert state.game_phase == GamePhase.MAIN_TURN
    assert len(state.bird_tray) == 3


def test_draw_2_can_mix_tray_and_deck_then_discards_at_end_of_turn():
    state = activate("Wood Duck")
    tray = list(state.bird_tray)
    actions = get_actions(state)
    assert DrawCardsAction((), 2) in actions
    assert DrawCardsAction((tray[0],), 1) in actions
    assert DrawCardsAction((tray[0], tray[1]), 0) in actions
    hand = len(state.players[0].bird_hand)

    state = transition_state(state, DrawCardsAction((tray[0],), 1))
    assert state.game_phase == GamePhase.END_TURN
    assert len(state.players[0].bird_hand) == hand + 2
    state = transition_state(state, IdAction("discard_card", tray[0]))
    assert len(state.players[0].bird_hand) == hand + 1


def test_discard_egg_to_draw_2_from_tray():
    state = initiate_state(2, seed=0)
    state.game_phase = GamePhase.ACTIVATE_POWERS
    state.current_player_index = 0
    bird_id = BY_NAME["Killdeer"]
    spot = state.players[0].board[2][0]
    spot.bird = PlacedBird(bird_id)
    spot.bird.state.eggs = 1
    setup_power_queue(
        state,
        [{"bird_id": bird_id, "power_data": get_bird_power(bird_id), "spot": spot}],
    )
    tray = list(state.bird_tray)

    state = transition_state(state, SimpleAction("activate_power"))
    state = transition_state(state, IdAction("discard_egg_from", bird_id))
    state = transition_state(state, DrawCardsAction((tray[1], tray[2]), 0))

    assert {tray[1], tray[2]} <= set(state.players[0].bird_hand)
    assert state.players[0].board[2][0].bird.state.eggs == 0


def test_tuck_then_draw_from_tray():
    state = activate("Tree Swallow")
    tray = list(state.bird_tray)
    tucked = state.players[0].bird_hand[0]

    state = transition_state(state, IdAction("tuck_card", tucked))
    state = transition_state(state, DrawCardsAction((tray[0],), 0))

    assert tray[0] in state.players[0].bird_hand
    assert tucked not in state.players[0].bird_hand
    assert state.players[0].board[2][0].bird.state.tucked_cards == 1


def test_fewest_wetland_birds_draw_in_turn_order_from_the_activator():
    """Players 0 and 2 are tied with no wetland birds; the activator (1) is not."""
    state = activate("Common Loon", n_players=3, actor=1)
    tray = list(state.bird_tray)

    assert state.current_player_index == 2  # clockwise from the activator
    state = transition_state(state, DrawCardsAction((tray[0],), 0))
    assert tray[0] in state.players[2].bird_hand

    assert state.current_player_index == 0
    assert DrawCardsAction((tray[0],), 0) not in get_actions(state)
    state = transition_state(state, DrawCardsAction((), 1))

    assert len(state.players[0].bird_hand) == 6
    assert len(state.players[1].bird_hand) == 5
    assert state.game_phase == GamePhase.MAIN_TURN


def test_all_players_draw_from_the_deck_has_no_tray_choice():
    state = activate("Northern Shoveler")

    assert state.game_phase == GamePhase.MAIN_TURN  # resolved without a prompt
    assert [len(p.bird_hand) for p in state.players] == [6, 6]
    assert len(state.bird_tray) == 3
