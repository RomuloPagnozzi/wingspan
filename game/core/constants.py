from dataclasses import dataclass, field
from enum import Enum, unique


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
