from typing import Dict
from .data import Player, Bonus, GameState, ScoringMode


def _count_bonus_birds(bonus: Bonus, player: Player) -> int:
    played_birds = [
        spot.bird for row in player.board for spot in row if spot.bird is not None
    ]

    if not played_birds:
        return 0

    if bonus.valid_birds_ids:
        played_birds_ids = {bird.id for bird in played_birds}
        return len(bonus.valid_birds_ids.intersection(played_birds_ids))

    match bonus.id:
        case 5:
            return len([bird for bird in played_birds if bird.eggs >= 4])
        case 7:
            forest_birds = len(
                [
                    spot.bird
                    for row in player.board
                    for spot in row
                    if spot.habitat == "forest"
                ]
            )
            grassland_birds = len(
                [
                    spot.bird
                    for row in player.board
                    for spot in row
                    if spot.habitat == "grassland"
                ]
            )
            wetland_birds = len(
                [
                    spot.bird
                    for row in player.board
                    for spot in row
                    if spot.habitat == "wetland"
                ]
            )
            return min(forest_birds, grassland_birds, wetland_birds)
        case 17:
            return len([bird for bird in played_birds if bird.eggs >= 1])
        case 23:
            return len(player.bird_hand)
        case _:
            raise NotImplementedError


def score_bonus_card(bonus: Bonus, player: Player) -> int:
    n_birds = _count_bonus_birds(bonus, player)
    if not n_birds:
        return 0
    score_params = bonus.score_params
    if "per_bird" in score_params:
        return score_params["per_bird"] * n_birds
    else:
        if n_birds >= score_params["upper_bound"]:
            return score_params["upper_score"]
        elif n_birds >= score_params["lower_bound"]:
            return score_params["lower_score"]
        return 0


def update_player_scores(player: Player) -> None:
    """Update all score components for a player at end of turn."""
    birds_on_board = [
        spot.bird for row in player.board for spot in row if spot.bird is not None
    ]

    player.score.bird_points = sum(bird.points for bird in birds_on_board)
    player.score.egg_points = sum(bird.eggs for bird in birds_on_board)
    player.score.cached_food = sum(bird.stashed_food for bird in birds_on_board)
    player.score.tucked_cards = sum(bird.tucked_cards for bird in birds_on_board)

    for bonus in player.bonus_hand:
        player.score.bonus_scores[bonus.id] = score_bonus_card(bonus, player)


def _count_eggs_on_nest_type(player: Player, nest_type: str) -> int:
    """Count total eggs on birds with specified nest type."""
    total = 0
    for row in player.board:
        for spot in row:
            if spot.bird is not None and spot.bird.nest == nest_type:
                total += spot.bird.eggs
    return total


def _count_birds_with_eggs_on_nest_type(player: Player, nest_type: str) -> int:
    """Count birds with specified nest type that have at least 1 egg."""
    count = 0
    for row in player.board:
        for spot in row:
            if (
                spot.bird is not None
                and spot.bird.nest == nest_type
                and spot.bird.eggs >= 1
            ):
                count += 1
    return count


def _count_eggs_in_habitat(player: Player, habitat_row: int) -> int:
    """Count total eggs on birds in specified habitat row."""
    total = 0
    for spot in player.board[habitat_row]:
        if spot.bird is not None:
            total += spot.bird.eggs
    return total


def _count_birds_in_habitat(player: Player, habitat_row: int) -> int:
    """Count birds in specified habitat row."""
    count = 0
    for spot in player.board[habitat_row]:
        if spot.bird is not None:
            count += 1
    return count


def _count_total_birds(player: Player) -> int:
    """Count all birds on player's board."""
    count = 0
    for row in player.board:
        for spot in row:
            if spot.bird is not None:
                count += 1
    return count


def _count_sets_of_eggs(player: Player) -> int:
    """Count complete sets of eggs (minimum eggs across all habitats)."""
    eggs_per_habitat = [_count_eggs_in_habitat(player, row) for row in range(3)]
    return min(eggs_per_habitat)


def evaluate_goal(state: GameState, player: Player, goal_name: str) -> int:
    """Evaluate how many items a player has matching the goal criteria."""
    habitat_rows = {"forest": 0, "grassland": 1, "wetland": 2}
    match goal_name:
        case "eggs_in_bowl":
            return _count_eggs_on_nest_type(player, "bowl")
        case "eggs_in_cavity":
            return _count_eggs_on_nest_type(player, "cavity")
        case "eggs_in_ground":
            return _count_eggs_on_nest_type(player, "ground")
        case "eggs_in_platform":
            return _count_eggs_on_nest_type(player, "platform")
        case "bowl_birds_with_egg":
            return _count_birds_with_eggs_on_nest_type(player, "bowl")
        case "cavity_birds_with_egg":
            return _count_birds_with_eggs_on_nest_type(player, "cavity")
        case "ground_birds_with_egg":
            return _count_birds_with_eggs_on_nest_type(player, "ground")
        case "platform_birds_with_egg":
            return _count_birds_with_eggs_on_nest_type(player, "platform")
        case "eggs_in_forest":
            return _count_eggs_in_habitat(player, habitat_rows["forest"])
        case "eggs_in_grassland":
            return _count_eggs_in_habitat(player, habitat_rows["grassland"])
        case "eggs_in_wetland":
            return _count_eggs_in_habitat(player, habitat_rows["wetland"])
        case "birds_in_forest":
            return _count_birds_in_habitat(player, habitat_rows["forest"])
        case "birds_in_grassland":
            return _count_birds_in_habitat(player, habitat_rows["grassland"])
        case "birds_in_wetland":
            return _count_birds_in_habitat(player, habitat_rows["wetland"])
        case "total_birds":
            return _count_total_birds(player)
        case "sets_of_eggs":
            return _count_sets_of_eggs(player)
        case _:
            raise ValueError(f"Unknown goal: {goal_name}")


def _calculate_blue_score(state: GameState, player: Player, goal_name: str) -> int:
    """Calculate blue scoring: 1 point per matching item, max 5."""
    return min(evaluate_goal(state, player, goal_name), 5)


def _calculate_green_scores(
    state: GameState,
    goal_name: str,
    round_num: int,
) -> Dict[int, int]:
    """Calculate green (competitive) scoring with tie-breaking."""
    green_scoring_table = {
        1: [4, 1, 0, 0],
        2: [5, 2, 1, 0],
        3: [6, 3, 2, 0],
        4: [7, 4, 3, 0],
    }
    player_counts = [
        (player.id, evaluate_goal(state, player, goal_name)) for player in state.players
    ]
    player_counts.sort(key=lambda x: x[1], reverse=True)

    round_scores = green_scoring_table[round_num]
    scores: Dict[int, int] = {}
    position = 0

    while position < len(player_counts):
        current_count = player_counts[position][1]

        tied_players = []
        tied_end = position
        while (
            tied_end < len(player_counts)
            and player_counts[tied_end][1] == current_count
        ):
            tied_players.append(player_counts[tied_end][0])
            tied_end += 1

        num_tied = len(tied_players)
        tied_positions = range(position, min(tied_end, len(round_scores)))
        total_tied_score = sum(
            round_scores[p] if p < len(round_scores) else 0 for p in tied_positions
        )
        tied_score = total_tied_score // num_tied

        for player_id in tied_players:
            scores[player_id] = tied_score

        position = tied_end

    return scores


def update_round_goal_scores(state: GameState) -> None:
    """Update round goal scores for all players at end of round."""
    round_index = state.round - 1
    config = state.round_goal_config
    if not config:
        raise ValueError("Empty goal config")
    goal_name = config.selected_goals[round_index]

    if config.scoring_mode == ScoringMode.BLUE:
        for player in state.players:
            player.score.round_goals[round_index] = _calculate_blue_score(
                state, player, goal_name
            )
    else:
        scores = _calculate_green_scores(state, goal_name, state.round)
        for player in state.players:
            player.score.round_goals[round_index] = scores.get(player.id, 0)
