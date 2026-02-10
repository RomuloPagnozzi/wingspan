from typing import Callable

from ..core import (
    GameState,
    PowerExecution,
    Action,
    SimpleAction,
    IdAction,
    NameAction,
    SelectDieAction,
    TradeAction,
    EggMapAction,
    FoodMapAction,
    frozen_map,
)
from ..utils import (
    get_egg_distribution_combinations,
    get_food_gain_combinations,
    get_valid_birds_for_eggs,
    get_collect_food_actions,
)

ChoiceGenerator = Callable[[GameState, PowerExecution], list[Action]]
_POWER_CHOICE_GENERATORS: dict[tuple[int, str], ChoiceGenerator] = {}


def power_choices(power_id: int, phase: str):
    """Decorator to register a power choice generator."""

    def decorator(func: ChoiceGenerator) -> ChoiceGenerator:
        _POWER_CHOICE_GENERATORS[(power_id, phase)] = func
        return func

    return decorator


def get_power_choice_generator(power_id: int, phase: str) -> ChoiceGenerator | None:
    """Get the choice generator for a specific power and phase."""
    return _POWER_CHOICE_GENERATORS.get((power_id, phase))


# =============================================================================
# Power 2: All players lay eggs on nest type
# =============================================================================


@power_choices(2, "choices")
def _get_power_2_choices(state: GameState, execution: PowerExecution) -> list[Action]:
    """Generate egg distribution choices for power 2."""
    nest_type = execution.context["nest_type"]
    activator = execution.context["activator"]
    player = state.players[state.current_player_index]
    amount = 2 if state.current_player_index == activator else 1

    valid_birds = get_valid_birds_for_eggs(player, nest_type)
    birds_capacity = {b.id: b.card.egg_limit - b.state.eggs for b in valid_birds}
    combos = get_egg_distribution_combinations(birds_capacity, amount)
    return [EggMapAction("activate_eggs", frozen_map(c)) for c in combos]


# =============================================================================
# Power 4: Discard resource to gain resource/cards
# =============================================================================


@power_choices(4, "select_discard")
def _get_power_4_discard_choices(
    state: GameState,
    execution: PowerExecution,
) -> list[Action]:
    """Generate discard choices for power 4."""
    discard_type = execution.context["discard_type"]
    gain_type = execution.context["gain_type"]
    current_player = state.players[state.current_player_index]

    if discard_type == "egg":
        actions: list[Action] = []
        for row in current_player.board:
            for spot in row:
                if spot.bird is not None and spot.bird.state.eggs > 0:
                    if gain_type == "wild" and spot.bird.id == execution.bird_id:
                        continue
                    actions.append(IdAction("discard_egg_from", spot.bird.id))
        return actions
    else:
        return [NameAction("discard_food", discard_type)]


@power_choices(4, "select_gain")
def _get_power_4_gain_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate resource gain choices for power 4 (wild resource)."""
    gain_qty = execution.context["gain_qty"]
    combos = get_food_gain_combinations(gain_qty)
    return [FoodMapAction("gain_food_combo", frozen_map(combo)) for combo in combos]


# =============================================================================
# Power 5: Draw cards or bonus cards
# =============================================================================


@power_choices(5, "select_bonus")
def _get_power_5_bonus_choices(_, execution: PowerExecution) -> list[Action]:
    """Get choices for power 5 bonus card selection."""
    drawn_ids = execution.context.get("bonus_options", [])
    return [IdAction("power_5_bonus", id) for id in drawn_ids]


# =============================================================================
# Power 6: Draw N+1 cards, all players select one
# =============================================================================


@power_choices(6, "select_card")
def _get_power_6_card_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate card selection choices for power 6."""
    available_ids = execution.context.get("available_cards", [])
    return [IdAction("select_card", id) for id in available_ids]


# =============================================================================
# Power 7: Each player gains 1 die from birdfeeder
# =============================================================================


@power_choices(7, "choose_starting_player")
def _get_power_7_starting_player_choices(state: GameState, _) -> list[Action]:
    """Generate player selection actions for Power 7."""
    num_players = len(state.players)
    return [IdAction("choose_player", i) for i in range(num_players)]


@power_choices(7, "select_die")
def _get_power_7_die_choices(state: GameState, _) -> list[Action]:
    """Generate die selection for Power 7."""
    return get_collect_food_actions(state)


# =============================================================================
# Power 8: Gain food with optional caching
# =============================================================================


@power_choices(8, "select_food_type")
def _get_power_8_food_type_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate food type choices from available feeder foods."""
    available_foods = execution.context.get("available_foods", [])
    return [NameAction("select_food_type", food) for food in available_foods]


@power_choices(8, "select_die")
def _get_power_8_die_choices(
    state: GameState,
    execution: PowerExecution,
) -> list[Action]:
    """Generate die choices for selected food type."""
    food_type = execution.context.get("food_type")
    all_actions = get_collect_food_actions(state)

    if not food_type:
        return all_actions

    filtered_actions: list[Action] = []
    for action in all_actions:
        if isinstance(action, SimpleAction) and action.type == "reroll_all":
            filtered_actions.append(action)
        elif isinstance(action, SelectDieAction) and action.food_type == food_type:
            filtered_actions.append(action)

    return filtered_actions


@power_choices(8, "choose_cache")
def _get_power_8_cache_choices(_, __) -> list[Action]:
    """Generate cache vs supply choices."""
    return [SimpleAction("cache_food"), SimpleAction("supply_food")]


# =============================================================================
# Power 9: Move bird to another habitat
# =============================================================================


@power_choices(9, "select_habitat")
def _get_power_9_habitat_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate habitat selection actions for Power 9."""
    valid_habitats = execution.context.get("valid_habitats", [])
    return [NameAction("select_habitat", habitat) for habitat in valid_habitats]


# =============================================================================
# Power 10: Lay eggs on birds
# =============================================================================


@power_choices(10, "select_bird")
def _get_power_10_bird_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate bird selection actions for Power 10."""
    valid_bird_ids = execution.context.get("valid_bird_ids", [])
    return [IdAction("select_bird", bird_id) for bird_id in valid_bird_ids]


# =============================================================================
# Power 13: Give resources to players with fewest birds in habitat
# =============================================================================


@power_choices(13, "select_die")
def _get_power_13_die_choices(state: GameState, _) -> list[Action]:
    """Generate die selection actions for Power 13."""
    return get_collect_food_actions(state)


# =============================================================================
# Power 14: Repeat another bird's power in this habitat
# =============================================================================


@power_choices(14, "select_bird")
def _get_power_14_bird_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate bird selection actions for Power 14."""
    eligible_birds = execution.context.get("eligible_birds", [])
    return [IdAction("select_bird", bird["bird_id"]) for bird in eligible_birds]


# =============================================================================
# Power 16: Trade food for another type
# =============================================================================


@power_choices(16, "select_trade")
def _get_power_16_trade_choices(state: GameState, _) -> list[Action]:
    """Generate trade actions for Power 16."""
    all_food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    current_player = state.players[state.current_player_index]
    player_food_types = list(current_player.food.keys())
    actions: list[Action] = []
    for from_type in player_food_types:
        for to_type in all_food_types:
            if to_type != from_type:
                actions.append(TradeAction(from_type, to_type))
    return actions


# =============================================================================
# Power 17: Tuck card for bonus
# =============================================================================


@power_choices(17, "select_card")
def _get_power_17_card_choices(state: GameState, _) -> list[Action]:
    """Generate card selection for Power 17."""
    current_player = state.players[state.current_player_index]
    return [IdAction("tuck_card", id) for id in current_player.bird_hand]


@power_choices(17, "select_food")
def _get_power_17_food_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate food selection for Power 17."""
    food_types = execution.context.get("food_types", [])
    return [NameAction("select_food", food) for food in food_types]


# =============================================================================
# Power 18: Pink - gain resource when opponent plays in habitat
# =============================================================================


@power_choices(18, "select_card")
def _get_power_18_card_choices(
    state: GameState, execution: PowerExecution
) -> list[Action]:
    """Generate card selection for Power 18."""
    player = state.players[execution.player_index]
    return [IdAction("tuck_card", id) for id in player.bird_hand]


# =============================================================================
# Power 20: Pink - lay egg when opponent lays eggs
# =============================================================================


@power_choices(20, "select_bird")
def _get_power_20_bird_choices(_, execution: PowerExecution) -> list[Action]:
    """Generate bird selection actions for Power 20."""
    valid_bird_ids = execution.context.get("valid_bird_ids", [])
    return [IdAction("select_bird", bird_id) for bird_id in valid_bird_ids]


# =============================================================================
# Power 21: Pink - gain die when opponent's predator succeeds
# =============================================================================


@power_choices(21, "select_die")
def _get_power_21_die_choices(state: GameState, _) -> list[Action]:
    """Generate die selection actions for Power 21."""
    return get_collect_food_actions(state)
