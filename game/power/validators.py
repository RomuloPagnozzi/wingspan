from typing import Callable

from ..core import GameState, get_bird_power
from ..utils import (
    get_valid_birds_for_eggs,
    find_leftmost_empty_spot,
    generate_playable_bird_spots,
    get_available_bird_cards,
)

_POWER_VALIDATORS: dict[int, Callable[[GameState, dict], bool]] = {}


def power_validator(power_id: int):
    """Decorator to register a power validator."""

    def decorator(func):
        _POWER_VALIDATORS[power_id] = func
        return func

    return decorator


def can_execute_power(state: GameState, power_entry: dict) -> bool:
    """Check if a power can be executed."""
    power_data = power_entry.get("power_data", power_entry)
    if not power_data.get("data") or "id" not in power_data["data"]:
        return False

    power_type = power_data["data"]["id"]
    validator = _POWER_VALIDATORS.get(power_type)

    if not validator:
        return True

    return validator(state, power_entry)


@power_validator(1)
def _can_execute_power_1(state: GameState, power_entry: dict) -> bool:
    """Validate power type 1: all players gain resource."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    if details.get("type") == "card":
        return get_available_bird_cards(state) >= len(state.players)
    return True


@power_validator(2)
def _can_execute_power_2(state: GameState, power_entry: dict) -> bool:
    """Validate power type 2: all players lay eggs on nest type."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")
    if not nest_type:
        return False

    for player in state.players:
        if get_valid_birds_for_eggs(player, nest_type):
            return True
    return False


@power_validator(4)
def _can_execute_power_4(state: GameState, power_entry: dict) -> bool:
    """Validate power type 4: discard resource to gain resource/cards."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    discard_type = details.get("discard")
    gain = details.get("gain")
    gain_qty = details.get("gain_qty", 1)

    current_player = state.players[state.current_player_index]

    if gain == "card":
        if get_available_bird_cards(state) < gain_qty:
            return False

    if discard_type == "egg":
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.state.eggs > 0:
                    if gain == "wild":
                        activating_bird_id = power_entry.get("bird_id")
                        if spot.bird.id != activating_bird_id:
                            return True
                    else:
                        return True
        return False
    else:
        return current_player.food.get(discard_type, 0) > 0


@power_validator(5)
def _can_execute_power_5(state: GameState, power_entry: dict) -> bool:
    """Validate power type 5: draw cards or bonus."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    amount = details.get("amount", 1)

    if details.get("bonus"):
        return len(state.bonus_deck) >= amount

    return get_available_bird_cards(state) >= amount


@power_validator(6)
def _can_execute_power_6(state: GameState, power_entry: dict) -> bool:
    """Validate power type 6: draw n+1 cards for all players to select."""
    return get_available_bird_cards(state) >= len(state.players) + 1


@power_validator(8)
def _can_execute_power_8(state: GameState, power_entry: dict) -> bool:
    """Validate power type 8: gain food."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    source = details["source"]
    food_types = details["food_types"]

    if source == "supply":
        return True

    for food_type in food_types:
        for die_face in state.feeder.values():
            if food_type in die_face:
                return True

    return False


@power_validator(9)
def _can_execute_power_9(state: GameState, power_entry: dict) -> bool:
    """Validate power type 9: move bird to another habitat if rightmost."""
    spot = power_entry["spot"]
    bird = spot.bird
    current_habitat = spot.habitat

    habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
    current_player = state.players[state.current_player_index]
    habitat_row = current_player.board[habitat_map[current_habitat]]

    birds_in_habitat = [s for s in habitat_row if s.bird is not None]
    if not birds_in_habitat:
        return False
    rightmost_spot = max(birds_in_habitat, key=lambda s: s.col)
    if spot.col != rightmost_spot.col:
        return False

    for habitat in bird.card.habitats:
        if habitat != current_habitat:
            target_row = current_player.board[habitat_map[habitat]]
            if find_leftmost_empty_spot(target_row) is not None:
                return True

    return False


@power_validator(10)
def _can_execute_power_10(state: GameState, power_entry: dict) -> bool:
    """Validate power type 10: lay eggs on birds."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    is_this = details.get("this", False)
    nest_type = details.get("type", "")

    current_player = state.players[state.current_player_index]

    if is_this:
        spot = power_entry.get("spot")
        if spot and spot.bird:
            return spot.bird.state.eggs < spot.bird.card.egg_limit
        return False

    if nest_type == "any":
        for row in current_player.board:
            for spot in row:
                if (
                    spot.bird is not None
                    and spot.bird.state.eggs < spot.bird.card.egg_limit
                ):
                    return True
        return False

    return len(get_valid_birds_for_eggs(current_player, nest_type)) > 0


@power_validator(11)
def _can_execute_power_11(state: GameState, power_entry: dict) -> bool:
    """Validate power type 11: predator draws 1 card."""
    return get_available_bird_cards(state) >= 1


@power_validator(12)
def _can_execute_power_12(state: GameState, power_entry: dict) -> bool:
    """Validate power type 12: play additional bird in habitat."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    habitat_spec = details.get("habitat", "")

    if habitat_spec == "this":
        spot = power_entry.get("spot")
        if not spot:
            return False
        target_habitat = spot.habitat
    else:
        target_habitat = habitat_spec

    current_player = state.players[state.current_player_index]

    for _, spot in generate_playable_bird_spots(current_player):
        if spot.habitat == target_habitat:
            return True

    return False


@power_validator(14)
def _can_execute_power_14(state: GameState, power_entry: dict) -> bool:
    """Validate power type 14: repeat another bird's power in this habitat."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    repeat_type = details.get("type")

    spot = power_entry.get("spot")
    if not spot:
        return False

    current_player = state.players[state.current_player_index]
    habitat_row = current_player.board[spot.row]

    activating_bird_id = power_entry.get("bird_id")

    for other_spot in habitat_row:
        if other_spot.bird is None:
            continue

        if other_spot.bird.id == activating_bird_id:
            continue

        other_power = get_bird_power(other_spot.bird.id)
        if not other_power or not other_power.get("data"):
            continue

        if repeat_type == "predator":
            if other_power["data"].get("id") == 11:
                return True

        elif repeat_type == "brown":
            if other_power.get("color") == "brown":
                if other_power["data"].get("id") == 14:
                    continue
                power_entry_candidate = {
                    "bird_id": other_spot.bird.id,
                    "spot": other_spot,
                    "power_data": other_power,
                    "player_index": state.current_player_index,
                }
                if can_execute_power(state, power_entry_candidate):
                    return True

    return False


@power_validator(15)
def _can_execute_power_15(state: GameState, power_entry: dict) -> bool:
    """Validate power type 15: roll dice not in birdfeeder."""
    if len(state.feeder) != 5:
        return True
    return False


@power_validator(16)
def _can_execute_power_16(state: GameState, power_entry: dict) -> bool:
    """Validate power type 16: trade 1 food for any other type from supply."""
    current_player = state.players[state.current_player_index]
    return bool(current_player.food)


@power_validator(17)
def _can_execute_power_17(state: GameState, power_entry: dict) -> bool:
    """Validate power type 17: tuck card and get bonus."""
    current_player = state.players[state.current_player_index]
    if not current_player.bird_hand:
        return False

    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    if details.get("types") == ["card"]:
        if get_available_bird_cards(state) < 1:
            return False

    return True


@power_validator(18)
def _can_execute_power_18(state: GameState, power_entry: dict) -> bool:
    """Validate power type 18: gain resource or tuck card when opponent plays in habitat."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    resource = details.get("resource")

    if resource == "card":
        player_index = power_entry.get("player_index", state.current_player_index)
        player = state.players[player_index]
        return bool(player.bird_hand)

    return True


@power_validator(20)
def _can_execute_power_20(state: GameState, power_entry: dict) -> bool:
    """Validate power type 20: lay egg on nest type when opponent lays eggs."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")
    pink_bird_id = power_entry.get("bird_id")

    player_index = power_entry.get("player_index", state.current_player_index)
    player = state.players[player_index]

    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    valid_birds = [b for b in valid_birds if b.id != pink_bird_id]

    return len(valid_birds) > 0
