from typing import Dict
from .data import GameState
from .utils import (
    get_valid_birds_for_eggs,
    find_leftmost_empty_spot,
    generate_playable_bird_spots,
)


def can_execute_power(state: GameState, power_entry: Dict) -> bool:
    """Check if a power can be executed."""
    power_data = power_entry.get("power_data", power_entry)
    if not power_data.get("data") or "id" not in power_data["data"]:
        return False

    power_type = power_data["data"]["id"]
    validator = POWER_VALIDATORS.get(power_type)

    if not validator:
        return False

    return validator(state, power_entry)


def _can_execute_power_1(state: GameState, power_entry: Dict) -> bool:
    """Validate power type 1: all players gain resource."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    if details.get("type") == "card":
        return len(state.bird_deck) > 0
    return True


def _can_execute_power_2(state: GameState, power_entry: Dict) -> bool:
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


def _can_execute_power_4(state: GameState, power_entry: Dict) -> bool:
    """Validate power type 4: discard resource to gain resource/cards."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    discard_type = details.get("discard")
    gain = details.get("gain")

    current_player = state.players[state.current_player_index]

    if discard_type == "egg":
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.eggs > 0:
                    if gain == "wild":
                        activating_bird_id = power_entry.get("bird_id")
                        if spot.bird.id != activating_bird_id:
                            return True
                    else:
                        return True
        return False
    else:
        return current_player.food.get(discard_type, 0) > 0


def _can_execute_power_8(state: GameState, power_entry: Dict) -> bool:
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


def _can_execute_power_9(state: GameState, power_entry: Dict) -> bool:
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

    for habitat in bird.habitats:
        if habitat != current_habitat:
            target_row = current_player.board[habitat_map[habitat]]
            if find_leftmost_empty_spot(target_row) is not None:
                return True

    return False


def _can_execute_power_10(state: GameState, power_entry: Dict) -> bool:
    """Validate power type 10: lay eggs on birds."""
    power_data = power_entry.get("power_data", power_entry)
    details = power_data["data"].get("details", {})
    is_this = details.get("this", False)
    nest_type = details.get("type", "")

    current_player = state.players[state.current_player_index]

    if is_this:
        spot = power_entry.get("spot")
        if spot and spot.bird:
            return spot.bird.eggs < spot.bird.egg_limit
        return False

    if nest_type == "any":
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.eggs < spot.bird.egg_limit:
                    return True
        return False

    return len(get_valid_birds_for_eggs(current_player, nest_type)) > 0


def _can_execute_power_12(state: GameState, power_entry: Dict) -> bool:
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


POWER_VALIDATORS = {
    1: _can_execute_power_1,
    2: _can_execute_power_2,
    3: lambda _, __: True,
    4: _can_execute_power_4,
    5: lambda _, __: True,
    6: lambda _, __: True,
    7: lambda _, __: True,
    8: _can_execute_power_8,
    9: _can_execute_power_9,
    10: _can_execute_power_10,
    11: lambda _, __: True,
    12: _can_execute_power_12,
}
