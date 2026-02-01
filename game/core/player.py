from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Set

from .registry import BIRD_REGISTRY

if TYPE_CHECKING:
    from .constants import BirdCard


@dataclass(slots=True)
class ScoreState:
    """Tracks all scoring components for a player."""

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


def init_food() -> Dict[str, int]:
    """Create initial food supply with 1 of each type."""
    food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    return {food: 1 for food in food_types}


def build_board() -> List[List[Spot]]:
    """Create an empty 3x5 player board with habitat spots."""
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


@dataclass(slots=True)
class Player:
    """A player in the game with their board, resources, and state."""

    id: int
    bird_hand: List[int] = field(default_factory=list, init=False)
    bonus_hand: List[int] = field(default_factory=list, init=False)
    food: Dict[str, int] = field(default_factory=init_food, init=False)
    board: List[List[Spot]] = field(default_factory=build_board, init=False, repr=False)
    action_cubes: int = field(default=9, init=False)
    first_player: bool = field(default=False, init=False)
    used_pink_powers: Set[int] = field(default_factory=set, init=False)
    score: ScoreState = field(default_factory=ScoreState, init=False)


@dataclass(slots=True)
class BirdState:
    """Mutable state for a bird in play (only this is copied)."""

    eggs: int = 0
    stashed_food: int = 0
    tucked_cards: int = 0


@dataclass(slots=True, eq=False, repr=False)
class PlacedBird:
    """A bird placed on the board - combines card reference with mutable state."""

    card_id: int
    state: BirdState = field(default_factory=BirdState)

    @property
    def card(self) -> BirdCard:
        """Get the frozen card definition from registry."""
        return BIRD_REGISTRY[self.card_id]

    @property
    def id(self) -> int:
        return self.card_id

    @property
    def name(self) -> str:
        return self.card.name

    @property
    def habitats(self) -> tuple:
        return self.card.habitats

    @property
    def cost(self) -> tuple:
        return self.card.cost

    @property
    def points(self) -> int:
        return self.card.points

    @property
    def nest(self) -> str:
        return self.card.nest

    @property
    def egg_limit(self) -> int:
        return self.card.egg_limit

    @property
    def wingspan(self) -> int:
        return self.card.wingspan

    @property
    def eggs(self) -> int:
        return self.state.eggs

    @eggs.setter
    def eggs(self, value: int):
        self.state.eggs = value

    @property
    def stashed_food(self) -> int:
        return self.state.stashed_food

    @stashed_food.setter
    def stashed_food(self, value: int):
        self.state.stashed_food = value

    @property
    def tucked_cards(self) -> int:
        return self.state.tucked_cards

    @tucked_cards.setter
    def tucked_cards(self, value: int):
        self.state.tucked_cards = value

    def __repr__(self) -> str:
        return f"PlacedBird(id={self.card_id}, eggs={self.state.eggs}, food={self.state.stashed_food}, tucked={self.state.tucked_cards})"

    def __eq__(self, other) -> bool:
        """Compare by card ID."""
        if isinstance(other, PlacedBird):
            return self.card_id == other.card_id
        return False

    def __hash__(self) -> int:
        return hash(self.card_id)


@dataclass(slots=True)
class Spot:
    """A single spot on the player's board."""

    row: int
    col: int
    habitat: str
    resource: str
    resource_amount: int
    extra_resource: bool
    egg_cost: int
    bird: PlacedBird | None = None
