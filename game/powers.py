from typing import Dict
from .data import GameState
from .utils import get_valid_birds_for_eggs


def can_execute_power(state: GameState, power_data: Dict) -> bool:
    """Check if a power can be executed."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        return False

    power_type = power_data["data"]["id"]
    validator = POWER_VALIDATORS.get(power_type)

    if not validator:
        return False

    return validator(state, power_data)


def _can_execute_power_1(state: GameState, power_data: Dict) -> bool:
    """Validate power type 1: all players gain resource."""
    details = power_data["data"].get("details", {})
    if details.get("type") == "card":
        return len(state.bird_deck) > 0
    return True


def _can_execute_power_2(state: GameState, power_data: Dict) -> bool:
    """Validate power type 2: all players lay eggs on nest type."""
    details = power_data["data"].get("details", {})
    nest_type = details.get("type")
    if not nest_type:
        return False

    for player in state.players:
        if get_valid_birds_for_eggs(player, nest_type):
            return True
    return False


POWER_VALIDATORS = {
    1: _can_execute_power_1,
    2: _can_execute_power_2,
}
