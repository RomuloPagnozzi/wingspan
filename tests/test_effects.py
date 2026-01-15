"""Test atomic effects in isolation."""

import sys

sys.path.append(".")
from game.data import initiate_state
from game.effects import (
    draw_cards_effect,
    gain_food_effect,
    lay_eggs_effect,
    parse_draw_cards_action,
    parse_lay_eggs_action,
    place_bird_effect,
    parse_play_bird_action,
    pay_eggs_effect,
    pay_food_effect,
)
import json


def test_draw_cards_from_deck():
    state = initiate_state(2)
    initial_hand = len(state.players[0].bird_hand)

    draw_cards_effect(state, tray_bird_ids=[], deck_count=2, player_index=0)

    assert len(state.players[0].bird_hand) == initial_hand + 2
    assert len(state.bird_tray) == 3


def test_draw_cards_from_tray():
    state = initiate_state(2)
    tray_bird_id = state.bird_tray[0].id

    draw_cards_effect(state, tray_bird_ids=[tray_bird_id], deck_count=0, player_index=0)

    assert any(bird.id == tray_bird_id for bird in state.players[0].bird_hand)
    assert len(state.bird_tray) == 2


def test_draw_cards_different_player():
    state = initiate_state(2)
    initial_hand = len(state.players[1].bird_hand)

    draw_cards_effect(state, tray_bird_ids=[], deck_count=1, player_index=1)

    assert len(state.players[1].bird_hand) == initial_hand + 1


def test_gain_food_new():
    state = initiate_state(2)
    state.players[0].food = {}

    gain_food_effect(state, "fish", amount=2, player_index=0)

    assert state.players[0].food["fish"] == 2


def test_gain_food_existing():
    state = initiate_state(2)
    state.players[0].food = {"fish": 3}

    gain_food_effect(state, "fish", amount=1, player_index=0)

    assert state.players[0].food["fish"] == 4


def test_lay_eggs_single_bird():
    state = initiate_state(2)
    bird = state.players[0].bird_hand[0]
    state.players[0].board[0][0].bird = bird

    lay_eggs_effect(state, {bird.id: 2}, player_index=0)

    assert state.players[0].board[0][0].bird.eggs == 2


def test_lay_eggs_multiple_birds():
    state = initiate_state(2)
    bird1 = state.players[0].bird_hand[0]
    bird2 = state.players[0].bird_hand[1]
    state.players[0].board[0][0].bird = bird1
    state.players[0].board[1][1].bird = bird2

    lay_eggs_effect(state, {bird1.id: 1, bird2.id: 3}, player_index=0)

    assert state.players[0].board[0][0].bird.eggs == 1
    assert state.players[0].board[1][1].bird.eggs == 3


def test_parse_draw_cards_action():
    action = json.dumps({"tray_birds": [1, 2], "deck_cards": 3})
    tray_ids, deck_count = parse_draw_cards_action(action)
    assert tray_ids == [1, 2]
    assert deck_count == 3


def test_parse_lay_eggs_action():
    action = json.dumps({"123": 2, "456": 1})
    distribution = parse_lay_eggs_action(action)
    assert distribution == {123: 2, 456: 1}


def test_place_bird():
    state = initiate_state(2)
    bird = state.players[0].bird_hand[0]
    initial_hand_size = len(state.players[0].bird_hand)

    place_bird_effect(state, bird.id, row=0, col=0, player_index=0)

    assert state.players[0].board[0][0].bird == bird
    assert len(state.players[0].bird_hand) == initial_hand_size - 1


def test_place_bird_different_player():
    state = initiate_state(2)
    bird = state.players[1].bird_hand[0]

    place_bird_effect(state, bird.id, row=1, col=2, player_index=1)

    assert state.players[1].board[1][2].bird == bird


def test_parse_play_bird_action():
    action = "play_bird_123_at_1_2"
    bird_id, row, col = parse_play_bird_action(action)
    assert bird_id == 123
    assert row == 1
    assert col == 2


def test_pay_eggs():
    state = initiate_state(2)
    bird = state.players[0].bird_hand[0]
    state.players[0].board[0][0].bird = bird
    bird.eggs = 3

    pay_eggs_effect(state, {bird.id: 2}, player_index=0)

    assert state.players[0].board[0][0].bird.eggs == 1


def test_pay_food():
    state = initiate_state(2)
    state.players[0].food = {"fish": 3, "seed": 2}

    pay_food_effect(state, {"fish": 2, "seed": 1}, player_index=0)

    assert state.players[0].food == {"fish": 1, "seed": 1}
