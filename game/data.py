from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
import random
import pickle


def init_food() -> Dict[str, int]:
    food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    return {food: 1 for food in food_types}


@dataclass(slots=True)
class Bird:
    id: int
    name: str
    habitats: List[str]
    cost: List[Optional[Dict[str, int]]]
    points: int
    nest: str
    egg_limit: int
    wingspan: int
    power: Dict = field(repr=False)
    eggs: int = field(default=0, init=False)
    stashed_food: int = field(default=0, init=False)
    tucked_cards: int = field(default=0, init=False)
    
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
    bird: Bird = None


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


@dataclass(slots=True)
class Player:
    id: int
    bird_hand: List[Bird] = field(default_factory=lambda: [], init=False)
    bonus_hand: List[Bonus] = field(default_factory=lambda: [], init=False)
    food: Dict[str, int] = field(default_factory=init_food, init=False)
    board: List[List[Spot]] = field(default_factory=build_board, init=False, repr=False)
    action_cubes: int = field(default=8, init=False)
    first_player: bool = field(default=False, init=False)


def load_deck(type: str) -> List:
    deck = []
    with open(
        f"/Users/romulo/Documents/Projects/wingspan/game/assets/{type}.pickle", "rb"
    ) as f:
        deck.extend(pickle.load(f))
    random.shuffle(deck)
    return deck


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
    round: int = field(default=0, init=False)


def initiate_state(n_players):
    if n_players not in [2, 3, 4, 5]:
        raise Exception("Forbidden number of players")
    s = GameState()
    s.bird_tray = [s.bird_deck.pop(-1) for _ in range(3)]
    s.players = [Player(i + 1) for i in range(n_players)]
    first_player = random.randint(0, n_players - 1)
    for i, p in enumerate(s.players):
        if i == first_player:
            p.first_player = True
        p.bird_hand = [s.bird_deck.pop(-1) for _ in range(5)]
        p.bonus_hand = [s.bonus_deck.pop(-1) for _ in range(2)]
    return s


def _count_bonus_birds(bonus: Bonus, player: Player) -> int:
    played_birds = [spot.bird for row in player.board for spot in row]

    if all(bird is None for bird in played_birds):
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

    raise NotImplementedError


def score_bonus_card(bonus: Bonus, player: Player) -> int:
    n_birds = _count_bonus_birds(bonus, player)
    score_params = bonus.score_params
    per_bird = score_params.get("per_bird")
    if per_bird:
        return per_bird * n_birds
    if n_birds >= score_params.get("upper_bound"):
        return score_params.get("upper_score")
    if n_birds >= score_params.get("lower_bound"):
        return score_params.get("lower_score")
    return 0


@dataclass(slots=True, frozen=True)
class Action:
    type: str
    details: Dict
