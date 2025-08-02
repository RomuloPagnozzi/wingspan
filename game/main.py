from .data import GameState, Action, initiate_state, Spot, Player, Bird, roll_feeder
from itertools import (
    cycle,
    islice,
    combinations_with_replacement,
    combinations,
    product,
)
from typing import List, Optional, Dict


def _find_leftmost_empty_spot(board_row: List[Spot]) -> Optional[Spot]:
    """Find the leftmost empty spot in a board row."""
    for spot in board_row:
        if spot.bird is None:
            return spot
    return None


def get_player_index(s: GameState) -> int:
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


# def get_actions(s: GameState, player: Player) -> List[Action]:
#     actions = []
#     if not player.action_cubes:
#         return actions

#     if player.bird_hand:
#         actions.extend(_get_play_bird_actions(player))

#     available_egg_capacity = any(
#         [
#             spot.bird.eggs < spot.bird.egg_limit
#             for row in player.board
#             for spot in row
#             if spot.bird is not None
#         ]
#     )
#     if available_egg_capacity:
#         actions.extend(_get_lay_eggs_actions(player))

#     # actions.extend(_get_gain_food_actions(player, s))

#     # Draw birds
#     return actions


# def _get_gain_food_actions(player: Player, s: GameState) -> List[Action]:
#     food_spot: Optional[Spot] = _find_leftmost_empty_spot(player.board[0])
#     if food_spot:
#         resource_amount = food_spot.resource_amount
#         extra_resource = food_spot.extra_resource
#     else:
#         resource_amount = 3
#         extra_resource = True

#     if not player.bird_hand:
#         extra_resource = False

#     available_food = len(s.feeder)
#     # unique_tokens = set(token for dice in s.feeder.values() for token in dice)
#     # if unique_tokens == 1:
#     #     reroll = True

#     if resource_amount <= available_food:
#         actions = []
#         food_combinations = _get_food_combinations(s.feeder, resource_amount)
#         for comb in food_combinations:
#             actions.append(Action("gain_food", {"food": comb}))

#     return actions


def _get_lay_eggs_actions(player: Player) -> List[Action]:
    egg_spot: Optional[Spot] = _find_leftmost_empty_spot(player.board[1])
    if egg_spot:
        resource_amount = egg_spot.resource_amount
        extra_resource = egg_spot.extra_resource
    else:
        resource_amount = 4
        extra_resource = True

    if not player.food:
        extra_resource = False

    available_birds = {
        spot.bird.id: spot.bird.egg_limit - spot.bird.eggs
        for row in player.board
        for spot in row
        if spot.bird and spot.bird.egg_limit > spot.bird.eggs
    }

    egg_distribution_combinations = _get_egg_distribution_combinations(
        available_birds, resource_amount
    )

    actions = []
    for combination in egg_distribution_combinations:
        actions.append(Action("lay_egg", {"birds": combination}))

    if extra_resource:
        extra_egg_distribution_combinations = _get_egg_distribution_combinations(
            available_birds, resource_amount + 1
        )
        available_food_types = [
            food for food, amount in player.food.items() if amount > 0
        ]
        for food in available_food_types:
            for combination in extra_egg_distribution_combinations:
                actions.append(
                    Action("lay_egg", {"birds": combination, "food_cost": {food: 1}})
                )

    return actions


def _get_play_bird_actions(player: Player) -> List[Action]:
    actions = []

    # Get leftmost empty spot for each habitat that player can afford egg cost
    available_spots = [
        next((spot for spot in row if spot.bird is None), None) for row in player.board
    ]
    played_birds = [
        spot.bird for row in player.board for spot in row if spot.bird is not None
    ]
    available_eggs = sum(bird.eggs for bird in played_birds) if played_birds else 0
    available_spots = [
        spot
        for spot in available_spots
        if spot is not None and spot.egg_cost <= available_eggs
    ]

    if not available_spots:
        return actions

    # Get birds that can be played in available habitats and are affordable
    available_habitats = set(spot.habitat for spot in available_spots)
    birds_to_play = [
        bird
        for bird in player.bird_hand
        if set(bird.habitats).intersection(available_habitats)
        and _is_bird_affordable(bird, player.food)
    ]

    if not birds_to_play:
        return actions

    potential_pairs = [
        (bird, spot)
        for bird in birds_to_play
        for spot in available_spots
        if spot.habitat in bird.habitats
    ]

    for bird, spot in potential_pairs:
        cost_payment_combinations = _get_food_payment_combinations(bird, player.food)

        if spot.egg_cost == 0:
            for c in cost_payment_combinations:
                actions.append(
                    Action(
                        "play_bird",
                        {
                            "bird_id": bird.id,
                            "spot": (spot.row, spot.col),
                            "food_cost": c,
                        },
                    )
                )

        if spot.egg_cost > 0:
            birds_with_eggs = {
                bird.id: bird.eggs for bird in played_birds if bird.eggs > 0
            }
            egg_payment_combinations = _get_egg_distribution_combinations(
                birds_with_eggs, spot.egg_cost
            )
            for c in cost_payment_combinations:
                for e in egg_payment_combinations:
                    actions.append(
                        Action(
                            "play_bird",
                            {
                                "bird_id": bird.id,
                                "spot": (spot.row, spot.col),
                                "food_cost": c,
                                "egg_cost": e,
                            },
                        )
                    )

    return actions


def _is_bird_affordable(bird: Bird, food: Dict[str, int]) -> bool:
    if not bird.cost:
        return True

    total_food = sum(food.values())

    for cost in bird.cost:
        if all(
            food.get(type, 0) >= amount
            for type, amount in cost.items()
            if type != "wild"
        ):
            if total_food >= sum(cost.values()):
                return True

    return False


def _get_egg_distribution_combinations(
    birds: Dict[int, int], egg_cost: int
) -> List[Dict[int, int]]:
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


def _get_food_payment_combinations(
    bird: Bird, food: Dict[str, int]
) -> List[Dict[str, int]]:
    if not bird.cost:
        return [{}]
    possible_payments = []

    for cost in bird.cost:
        if "wild" not in cost.keys():
            if all(
                food.get(food_type, 0) >= amount for food_type, amount in cost.items()
            ):
                if cost not in possible_payments:
                    possible_payments.append(cost)
            continue

        wild_count = cost["wild"]
        non_wild_cost = {k: v for k, v in cost.items() if k != "wild"}
        available_food_types = [
            food_type for food_type, amount in food.items() if amount > 0
        ]
        wild_combinations = combinations_with_replacement(
            available_food_types, wild_count
        )  # TODO: Check if with_replacement is needed

        for wild_combination in wild_combinations:
            combined_food = non_wild_cost.copy()
            for food_type in wild_combination:
                combined_food[food_type] = combined_food.get(food_type, 0) + 1

            if all(
                food.get(food_type, 0) >= amount
                for food_type, amount in combined_food.items()
            ):
                if combined_food not in possible_payments:
                    possible_payments.append(combined_food)

    return possible_payments


def _get_food_combinations(feeder: Dict, resource_amount: int) -> List:
    dice_choices = list(combinations(feeder.keys(), resource_amount))
    unique_combinations = []
    seen_resources = set()

    for dice in dice_choices:
        token_list = [feeder[token] for token in dice]
        token_combinations = list(product(*token_list))

        for comb in token_combinations:
            resource_comb = tuple(sorted(comb))

            if resource_comb not in seen_resources:
                seen_resources.add(resource_comb)
                comb_dict = {dice[i]: comb[i] for i in range(resource_amount)}
                unique_combinations.append(comb_dict)

    return unique_combinations


# Player chooses to keep up to 5 birds, discarding 1 food token for each
# Player chooses to keep 1 bonus card


# S0
# Player - return which player to move in state s DONE
# Action - return legal moves in state s
# Result - return state after action a taken in state s
# Terminal - checks if state s is a terminal state
# Utility - final numerical value for terminal state s

from .helper import print_board_resources, print_board_birds, print_board_bird_stats

# s: GameState = initiate_state(2)
# s.players[0].board[0][0].bird = s.bird_deck.pop()
# s.players[0].board[0][1].bird = s.bird_deck.pop()
# s.players[0].board[0][2].bird = s.bird_deck.pop()
# s.players[0].board[0][3].bird = s.bird_deck.pop()
# s.players[0].board[0][4].bird = s.bird_deck.pop()
# s.players[0].board[1][0].bird = s.bird_deck.pop()
# s.players[0].board[1][0].bird.eggs = 1
# s.players[0].board[1][1].bird = s.bird_deck.pop()
# s.players[0].board[1][1].bird.stashed_food = 3
# s.players[0].board[1][1].bird.tucked_cards = 2
# print_board_birds(s.players[0].board)
# print_board_bird_stats(s.players[0].board)
# print(s.players[0].board[1][1].bird)
# print("birds")
# played_birds = [spot.bird for row in s.players[0].board for spot in row if spot.bird]
# for bird in played_birds:
#     print(bird)
# print("actions")
# actions = get_actions(s, s.players[0])
# for action in actions:
#     print(action)
# print(len(actions))

# s: GameState = initiate_state(2)
# s.players[0].board[0][0].bird = s.bird_deck.pop()
# s.players[0].board[0][1].bird = s.bird_deck.pop()
# actions = get_actions(s, s.players[0])
# for action in actions:
#     print(action)

# s: GameState = initiate_state(2)
# f = s.feeder
# print(set(x for l in f.values() for x in l))
# unique = print(f.values())
# print(unique)

from .engine import get_actions, transition_state

print("=" * 60)
print("COMPREHENSIVE GAIN_FOOD TESTING")
print("=" * 60)

# Test 1: Basic gain_food with no extra resource available
print("\n=== TEST 1: NO EXTRA RESOURCE (should go directly to collecting_food) ===")
s1 = initiate_state(2)
current_player = s1.players[s1.current_player_index]

print(f"Current player: {s1.current_player_index}")
print(f"Birds in hand: {len(current_player.bird_hand)}")
print(
    f"Forest spot pattern: {[(i, spot.extra_resource) for i, spot in enumerate(current_player.board[0])]}"
)

s1_after = transition_state(s1, "gain_food")
print(f"Decision phase: {s1_after.decision_phase}")
print(f"Decision data: {s1_after.decision_data}")
print(f"Available actions: {get_actions(s1_after)[:3]}...")  # Show first 3

# Test food collection
if s1_after.decision_phase == "collecting_food":
    selected_action = get_actions(s1_after)[0]
    print(f"Selecting: {selected_action}")
    s1_final = transition_state(s1_after, selected_action)
    print(
        f"After selection - Phase: {s1_final.decision_phase}, Data: {s1_final.decision_data}"
    )

# Test 2: With extra resource available
print("\n=== TEST 2: EXTRA RESOURCE AVAILABLE (should go to extra_food_decision) ===")
s2 = initiate_state(2)
current_player = s2.players[s2.current_player_index]

# Place bird in position 0 to make position 1 (extra_resource=True) the leftmost empty
current_player.board[0][0].bird = s2.bird_deck.pop()

print(f"Current player: {s2.current_player_index}")
print(f"Birds in hand: {len(current_player.bird_hand)}")
print(f"Bird placed at position 0: {current_player.board[0][0].bird is not None}")
print(f"Position 1 extra_resource: {current_player.board[0][1].extra_resource}")

s2_after = transition_state(s2, "gain_food")
print(f"Decision phase: {s2_after.decision_phase}")
print(f"Decision data: {s2_after.decision_data}")
print(f"Available actions: {get_actions(s2_after)}")

# Test both paths
if s2_after.decision_phase == "extra_food_decision":
    # Test skip trade path
    print(f"\n--- Testing SKIP_TRADE path ---")
    s2_skip = transition_state(s2_after, "skip_trade")
    print(f"Phase: {s2_skip.decision_phase}, Food needed: {s2_skip.decision_data}")

    # Test trade bird path
    print(f"\n--- Testing TRADE_BIRD path ---")
    s2_trade = transition_state(s2_after, "trade_bird")
    print(f"Phase: {s2_trade.decision_phase}")
    print(f"Available birds to discard: {get_actions(s2_trade)[:3]}...")  # Show first 3

    # Test discarding a bird
    if get_actions(s2_trade):
        discard_action = get_actions(s2_trade)[0]
        print(f"Discarding: {discard_action}")
        s2_discard = transition_state(s2_trade, discard_action)
        print(f"After discard - Phase: {s2_discard.decision_phase}")
        print(f"Food needed (should be base+1): {s2_discard.decision_data}")
        print(
            f"Birds in hand (should be 4): {len(s2_discard.players[s2_discard.current_player_index].bird_hand)}"
        )

print("\n" + "=" * 60)
print("TESTING COMPLETE")
print("=" * 60)
