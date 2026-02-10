from typing import Optional

from game.core import GameState, roll_feeder, PlacedBird, BirdState
from game.utils import ensure_bird_deck


def draw_cards_effect(
    state: GameState,
    tray_bird_ids: list[int],
    deck_count: int,
    player_index: Optional[int] = None,
) -> None:
    """Draw cards from tray and/or deck. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id in tray_bird_ids:
        if bird_id in state.bird_tray:
            target_player.bird_hand.append(bird_id)
            state.bird_tray.remove(bird_id)

    ensure_bird_deck(state, deck_count)
    actual_deck_draws = min(deck_count, len(state.bird_deck))
    for _ in range(actual_deck_draws):
        target_player.bird_hand.append(state.bird_deck.pop())


def tuck_cards_effect(state: GameState, bird_id: int, count: int) -> None:
    """Draw cards from deck and tuck them under a specific bird. Mutates state in-place."""
    current_player = state.players[state.current_player_index]

    for row in current_player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.id == bird_id:
                ensure_bird_deck(state, count)
                actual_tucks = min(count, len(state.bird_deck))
                for _ in range(actual_tucks):
                    state.bird_deck.pop()

                spot.bird.state.tucked_cards += actual_tucks
                return

    raise ValueError(f"Bird {bird_id} not found on current player's board")


def gain_food_effect(
    state: GameState,
    food_type: str,
    amount: int = 1,
    player_index: Optional[int] = None,
) -> None:
    """Add food to player's supply. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    if food_type in target_player.food:
        target_player.food[food_type] += amount
    else:
        target_player.food[food_type] = amount


def lay_eggs_effect(
    state: GameState,
    egg_distribution: dict[int, int],
    player_index: Optional[int] = None,
) -> None:
    """Add eggs to birds. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id, eggs_to_add in egg_distribution.items():
        for row in target_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.id == bird_id:
                    spot.bird.state.eggs += eggs_to_add
                    break


def select_die_effect(
    state: GameState,
    die_index: int,
    food_type: str,
    player_index: Optional[int] = None,
) -> None:
    """Select die from feeder and gain food. Mutates state in-place."""
    if die_index not in state.feeder:
        raise ValueError(f"Die {die_index} not in feeder")
    if food_type not in state.feeder[die_index]:
        raise ValueError(f"Die {die_index} doesn't have {food_type}")

    gain_food_effect(state, food_type, amount=1, player_index=player_index)
    del state.feeder[die_index]

    if not state.feeder:
        state.feeder = roll_feeder(state.rng)


def place_bird_effect(
    state: GameState,
    bird_id: int,
    row: int,
    col: int,
    player_index: Optional[int] = None,
) -> None:
    """Place bird from hand onto board spot. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    if bird_id not in target_player.bird_hand:
        raise ValueError(f"Bird {bird_id} not in hand")

    target_spot = target_player.board[row][col]

    if target_spot.bird is not None:
        raise ValueError(f"Spot at {row}, {col} is already occupied")

    placed_bird = PlacedBird(id=bird_id, state=BirdState())
    target_spot.bird = placed_bird
    target_player.bird_hand.remove(bird_id)


def pay_eggs_effect(
    state: GameState,
    egg_payment: dict[int, int],
    player_index: Optional[int] = None,
) -> None:
    """Remove eggs from birds to pay a cost. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id, eggs_to_remove in egg_payment.items():
        for row in target_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.id == bird_id:
                    spot.bird.state.eggs -= eggs_to_remove
                    break


def pay_food_effect(
    state: GameState,
    food_payment: dict[str, int],
    player_index: Optional[int] = None,
) -> None:
    """Remove food from player's supply to pay a cost. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for food_type, amount in food_payment.items():
        target_player.food[food_type] -= amount
        if target_player.food[food_type] == 0:
            del target_player.food[food_type]


def discard_bird_from_hand_effect(
    state: GameState,
    bird_id: int,
    player_index: Optional[int] = None,
) -> None:
    """Remove bird from hand and add to discard pile. Mutates state in-place."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    if bird_id not in target_player.bird_hand:
        raise ValueError(f"Bird {bird_id} not in hand")

    target_player.bird_hand.remove(bird_id)
    state.discarded_birds.append(bird_id)
