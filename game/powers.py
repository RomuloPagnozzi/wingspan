from typing import Dict
from .data import GameState
from .utils import get_valid_birds_for_eggs


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


POWER_VALIDATORS = {
    1: _can_execute_power_1,
    2: _can_execute_power_2,
    3: lambda _, __: True,
    4: _can_execute_power_4,
    5: lambda _, __: True,
    6: lambda _, __: True,
    7: lambda _, __: True,
}
