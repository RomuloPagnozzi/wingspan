from typing import List, Dict
from .data import Spot, Player, Bird


def find_leftmost_empty_spot(board_row: List[Spot]) -> Spot | None:
    """Find the leftmost empty spot in a board row."""
    for spot in board_row:
        if spot.bird is None:
            return spot
    return None


def is_bird_affordable(bird: Bird, food: Dict[str, int]) -> bool:
    """Checks if bird can be paid by player's food supply."""
    if not bird.cost:
        return True

    for cost in bird.cost:
        cost_copy = cost.copy()
        tokens_needed = cost_copy.pop("wild", 0)
        available_for_trading = food.copy()

        for food_type, amount in cost_copy.items():
            if amount == 0:
                continue

            available = available_for_trading.get(food_type, 0)
            if available >= amount:
                available_for_trading[food_type] -= amount
            else:
                if available > 0:
                    available_for_trading[food_type] = 0
                tokens_needed += (amount - available) * 2

        if sum(available_for_trading.values()) >= tokens_needed:
            return True

    return False


def can_play_a_bird(player: Player) -> bool:
    """Check if player has at least one playable bird."""
    if not player.bird_hand:
        return False

    empty_spots = [find_leftmost_empty_spot(row) for row in player.board]
    if not empty_spots:
        return False

    played_birds = [
        spot.bird for row in player.board for spot in row if spot.bird is not None
    ]
    available_eggs = 0
    if played_birds:
        available_eggs += sum(bird.eggs for bird in played_birds)

    available_spots = [
        spot
        for spot in empty_spots
        if spot is not None and spot.egg_cost <= available_eggs
    ]
    if not available_spots:
        return False

    available_habitats = set(spot.habitat for spot in available_spots)
    for bird in player.bird_hand:
        if set(bird.habitats).intersection(available_habitats) and is_bird_affordable(
            bird, player.food
        ):
            return True
    return False
