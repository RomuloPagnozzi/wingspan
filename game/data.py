from dataclasses import dataclass, field
from typing import List, Dict, Set, Any
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


# =============================================================================
# Power Execution Data Structures
# =============================================================================


@dataclass
class PowerExecution:
    """A power currently being executed on the execution stack."""

    power_id: int
    bird_id: int
    spot_row: int
    spot_col: int
    player_index: int
    phase: str | None
    context: Dict[str, Any] = field(default_factory=dict)

    def get_spot(self, state: "GameState") -> "Spot":
        """Resolve spot reference from the state."""
        return state.players[self.player_index].board[self.spot_row][self.spot_col]


@dataclass
class QueuedPower:
    """A power waiting in the activation queue."""

    power_id: int
    bird_id: int
    spot_row: int
    spot_col: int
    player_index: int
    power_data: Dict[str, Any]


@dataclass
class CostPayment:
    """Context for paying egg or food cost."""

    cost_type: str
    amount: int | Dict[str, int] | List[Dict[str, int]]
    callback_phase: "GamePhase"
    callback_action: str


@dataclass
class EndTurnEffect:
    """A deferred end-of-turn effect."""

    effect_type: str
    player_index: int
    amount: int = 0


@dataclass
class ActionData:
    """This structure holds all transient state needed during action resolution,
    power execution, and turn management.
    """

    powers_queue: List[QueuedPower] = field(default_factory=list)
    current_power_index: int = 0
    action_player_index: int | None = None
    execution_stack: List[PowerExecution] = field(default_factory=list)
    pending_cost: CostPayment | None = None
    end_turn_effects: List[EndTurnEffect] = field(default_factory=list)
    food_needed: int = 0
    eggs_needed: int = 0
    cards_needed: int = 0
    base_amount: int = 0
    gained_rodent: bool = False
    amount_to_discard: int = 0
    pending_callback: tuple["GamePhase", str] | None = None

    def clear(self) -> None:
        """Reset to empty state for new turn."""
        self.powers_queue.clear()
        self.current_power_index = 0
        self.action_player_index = None
        self.execution_stack.clear()
        self.pending_cost = None
        self.end_turn_effects.clear()
        self.food_needed = 0
        self.eggs_needed = 0
        self.cards_needed = 0
        self.base_amount = 0
        self.gained_rodent = False
        self.amount_to_discard = 0
        self.pending_callback = None

    def get_current_queued_power(self) -> QueuedPower | None:
        """Get the current power from the queue, if any."""
        if self.current_power_index < len(self.powers_queue):
            return self.powers_queue[self.current_power_index]
        return None

    def get_current_execution(self) -> PowerExecution | None:
        """Get the top of the execution stack, if any."""
        if self.execution_stack:
            return self.execution_stack[-1]
        return None


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
        new_bird = object.__new__(Bird)
        memo[id(self)] = new_bird
        new_bird.id = self.id
        new_bird.name = self.name
        new_bird.habitats = self.habitats
        new_bird.cost = self.cost
        new_bird.points = self.points
        new_bird.nest = self.nest
        new_bird.egg_limit = self.egg_limit
        new_bird.wingspan = self.wingspan
        new_bird.eggs = self.eggs
        new_bird.stashed_food = self.stashed_food
        new_bird.tucked_cards = self.tucked_cards
        return new_bird

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
    action_data: ActionData = field(default_factory=ActionData, init=False)
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
