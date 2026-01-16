from dataclasses import dataclass, field
from typing import List, Dict, Set
from enum import Enum, unique
import random
import pickle


@unique
class PinkTrigger(str, Enum):
    BIRD_PLAYED = "bird_played"
    GAIN_FOOD = "gain_food"
    LAY_EGGS = "lay_eggs"
    PREDATOR_SUCCESS = "predator_success"


@unique
class GamePhase(str, Enum):
    GAME_SETUP = "game_setup"
    MAIN_TURN = "main_turn"
    EXTRA_FOOD_ACTION = "extra_food_action"
    EXTRA_LAY_EGGS_ACTION = "extra_lay_eggs_action"
    EXTRA_CARD_DRAW_ACTION = "extra_card_draw_action"
    SELECT_INITIAL_CARDS = "select_initial_cards"
    DISCARD_FOOD = "discard_food"
    COLLECT_FOOD = "collect_food"
    LAY_EGGS = "lay_eggs"
    DRAW_CARDS = "draw_cards"
    PLAY_BIRD = "play_bird"
    SELECT_BIRD_TO_DISCARD = "select_bird_to_discard"
    SELECT_FOOD_TO_DISCARD = "select_food_to_discard"
    SELECT_EGG_TO_DISCARD = "select_egg_to_discard"
    PAY_EGG_COST = "pay_egg_cost"
    PAY_FOOD_COST = "pay_food_cost"
    ACTIVATE_POWERS = "activate_powers"
    END_TURN = "end_turn"
    GAME_OVER = "game_over"


@unique
class ScoringMode(str, Enum):
    BLUE = "blue"
    GREEN = "green"


@dataclass(slots=True)
class RoundGoalConfig:
    scoring_mode: ScoringMode
    selected_goals: List[str]


def init_food() -> Dict[str, int]:
    food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    return {food: 1 for food in food_types}


@dataclass(slots=True)
class Bird:
    id: int
    name: str
    habitats: List[str]
    cost: List[Dict[str, int]]
    points: int
    nest: str
    egg_limit: int
    wingspan: int
    eggs: int = field(default=0, init=False)
    stashed_food: int = field(default=0, init=False)
    tucked_cards: int = field(default=0, init=False)

    def __deepcopy__(self, memo):
        return self

    def __str__(self) -> str:
        cost_str = " or ".join(
            f"{{{', '.join(f'{k}: {v}' for k, v in cost.items())}}}" if cost else "free"
            for cost in self.cost
        )
        return (
            f"{self.name} (ID: {self.id})\n"
            f"Habitats: {', '.join(self.habitats)}\n"
            f"Cost: {cost_str}\n"
            f"Points: {self.points} | Nest: {self.nest} | Eggs: {self.eggs}/{self.egg_limit}\n"
            f"Wingspan: {self.wingspan}cm | Food: {self.stashed_food} | Tucked: {self.tucked_cards}"
        )


@dataclass(slots=True)
class Spot:
    row: int
    col: int
    habitat: str
    resource: str
    resource_amount: int
    extra_resource: bool
    egg_cost: int
    bird: Bird | None = None


def build_board() -> List[List[Spot]]:
    board = []
    habitats = {0: "forest", 1: "grassland", 2: "wetland"}
    resources = {0: "food", 1: "egg", 2: "card"}
    resource_amount = {0: 1, 1: 1, 2: 2, 3: 2, 4: 3}
    extra = {0: False, 1: True, 2: False, 3: True, 4: True}
    egg_cost = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2}
    for line in range(3):
        line_data = []
        for column in range(5):
            line_data.append(
                Spot(
                    line,
                    column,
                    habitats[line],
                    resources[line],
                    (
                        resource_amount[column]
                        if habitats[line] != "grassland"
                        else resource_amount[column] + 1
                    ),
                    extra[column],
                    egg_cost[column],
                )
            )
        board.append(line_data)
    return board


@dataclass(slots=True, frozen=True)
class Bonus:
    id: int
    name: str
    condition: str
    score_params: Dict
    valid_birds_ids: Set[int] = field(repr=False)

    def __deepcopy__(self, memo):
        return self


@dataclass(slots=True)
class ScoreState:
    bird_points: int = 0
    egg_points: int = 0
    cached_food: int = 0
    tucked_cards: int = 0
    round_goals: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    bonus_scores: Dict[int, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.bird_points
            + self.egg_points
            + self.cached_food
            + self.tucked_cards
            + sum(self.round_goals)
            + sum(self.bonus_scores.values())
        )


@dataclass(slots=True)
class Player:
    id: int
    bird_hand: List[Bird] = field(default_factory=lambda: [], init=False)
    bonus_hand: List[Bonus] = field(default_factory=lambda: [], init=False)
    food: Dict[str, int] = field(default_factory=init_food, init=False)
    board: List[List[Spot]] = field(default_factory=build_board, init=False, repr=False)
    action_cubes: int = field(default=9, init=False)
    first_player: bool = field(default=False, init=False)
    used_pink_powers: Set[int] = field(default_factory=set, init=False)
    score: ScoreState = field(default_factory=ScoreState, init=False)


def load_deck(type: str) -> List:
    deck = []
    with open(f"game/assets/{type}.pickle", "rb") as f:
        deck.extend(pickle.load(f))
    random.shuffle(deck)
    return deck


def load_powers() -> Dict:
    """Load powers data from powers.pickle"""
    with open("game/assets/powers.pickle", "rb") as f:
        return pickle.load(f)


def _build_goal_tiles() -> List[tuple]:
    """Build the 8 double-sided goal tiles."""
    nests = ["bowl", "cavity", "ground", "platform"]
    habitats = ["forest", "grassland", "wetland"]
    tiles = [(f"eggs_in_{nest}", f"{nest}_birds_with_egg") for nest in nests]
    tiles.extend(
        [(f"eggs_in_{habitat}", f"birds_in_{habitat}") for habitat in habitats]
    )
    tiles.append(("total_birds", "sets_of_eggs"))
    return tiles


def select_round_goals() -> List[str]:
    """Randomly select 4 goals for the game, one per round."""
    selected_tiles = random.sample(_build_goal_tiles(), 4)
    return [random.choice(tile) for tile in selected_tiles]


def get_bird_power(bird_id: int) -> Dict:
    """Get power data for a specific bird ID"""
    powers = load_powers()
    return powers.get(bird_id, {})


def get_bird(bird_id: int) -> Bird | None:
    """Get a bird by id"""
    deck: List[Bird] = load_deck("birds")
    for bird in deck:
        if bird.id == bird_id:
            return bird
    return None


def roll_feeder():
    faces = [
        ["fish"],
        ["fruit"],
        ["rodent"],
        ["invertebrate"],
        ["seed"],
        ["invertebrate", "seed"],
    ]
    return {i: random.choice(faces) for i in range(5)}


@dataclass(slots=True)
class GameState:
    players: List[Player] = field(default_factory=lambda: [], init=False)
    bird_deck: List[Bird] = field(
        default_factory=lambda: load_deck("birds"), init=False
    )
    discarded_birds: List[Bird] = field(default_factory=lambda: [], init=False)
    bonus_deck: List[Bonus] = field(
        default_factory=lambda: load_deck("bonus"), init=False
    )
    discarded_bonuses: List[Bird] = field(default_factory=lambda: [], init=False)
    bird_tray: List = field(default_factory=lambda: [], init=False)
    feeder: Dict = field(default_factory=roll_feeder, init=False)
    round: int = field(default=1, init=False)
    current_player_index: int = field(default=0, init=False)
    game_phase: GamePhase = field(default=GamePhase.GAME_SETUP, init=False)
    action_data: Dict = field(default_factory=dict, init=False)
    round_goal_config: RoundGoalConfig | None = field(default=None, init=False)


def initiate_state(
    n_players: int,
    scoring_mode: ScoringMode = ScoringMode.GREEN,
) -> GameState:
    """Initialize a new game state with the given number of players."""
    if n_players not in [2, 3, 4, 5]:
        raise Exception("Forbidden number of players")
    s = GameState()
    s.round_goal_config = RoundGoalConfig(
        scoring_mode=scoring_mode,
        selected_goals=select_round_goals(),
    )
    s.bird_tray = [s.bird_deck.pop() for _ in range(3)]
    s.players = [Player(i + 1) for i in range(n_players)]
    first_player = random.randint(0, n_players - 1)
    for i, p in enumerate(s.players):
        if i == first_player:
            p.first_player = True
        p.bird_hand = [s.bird_deck.pop() for _ in range(5)]
        p.bonus_hand = [s.bonus_deck.pop() for _ in range(2)]
    s.current_player_index = first_player
    return s


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


HABITAT_ROWS = {"forest": 0, "grassland": 1, "wetland": 2}


def evaluate_goal(state: GameState, player: Player, goal_name: str) -> int:
    """Evaluate how many items a player has matching the goal criteria."""
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
            return _count_eggs_in_habitat(player, HABITAT_ROWS["forest"])
        case "eggs_in_grassland":
            return _count_eggs_in_habitat(player, HABITAT_ROWS["grassland"])
        case "eggs_in_wetland":
            return _count_eggs_in_habitat(player, HABITAT_ROWS["wetland"])
        case "birds_in_forest":
            return _count_birds_in_habitat(player, HABITAT_ROWS["forest"])
        case "birds_in_grassland":
            return _count_birds_in_habitat(player, HABITAT_ROWS["grassland"])
        case "birds_in_wetland":
            return _count_birds_in_habitat(player, HABITAT_ROWS["wetland"])
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
