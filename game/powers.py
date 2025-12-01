from typing import Dict, Optional, List
from .data import GameState
from .utils import get_valid_birds_for_eggs, get_egg_distribution_combinations
import json
from .effects import (
    EffectResult,
    EffectContext,
    draw_cards_effect,
    gain_food_effect,
    lay_eggs_effect,
)


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


def get_power_choices(state: GameState, power_data: Dict) -> List[str]:
    """Get available choices for a power that requires player selection."""
    if not power_data.get("data") or "id" not in power_data["data"]:
        return []

    power_id = power_data["data"]["id"]
    choice_generator = POWER_CHOICE_GENERATORS.get(power_id)

    if not choice_generator:
        return []

    return choice_generator(state, power_data)


def _can_execute_power_1(state: GameState, power_data: Dict) -> bool:
    """Check if Power ID 1 (all players gain resource) can be executed."""
    if not power_data.get("data") or not power_data["data"].get("details"):
        return False

    resource_type = power_data["data"]["details"].get("type")

    if resource_type == "card":
        return len(state.bird_deck) > 0

    return True


def _execute_power_1(state: GameState, power_data: Dict) -> GameState:
    """Execute Power ID 1: All players gain 1 resource."""
    from .engine import apply_effect_with_flow

    resource_type = power_data["data"]["details"].get("type")

    if resource_type == "card":
        for i in range(len(state.players)):
            state = draw_cards_effect(
                state, tray_bird_ids=[], deck_count=1, player_index=i
            )
    else:
        for i in range(len(state.players)):
            state = gain_food_effect(state, resource_type, amount=1, player_index=i)

    result = EffectResult(state=state, triggers_powers=False)
    return apply_effect_with_flow(state, result, EffectContext.POWER_ACTIVATION)


def _can_execute_power_2(state: GameState, power_data: Dict) -> bool:
    """Check if Power ID 2 (all players lay eggs on nest type birds) can be executed."""
    if not power_data.get("data") or not power_data["data"].get("details"):
        return False

    nest_type = power_data["data"]["details"].get("type")
    if not nest_type:
        return False

    if "power_2_players" in state.action_data:
        queue = state.action_data["power_2_players"]
        if not queue:
            return False

        player_idx, _ = queue[0]
        player = state.players[player_idx]
        valid_birds = get_valid_birds_for_eggs(player, nest_type)
        return len(valid_birds) > 0

    activating_player = state.players[state.current_player_index]
    valid_birds = get_valid_birds_for_eggs(activating_player, nest_type)
    return len(valid_birds) > 0


def _execute_power_2(
    state: GameState, power_data: Dict, choice: Optional[str] = None
) -> GameState:
    """Execute Power ID 2: All players lay eggs on nest type birds."""
    nest_type = power_data["data"]["details"].get("type")

    if "power_2_players" not in state.action_data:
        activating_player_idx = state.current_player_index
        queue = []

        for i, player in enumerate(state.players):
            valid_birds = get_valid_birds_for_eggs(player, nest_type)
            if valid_birds:
                eggs_to_lay = 2 if i == activating_player_idx else 1
                queue.append((i, eggs_to_lay))

        state.action_data["power_2_players"] = queue
        state.action_data["choice_powers"] = True

        if queue:
            state.current_player_index = queue[0][0]
            if "current_power_index" in state.action_data:
                state.action_data["current_power_index"] -= 1

        return state

    if choice is not None:
        player_idx, _ = state.action_data["power_2_players"].pop(0)
        egg_distribution = {int(k): v for k, v in json.loads(choice).items()}

        state = lay_eggs_effect(state, egg_distribution, player_index=player_idx)

        if state.action_data["power_2_players"]:
            next_player_idx, _ = state.action_data["power_2_players"][0]
            state.current_player_index = next_player_idx

            if "current_power_index" in state.action_data:
                state.action_data["current_power_index"] -= 1
        else:
            del state.action_data["power_2_players"]
            if "choice_powers" in state.action_data:
                del state.action_data["choice_powers"]

    return state


def _get_power_2_choice_actions(state: GameState, power_data: Dict) -> List[str]:
    """Get available choices for Power ID 2."""
    if "power_2_players" not in state.action_data:
        return []

    queue = state.action_data["power_2_players"]
    if not queue:
        return []

    nest_type = power_data["data"]["details"].get("type")
    player_idx, egg_count = queue[0]
    player = state.players[player_idx]

    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    birds_capacity = {bird.id: bird.egg_limit - bird.eggs for bird in valid_birds}

    combinations = get_egg_distribution_combinations(birds_capacity, egg_count)

    return [json.dumps(combo) for combo in combinations]


POWER_VALIDATORS = {
    1: _can_execute_power_1,
    2: _can_execute_power_2,
}

POWER_EXECUTORS = {
    1: _execute_power_1,
    2: _execute_power_2,
}

POWER_CHOICE_GENERATORS = {
    2: _get_power_2_choice_actions,
}
