from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
import pickle

# =============================================================================
# Enums
# =============================================================================


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


# =============================================================================
# Card types
# =============================================================================


@dataclass(frozen=True, slots=True)
class BirdCard:
    """Immutable bird card definition - shared across all game states."""

    id: int
    name: str
    habitats: tuple[str, ...]
    cost: tuple[tuple[tuple[str, int], ...], ...]
    points: int
    nest: str
    egg_limit: int
    wingspan: int


@dataclass(slots=True, frozen=True)
class Bonus:
    """Immutable bonus card definition."""

    id: int
    name: str
    condition: str
    score_params: dict
    valid_birds_ids: frozenset[int] = field(repr=False)


# =============================================================================
# Registry
# =============================================================================

BIRD_REGISTRY: dict[int, BirdCard] = {}
POWER_REGISTRY: dict[int, dict] = {}
BONUS_REGISTRY: dict[int, Bonus] = {}
_REGISTRIES_INITIALIZED = False


def load_deck(type: str) -> list:
    """Load a deck from a pickle file."""
    with open(f"game/assets/{type}.pickle", "rb") as f:
        return pickle.load(f)


def load_powers() -> dict:
    """Load powers data from powers.pickle"""
    with open("game/assets/powers.pickle", "rb") as f:
        return pickle.load(f)


def init_registries() -> None:
    """Initialize all card registries from pickle files."""
    global _REGISTRIES_INITIALIZED
    if _REGISTRIES_INITIALIZED:
        return

    for bird in load_deck("birds"):
        if bird.id not in BIRD_REGISTRY:
            BIRD_REGISTRY[bird.id] = bird

    for bird_id, power_data in load_powers().items():
        POWER_REGISTRY[bird_id] = power_data

    for bonus in load_deck("bonuses"):
        if bonus.id not in BONUS_REGISTRY:
            BONUS_REGISTRY[bonus.id] = bonus

    _REGISTRIES_INITIALIZED = True


def get_bird_card(bird_id: int) -> BirdCard | None:
    """Get frozen bird card from registry."""
    init_registries()
    return BIRD_REGISTRY.get(bird_id)


def get_bonus_card(bonus_id: int) -> Bonus | None:
    """Get frozen bonus card from registry."""
    init_registries()
    return BONUS_REGISTRY.get(bonus_id)


def get_bird_power(bird_id: int) -> dict:
    """Get power data for a specific bird ID from registry."""
    init_registries()
    return POWER_REGISTRY.get(bird_id, {})


# =============================================================================
# Board primitives
# =============================================================================


@dataclass(slots=True)
class BirdState:
    """Mutable state for a bird in play (only this is copied)."""

    eggs: int = 0
    stashed_food: int = 0
    tucked_cards: int = 0


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


@dataclass(slots=True, eq=False, repr=False)
class PlacedBird:
    """A bird placed on the board - combines card reference with mutable state."""

    id: int
    state: BirdState = field(default_factory=BirdState)

    @property
    def card(self) -> BirdCard:
        """Get the frozen card definition from registry."""
        return BIRD_REGISTRY[self.id]

    def __repr__(self) -> str:
        return f"PlacedBird(id={self.id}, eggs={self.state.eggs}, food={self.state.stashed_food}, tucked={self.state.tucked_cards})"

    def __eq__(self, other) -> bool:
        """Compare by card ID."""
        if isinstance(other, PlacedBird):
            return self.id == other.id
        return False

    def __hash__(self) -> int:
        return hash(self.id)


# =============================================================================
# Player
# =============================================================================


@dataclass(slots=True)
class ScoreState:
    """Tracks all scoring components for a player."""

    bird_points: int = 0
    egg_points: int = 0
    cached_food: int = 0
    tucked_cards: int = 0
    round_goals: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    bonus_scores: dict[int, int] = field(default_factory=dict)

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


def init_food() -> dict[str, int]:
    """Create initial food supply with 1 of each type."""
    food_types = ["invertebrate", "seed", "fish", "fruit", "rodent"]
    return {food: 1 for food in food_types}


def build_board() -> list[list[Spot]]:
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
    bird_hand: list[int] = field(default_factory=list, init=False)
    bonus_hand: list[int] = field(default_factory=list, init=False)
    food: dict[str, int] = field(default_factory=init_food, init=False)
    board: list[list[Spot]] = field(default_factory=build_board, init=False, repr=False)
    action_cubes: int = field(default=9, init=False)
    first_player: bool = field(default=False, init=False)
    used_pink_powers: set[int] = field(default_factory=set, init=False)
    score: ScoreState = field(default_factory=ScoreState, init=False)
