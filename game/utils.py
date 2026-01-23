from typing import List, Dict, Tuple, Generator
from .data import Spot, Player, Bird, GameState, get_bird_power, PinkTrigger
from itertools import (
    combinations_with_replacement,
    product,
    combinations,
    cycle,
    islice,
)
import random


def reshuffle_discard_into_deck(state: GameState) -> None:
    """Shuffle discarded birds back into the deck."""
    if state.discarded_birds:
        state.bird_deck.extend(state.discarded_birds)
        state.discarded_birds.clear()
        random.shuffle(state.bird_deck)


def ensure_bird_deck(state: GameState, count: int = 1) -> int:
    """Ensure deck has cards, reshuffling discard if needed. Returns available count."""
    if len(state.bird_deck) < count and state.discarded_birds:
        reshuffle_discard_into_deck(state)
    return len(state.bird_deck)


def get_available_bird_cards(state: GameState) -> int:
    """Return total cards available (deck + discard, excluding tray)."""
    return len(state.bird_deck) + len(state.discarded_birds)


def refresh_bird_tray(state: GameState) -> None:
    """Top up bird tray to 3 cards without discarding existing cards."""
    while len(state.bird_tray) < 3:
        ensure_bird_deck(state, 1)
        if not state.bird_deck:
            break
        state.bird_tray.append(state.bird_deck.pop())


def get_current_player_index(s: GameState) -> int:
    """Returns current player index."""
    players = s.players
    first_player_index = next(
        i for i, player in enumerate(players) if player.first_player
    )
    all_same_cubes = all(
        player.action_cubes == players[0].action_cubes for player in players
    )

    if all_same_cubes:
        return first_player_index

    first_player_actions = players[first_player_index].action_cubes
    cycle_iterator = islice(cycle(enumerate(players)), first_player_index, None, 1)
    index, player = next(islice(cycle_iterator, None, None))
    while player.action_cubes == first_player_actions:
        index, player = next(islice(cycle_iterator, None, None))
    return index


def find_leftmost_empty_spot(board_row: List[Spot]) -> Spot | None:
    """Find the leftmost empty spot in a board row."""
    for spot in board_row:
        if spot.bird is None:
            return spot
    return None


def can_play_a_bird(player: Player) -> bool:
    """Check if player has at least one playable bird."""
    try:
        next(generate_playable_bird_spots(player))
        return True
    except StopIteration:
        return False


def generate_playable_bird_spots(
    player: Player,
) -> Generator[Tuple[Bird, Spot], None, None]:
    """Generator that yields all valid (bird, spot) combinations."""
    if not player.bird_hand:
        return

    empty_spots: List[Spot] = []
    for row in player.board:
        spot = find_leftmost_empty_spot(row)
        if spot is not None:
            empty_spots.append(spot)

    if not empty_spots:
        return

    played_birds = [
        spot.bird for row in player.board for spot in row if spot.bird is not None
    ]
    available_eggs = sum(bird.eggs for bird in played_birds) if played_birds else 0

    available_spots = [spot for spot in empty_spots if spot.egg_cost <= available_eggs]

    if not available_spots:
        return

    for bird in player.bird_hand:
        if not can_afford_bird(bird.cost, player.food):
            continue

        for spot in available_spots:
            if spot.habitat in bird.habitats:
                yield (bird, spot)


def get_egg_payment_combinations(
    birds: Dict[int, int], egg_cost: int
) -> List[Dict[int, int]]:
    """Generate all valid ways to pay egg cost using available eggs from birds."""

    if egg_cost <= 0:
        raise ValueError(f"Invalid egg cost: {egg_cost}. Must be positive.")

    if not birds:
        raise ValueError("No birds with eggs available to pay egg cost.")

    if sum(birds.values()) < egg_cost:
        raise ValueError(
            f"Not enough eggs available. Need {egg_cost}, have {sum(birds.values())}"
        )

    combinations = []

    def find_combinations(remaining, combination, index):
        if remaining == 0:
            combinations.append(combination.copy())
            return

        for i in range(index, len(birds)):
            id, amount = list(birds.items())[i]
            for count in range(1, amount + 1):
                combination[id] = count
                find_combinations(remaining - count, combination, i + 1)
                del combination[id]

    find_combinations(egg_cost, {}, 0)
    return combinations


def get_egg_distribution_combinations(
    birds_capacity: Dict[int, int], eggs_to_distribute: int
) -> List[Dict[int, int]]:
    """Generate all valid ways to distribute eggs to birds based on their available capacity."""

    if eggs_to_distribute <= 0:
        raise ValueError(
            f"Invalid eggs to distribute: {eggs_to_distribute}. Must be positive."
        )

    if not birds_capacity:
        raise ValueError("No birds available to receive eggs.")

    available_birds = {
        bird_id: capacity
        for bird_id, capacity in birds_capacity.items()
        if capacity > 0
    }

    if not available_birds:
        raise ValueError("No birds have available egg capacity.")

    total_capacity = sum(available_birds.values())

    if eggs_to_distribute >= total_capacity:
        return [dict(available_birds)]

    combinations = []
    bird_ids = list(available_birds.keys())

    def find_distributions(
        remaining_eggs: int, distribution: Dict[int, int], bird_index: int
    ) -> None:
        if bird_index == len(bird_ids):
            if remaining_eggs == 0:
                combinations.append(dict(distribution))
            return

        bird_id = bird_ids[bird_index]
        capacity = available_birds[bird_id]
        max_eggs_for_bird = min(capacity, remaining_eggs)
        remaining_capacity = sum(
            available_birds[bird_ids[i]] for i in range(bird_index + 1, len(bird_ids))
        )

        for eggs_to_bird in range(max_eggs_for_bird + 1):
            remaining_after = remaining_eggs - eggs_to_bird

            if remaining_after <= remaining_capacity:
                if eggs_to_bird > 0:
                    distribution[bird_id] = eggs_to_bird
                find_distributions(remaining_after, distribution, bird_index + 1)
                if eggs_to_bird > 0:
                    del distribution[bird_id]

    find_distributions(eggs_to_distribute, {}, 0)
    return combinations


def can_afford_bird(
    cost_options: List[Dict[str, int]], resources: Dict[str, int]
) -> bool:
    """Check if we can afford a bird using any of its cost options."""
    try:
        next(generate_food_payments(cost_options, resources))
        return True
    except StopIteration:
        return False


def generate_food_payments(
    cost_options: List[Dict[str, int]], resources: Dict[str, int]
) -> Generator[Dict[str, int], None, None]:
    """Generator that yields all valid ways to pay bird food cost with available resources."""
    if not cost_options:
        yield {}
        return

    seen_payments = set()
    for cost_option in cost_options:
        for payment in _generate_food_payments_for_cost_option(cost_option, resources):
            payment_key = frozenset(payment.items())
            if payment_key not in seen_payments:
                seen_payments.add(payment_key)
                yield payment


def _generate_food_payments_for_cost_option(
    cost: Dict[str, int], resources: Dict[str, int]
) -> Generator[Dict[str, int], None, None]:
    """Generate all valid ways to pay a single food cost option with available resources."""
    remaining_cost = cost.copy()
    remaining_resources = resources.copy()

    wild_cost = remaining_cost.pop("wild", 0)

    exact_payment = {}
    for food_type in list(remaining_cost.keys()):
        if food_type in remaining_resources:
            matches_used = min(
                remaining_cost[food_type], remaining_resources[food_type]
            )
            if matches_used > 0:
                exact_payment[food_type] = matches_used
                remaining_cost[food_type] -= matches_used
                remaining_resources[food_type] -= matches_used

                if remaining_cost[food_type] == 0:
                    del remaining_cost[food_type]
                if remaining_resources[food_type] == 0:
                    del remaining_resources[food_type]

    if remaining_cost:
        yield from _generate_2_to_1_trade_combinations(
            remaining_cost, remaining_resources, exact_payment, wild_cost
        )
    elif wild_cost > 0:
        yield from _generate_wild_payments(
            exact_payment, remaining_resources, wild_cost
        )
    else:
        yield exact_payment


def _generate_2_to_1_trade_combinations(
    remaining_cost: Dict[str, int],
    remaining_resources: Dict[str, int],
    exact_payment: Dict[str, int],
    wild_cost: int,
) -> Generator[Dict[str, int], None, None]:
    """Generate all valid 2:1 trade combinations for remaining costs."""

    total_units_needed = sum(remaining_cost.values())

    tradeable_foods = [
        food for food, amount in remaining_resources.items() if amount >= 2
    ]

    if not tradeable_foods:
        return

    for trade_assignment in product(tradeable_foods, repeat=total_units_needed):

        trade_usage = {}
        for food in trade_assignment:
            trade_usage[food] = trade_usage.get(food, 0) + 2

        valid = True
        for food_type, needed in trade_usage.items():
            if remaining_resources.get(food_type, 0) < needed:
                valid = False
                break

        if not valid:
            continue

        payment = exact_payment.copy()
        for food_type, used in trade_usage.items():
            payment[food_type] = payment.get(food_type, 0) + used

        resources_after_trades = remaining_resources.copy()
        for food_type, used in trade_usage.items():
            resources_after_trades[food_type] -= used
            if resources_after_trades[food_type] == 0:
                del resources_after_trades[food_type]

        if wild_cost > 0:
            yield from _generate_wild_payments(
                payment, resources_after_trades, wild_cost
            )
        else:
            yield payment


def _generate_wild_payments(
    base_payment: Dict[str, int], remaining: Dict[str, int], wild_count: int
) -> Generator[Dict[str, int], None, None]:
    """Generate all ways to pay wild cost with remaining resources."""
    available_foods = []
    for food_type, amount in remaining.items():
        available_foods.extend([food_type] * amount)

    if len(available_foods) < wild_count:
        return

    for wild_selection in combinations_with_replacement(
        sorted(set(available_foods)), wild_count
    ):
        wild_usage = {}
        for food in wild_selection:
            wild_usage[food] = wild_usage.get(food, 0) + 1

        valid = True
        for food_type, needed in wild_usage.items():
            if remaining.get(food_type, 0) < needed:
                valid = False
                break

        if valid:
            payment = base_payment.copy()
            for food_type, count in wild_usage.items():
                payment[food_type] = payment.get(food_type, 0) + count
            yield payment


def get_card_draw_combinations(
    cards_needed: int,
    available_tray_bird_ids: List[int],
    max_deck_cards: int | None = None,
) -> List[Dict]:
    """Return all valid ways to draw cards from mix of tray and deck. Allows partial draw"""

    if cards_needed <= 0:
        raise ValueError("Number of cards must be positive")

    if max_deck_cards is None:
        max_deck_cards = cards_needed

    total_available = len(available_tray_bird_ids) + max_deck_cards

    if total_available == 0:
        raise ValueError(
            f"Cannot draw cards: no cards available (tray empty, deck empty). "
            f"This should have been prevented by the action gate check."
        )

    actual_cards_needed = min(cards_needed, total_available)

    combinations_list = []
    max_from_tray = min(actual_cards_needed, len(available_tray_bird_ids))

    for tray_count in range(max_from_tray + 1):
        deck_count = actual_cards_needed - tray_count

        if deck_count > max_deck_cards:
            continue

        if tray_count == 0:
            combinations_list.append({"tray_birds": [], "deck_cards": deck_count})
        else:
            for tray_bird_ids in combinations(available_tray_bird_ids, tray_count):
                combinations_list.append(
                    {"tray_birds": list(tray_bird_ids), "deck_cards": deck_count}
                )

    return combinations_list


def get_initial_card_combinations(
    bird_ids: List[int],
    bonus_ids: List[int],
) -> List[Dict]:
    """Return all valid combinations of birds and bonus cards for setup."""
    if len(bonus_ids) != 2 or len(bird_ids) != 5:
        raise ValueError(
            "Player must have exactly 2 bonus and 5 bird cards during setup"
        )

    combinations_list = []

    for bonus_id in bonus_ids:
        for bird_count in range(len(bird_ids) + 1):
            for bird_combination in combinations(bird_ids, bird_count):
                combinations_list.append(
                    {"kept_birds": list(bird_combination), "kept_bonus": bonus_id}
                )

    return combinations_list


def get_food_discard_combinations(
    food: Dict[str, int],
    amount_needed: int,
) -> List[Dict[str, int]]:
    """Return all valid ways to discard the required amount of food tokens."""
    if amount_needed <= 0:
        raise ValueError("Amount needed must be positive")

    if sum(food.values()) < amount_needed:
        raise ValueError(
            f"Not enough food to discard. Need {amount_needed}, have {sum(food.values())}"
        )

    available_food = []
    for food_type, count in food.items():
        available_food.extend([food_type] * count)

    combinations_list = []

    for food_combination in combinations(available_food, amount_needed):
        discard_dict = {}
        for food_type in food_combination:
            discard_dict[food_type] = discard_dict.get(food_type, 0) + 1

        if discard_dict not in combinations_list:
            combinations_list.append(discard_dict)

    return combinations_list


def get_valid_birds_for_eggs(player: Player, nest_type: str) -> List[Bird]:
    """Get all birds on player's board that match nest type and have egg capacity."""
    valid_birds = []

    for row in player.board:
        for spot in row:
            if (
                spot.bird is not None
                and spot.bird.nest == nest_type
                and spot.bird.eggs < spot.bird.egg_limit
            ):
                valid_birds.append(spot.bird)

    return valid_birds


def get_triggered_powers(
    player: Player, color: str, habitat: str | None = None, spot: Spot | None = None
) -> List[Dict]:
    """Get powers whose trigger conditions are met for a specific color."""
    triggered_powers = []

    if spot is not None:
        spots_to_check = [spot]
    elif habitat is not None:
        habitat_map = {"forest": 0, "grassland": 1, "wetland": 2}
        if habitat not in habitat_map:
            return triggered_powers
        habitat_row = player.board[habitat_map[habitat]]
        spots_to_check = list(reversed(habitat_row))
    else:
        return triggered_powers

    for spot in spots_to_check:
        if spot.bird is not None:
            power_data = get_bird_power(spot.bird.id)

            if (
                power_data
                and power_data.get("color") == color
                and power_data.get("data")
                and "id" in power_data["data"]
            ):

                triggered_powers.append(
                    {
                        "bird_id": spot.bird.id,
                        "power_id": power_data["data"]["id"],
                        "power_data": power_data,
                        "spot": spot,
                    }
                )

    return triggered_powers


def _pink_power_matches_trigger(
    power_id: int,
    power_data: Dict,
    trigger_type: PinkTrigger,
    context: Dict,
) -> bool:
    """Check if a pink power's trigger matches the current event context."""
    details = power_data.get("data", {}).get("details", {})

    match power_id:
        case 18:
            return trigger_type == PinkTrigger.BIRD_PLAYED and context.get(
                "habitat"
            ) == details.get("habitat")
        case 19:
            return (
                trigger_type == PinkTrigger.GAIN_FOOD
                and context.get("food_type") == "rodent"
            )
        case 20:
            return trigger_type == PinkTrigger.LAY_EGGS
        case 21:
            return trigger_type == PinkTrigger.PREDATOR_SUCCESS
        case _:
            return False


def get_triggered_pink_powers(
    state: GameState,
    trigger_type: PinkTrigger,
    triggering_player_index: int,
    context: Dict | None = None,
) -> List[Dict]:
    """Find pink powers triggered by another player's action."""
    triggered = []
    context = context or {}

    for player_index, player in enumerate(state.players):
        if player_index == triggering_player_index:
            continue

        for row in player.board:
            for spot in row:
                if spot.bird is None:
                    continue

                power_data = get_bird_power(spot.bird.id)
                if not power_data or power_data.get("color") != "pink":
                    continue

                if spot.bird.id in player.used_pink_powers:
                    continue

                power_id = power_data.get("data", {}).get("id")
                if power_id is None:
                    continue

                if _pink_power_matches_trigger(
                    power_id, power_data, trigger_type, context
                ):
                    triggered.append(
                        {
                            "player_index": player_index,
                            "bird_id": spot.bird.id,
                            "power_id": power_id,
                            "power_data": power_data,
                            "spot": spot,
                        }
                    )

    return triggered


def get_food_gain_combinations(quantity: int) -> List[Dict[str, int]]:
    """Generate all valid ways to gain N food tokens from available food types."""
    food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    combinations = []

    def generate_combinations(remaining: int, combo: Dict[str, int], start_index: int):
        if remaining == 0:
            combinations.append(combo.copy())
            return

        for i in range(start_index, len(food_types)):
            food_type = food_types[i]
            for count in range(1, remaining + 1):
                combo[food_type] = count
                generate_combinations(remaining - count, combo, i + 1)
                del combo[food_type]

    generate_combinations(quantity, {}, 0)
    return combinations


def check_round_end(state: GameState) -> bool:
    """Check if all players have used all action cubes."""
    return all(player.action_cubes == 0 for player in state.players)


def get_action_cubes_for_round(round_num: int) -> int:
    """Get starting action cubes for a round (8/7/6/5)."""
    return 9 - round_num


def rotate_first_player(state: GameState) -> None:
    """Pass first player token clockwise."""
    current_idx = next(i for i, p in enumerate(state.players) if p.first_player)
    next_idx = (current_idx + 1) % len(state.players)
    state.players[current_idx].first_player = False
    state.players[next_idx].first_player = True


def restock_bird_tray(state: GameState) -> None:
    """Discard bird tray and draw up to 3 new cards (handles partial)."""
    state.discarded_birds.extend(state.bird_tray)
    state.bird_tray.clear()

    ensure_bird_deck(state, 3)

    cards_to_draw = min(3, len(state.bird_deck))
    state.bird_tray = [state.bird_deck.pop() for _ in range(cards_to_draw)]


def get_first_player_index(state: GameState) -> int:
    """Get index of first player."""
    return next(i for i, p in enumerate(state.players) if p.first_player)


def get_collect_food_actions(state: GameState) -> List[str]:
    """Return possible foods to collect from the bird feeder."""
    actions = []

    for die_index, food_types in state.feeder.items():
        for food_type in food_types:
            actions.append(f"select_die_{die_index}_{food_type}")

    if len(set(tuple(sorted(die_face)) for die_face in state.feeder.values())) == 1:
        actions.append("reroll_all")

    return actions
