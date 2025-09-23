from typing import Dict, Optional, List
from .data import GameState


def can_execute_power(state: GameState, power_data: Dict) -> bool:
    """Check if a power can be executed."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        return False

    power_id = power_data["data"]["id"]
    validator = POWER_VALIDATORS.get(power_id)

    if not validator:
        return False

    return validator(state, power_data)


def execute_power(
    state: GameState, power_data: Dict, choice: Optional[str] = None
) -> GameState:
    """Execute a power."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        return state

    power_id = power_data["data"]["id"]
    executor = POWER_EXECUTORS.get(power_id)

    if not executor:
        return state

    kwargs = {"choice": choice} if choice else {}
    return executor(state, power_data, **kwargs)


def can_execute_power_1(state: GameState, power_data: Dict) -> bool:
    """Check if Power ID 1 (all players gain resource) can be executed."""
    if not power_data.get("data") or not power_data["data"].get("details"):
        return False

    resource_type = power_data["data"]["details"].get("type")

    if resource_type == "card":
        return len(state.bird_deck) > 0

    return True


def execute_power_1(state: GameState, power_data: Dict) -> GameState:
    """Execute Power ID 1: All players gain 1 specified resource."""
    if not power_data.get("data") or not power_data["data"].get("details"):
        return state

    resource_type = power_data["data"]["details"].get("type")

    for player in state.players:
        if resource_type == "card":
            if state.bird_deck:
                player.bird_hand.append(state.bird_deck.pop())
        else:
            if resource_type in player.food:
                player.food[resource_type] += 1
            else:
                player.food[resource_type] = 1

    return state


def get_power_choices(state: GameState, power_data: Dict) -> List[str]:
    """Get available choices for a power that requires player selection."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        return []

    power_id = power_data["data"]["id"]
    choice_generator = POWER_CHOICE_GENERATORS.get(power_id)

    if not choice_generator:
        return []

    return choice_generator(state, power_data)


POWER_VALIDATORS = {
    1: can_execute_power_1,
}

POWER_EXECUTORS = {
    1: execute_power_1,
}

POWER_CHOICE_GENERATORS = {}
