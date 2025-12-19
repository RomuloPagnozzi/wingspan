import json
from typing import Optional, Dict, List
from game.data import GameState, roll_feeder


def draw_cards_effect(
    state: GameState,
    tray_bird_ids: List[int],
    deck_count: int,
    player_index: Optional[int] = None,
) -> GameState:
    """Draw cards from tray and/or deck."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id in tray_bird_ids:
        for bird in state.bird_tray:
            if bird.id == bird_id:
                target_player.bird_hand.append(bird)
                state.bird_tray.remove(bird)
                break

    for _ in range(deck_count):
        if state.bird_deck:
            target_player.bird_hand.append(state.bird_deck.pop())

    while len(state.bird_tray) < 3 and state.bird_deck:
        state.bird_tray.append(state.bird_deck.pop())

    return state


def parse_draw_cards_action(action: str) -> tuple:
    """Parse draw cards action to effect parameters."""
    data = json.loads(action)
    return data["tray_birds"], data["deck_cards"]


def tuck_cards_effect(state: GameState, bird_id: int, count: int) -> GameState:
    """Draw cards from deck and tuck them under a specific bird."""
    current_player = state.players[state.current_player_index]

    for row in current_player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.id == bird_id:
                for _ in range(count):
                    if state.bird_deck:
                        state.bird_deck.pop()

                spot.bird.tucked_cards += count
                return state

    raise ValueError(f"Bird {bird_id} not found on current player's board")


def gain_food_effect(
    state: GameState,
    food_type: str,
    amount: int = 1,
    player_index: Optional[int] = None,
) -> GameState:
    """Add food to player's supply."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    if food_type in target_player.food:
        target_player.food[food_type] += amount
    else:
        target_player.food[food_type] = amount

    return state


def lay_eggs_effect(
    state: GameState,
    egg_distribution: Dict[int, int],
    player_index: Optional[int] = None,
) -> GameState:
    """Add eggs to birds."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id, eggs_to_add in egg_distribution.items():
        for row in target_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.id == bird_id:
                    spot.bird.eggs += eggs_to_add
                    break

    return state


def parse_lay_eggs_action(action: str) -> Dict[int, int]:
    """Parse lay eggs action to effect parameters."""
    return {int(k): v for k, v in json.loads(action).items()}


def select_die_effect(state: GameState, die_index: int, food_type: str) -> GameState:
    """Select die from feeder and gain food."""
    if die_index not in state.feeder:
        raise ValueError(f"Die {die_index} not in feeder")
    if food_type not in state.feeder[die_index]:
        raise ValueError(f"Die {die_index} doesn't have {food_type}")

    state = gain_food_effect(state, food_type, amount=1)
    del state.feeder[die_index]

    if not state.feeder:
        state.feeder = roll_feeder()

    return state


def parse_select_die_action(action: str) -> tuple:
    """Parse select die action to effect parameters."""
    parts = action.split("_")
    die_index = int(parts[2])
    food_type = parts[3]
    return die_index, food_type


def place_bird_effect(
    state: GameState,
    bird_id: int,
    row: int,
    col: int,
    player_index: Optional[int] = None,
) -> GameState:
    """Place bird from hand onto board spot."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    bird_to_play = None
    for bird in target_player.bird_hand:
        if bird.id == bird_id:
            bird_to_play = bird
            break

    if not bird_to_play:
        raise ValueError(f"Bird {bird_id} not in hand")

    target_spot = target_player.board[row][col]

    if target_spot.bird is not None:
        raise ValueError(f"Spot at {row}, {col} is already occupied")

    target_spot.bird = bird_to_play
    target_player.bird_hand.remove(bird_to_play)

    return state


def parse_play_bird_action(action: str) -> tuple:
    """Parse play bird action to effect parameters."""
    parts = action.split("_")
    bird_id = int(parts[2])
    row = int(parts[4])
    col = int(parts[5])
    return bird_id, row, col


def parse_pay_eggs_action(action: str) -> Dict[int, int]:
    """Parse pay eggs action to effect parameters."""
    return {int(k): v for k, v in json.loads(action).items()}


def pay_eggs_effect(
    state: GameState,
    egg_payment: Dict[int, int],
    player_index: Optional[int] = None,
):
    """Remove eggs from birds to pay a cost."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for bird_id, eggs_to_remove in egg_payment.items():
        for row in target_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.id == bird_id:
                    spot.bird.eggs -= eggs_to_remove
                    break

    return state


def parse_pay_food_action(action: str) -> Dict[str, int]:
    """Parse pay food action to effect parameters."""
    return json.loads(action)


def pay_food_effect(
    state: GameState,
    food_payment: Dict[str, int],
    player_index: Optional[int] = None,
):
    """Remove food from player's supply to pay a cost."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    for food_type, amount in food_payment.items():
        target_player.food[food_type] -= amount
        if target_player.food[food_type] == 0:
            del target_player.food[food_type]

    return state


def discard_bird_from_hand_effect(
    state: GameState,
    bird_id: int,
    player_index: Optional[int] = None,
):
    """Remove bird from hand and add to discard pile."""
    target_player = state.players[
        player_index if player_index is not None else state.current_player_index
    ]

    bird_to_discard = None
    for bird in target_player.bird_hand:
        if bird.id == bird_id:
            bird_to_discard = bird
            break

    if not bird_to_discard:
        raise ValueError(f"Bird {bird_id} not in hand")

    target_player.bird_hand.remove(bird_to_discard)
    state.discarded_birds.append(bird_to_discard)

    return state
