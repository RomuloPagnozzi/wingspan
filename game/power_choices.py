from typing import List, Callable, Dict, Tuple
import json

from .data import GameState, PowerExecution
from .utils import (
    get_egg_distribution_combinations,
    get_food_gain_combinations,
    get_valid_birds_for_eggs,
    get_collect_food_actions,
)

POWER_CHOICE_GENERATORS: Dict[Tuple[int, str], Callable] = {}


def power_choices(power_id: int, phase: str):
    """Decorator to register a power choice generator."""

    def decorator(func):
        POWER_CHOICE_GENERATORS[(power_id, phase)] = func
        return func

    return decorator


@power_choices(2, "choices")
def _get_power_2_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate egg distribution choices for power 2."""
    nest_type = execution.context["nest_type"]
    activator = execution.context["activator"]
    player = state.players[state.current_player_index]
    amount = 2 if state.current_player_index == activator else 1

    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    birds_capacity = {b.id: b.egg_limit - b.eggs for b in valid_birds}
    combos = get_egg_distribution_combinations(birds_capacity, amount)
    return [f"activate_{json.dumps(c)}" for c in combos]


@power_choices(4, "select_discard")
def _get_power_4_discard_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate discard choices for power 4."""
    discard_type = execution.context["discard_type"]
    gain_type = execution.context["gain_type"]
    current_player = state.players[state.current_player_index]

    if discard_type == "egg":
        actions = []
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.eggs > 0:
                    if gain_type == "wild" and spot.bird.id == execution.bird_id:
                        continue
                    actions.append(f"discard_egg_from_{spot.bird.id}")
        return actions
    else:
        return [f"discard_food_{discard_type}"]


@power_choices(4, "select_gain")
def _get_power_4_gain_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate resource gain choices for power 4 (wild resource)."""
    gain_qty = execution.context["gain_qty"]
    combos = get_food_gain_combinations(gain_qty)
    return [f"gain_{json.dumps(combo)}" for combo in combos]


@power_choices(5, "select_bonus")
def _get_power_5_bonus_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Get choices for power 5 bonus card selection."""
    drawn_cards = execution.context.get("bonus_options", [])
    return [f"power_5_bonus_{card.id}" for card in drawn_cards]


@power_choices(6, "select_card")
def _get_power_6_card_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate card selection choices for power 6."""
    available_cards = execution.context.get("available_cards", [])
    return [f"select_card_{card.id}" for card in available_cards]


@power_choices(7, "choose_starting_player")
def _get_power_7_starting_player_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate player selection actions for Power 7."""
    num_players = len(state.players)
    return [f"choose_player_{i}" for i in range(num_players)]


@power_choices(7, "select_die")
def _get_power_7_die_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate die selection for Power 7."""
    return get_collect_food_actions(state)


@power_choices(8, "select_food_type")
def _get_power_8_food_type_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate food type choices from available feeder foods."""
    available_foods = execution.context.get("available_foods", [])
    return [f"select_food_type_{food}" for food in available_foods]


@power_choices(8, "select_die")
def _get_power_8_die_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate die choices for selected food type."""
    food_type = execution.context.get("food_type")
    all_actions = get_collect_food_actions(state)

    if not food_type:
        return all_actions

    filtered_actions = []
    for action in all_actions:
        if action == "reroll_all":
            filtered_actions.append(action)
        elif action.endswith(f"_{food_type}"):
            filtered_actions.append(action)

    return filtered_actions


@power_choices(8, "choose_cache")
def _get_power_8_cache_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate cache vs supply choices."""
    return ["cache_food", "supply_food"]


@power_choices(9, "select_habitat")
def _get_power_9_habitat_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate habitat selection actions for Power 9."""
    valid_habitats = execution.context.get("valid_habitats", [])
    return [f"select_habitat_{habitat}" for habitat in valid_habitats]


@power_choices(10, "select_bird")
def _get_power_10_bird_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate bird selection actions for Power 10."""
    valid_bird_ids = execution.context.get("valid_bird_ids", [])
    return [f"select_bird_{bird_id}" for bird_id in valid_bird_ids]


@power_choices(13, "select_die")
def _get_power_13_die_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate die selection actions for Power 13."""
    return get_collect_food_actions(state)


@power_choices(14, "select_bird")
def _get_power_14_bird_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate bird selection actions for Power 14."""
    eligible_birds = execution.context.get("eligible_birds", [])
    return [f"select_bird_{bird['bird_id']}" for bird in eligible_birds]


@power_choices(16, "select_trade")
def _get_power_16_trade_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate trade actions for Power 16."""
    all_food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    current_player = state.players[state.current_player_index]
    player_food_types = list(current_player.food.keys())
    actions = []
    for from_type in player_food_types:
        for to_type in all_food_types:
            if to_type != from_type:
                actions.append(f"trade_{from_type}_for_{to_type}")
    return actions


@power_choices(17, "select_card")
def _get_power_17_card_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate card selection for Power 17."""
    current_player = state.players[state.current_player_index]
    return [f"tuck_card_{card.id}" for card in current_player.bird_hand]


@power_choices(17, "select_food")
def _get_power_17_food_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate food selection for Power 17."""
    food_types = execution.context.get("food_types", [])
    return [f"select_food_{food}" for food in food_types]


@power_choices(18, "select_card")
def _get_power_18_card_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate card selection for Power 18."""
    player = state.players[execution.player_index]
    return [f"tuck_card_{card.id}" for card in player.bird_hand]


@power_choices(20, "select_bird")
def _get_power_20_bird_choices(
    state: GameState, execution: PowerExecution
) -> List[str]:
    """Generate bird selection actions for Power 20."""
    valid_bird_ids = execution.context.get("valid_bird_ids", [])
    return [f"select_bird_{bird_id}" for bird_id in valid_bird_ids]


@power_choices(21, "select_die")
def _get_power_21_die_choices(state: GameState, execution: PowerExecution) -> List[str]:
    """Generate die selection actions for Power 21."""
    return get_collect_food_actions(state)
