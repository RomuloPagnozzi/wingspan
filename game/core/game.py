from dataclasses import dataclass, field
import random

from .constants import ScoringMode, GamePhase
from .player import Player
from .turn_data import ActionData
from .registry import init_registries, BIRD_REGISTRY, BONUS_REGISTRY


def _load_bird_ids() -> list[int]:
    """Load bird deck and initializes registries."""
    init_registries()
    return list(BIRD_REGISTRY.keys())


def _load_bonus_ids() -> list[int]:
    """Load bonus deck and initializes registries."""
    init_registries()
    return list(BONUS_REGISTRY.keys())


def _build_goal_tiles() -> list[tuple]:
    """Build the 8 double-sided goal tiles."""
    nests = ["bowl", "cavity", "ground", "platform"]
    habitats = ["forest", "grassland", "wetland"]
    tiles = [(f"eggs_in_{nest}", f"{nest}_birds_with_egg") for nest in nests]
    tiles.extend(
        [(f"eggs_in_{habitat}", f"birds_in_{habitat}") for habitat in habitats]
    )
    tiles.append(("total_birds", "sets_of_eggs"))
    return tiles


def select_round_goals(rng: random.Random) -> list[str]:
    """Randomly select 4 goals for the game, one per round."""
    selected_tiles = rng.sample(_build_goal_tiles(), 4)
    return [rng.choice(tile) for tile in selected_tiles]


def roll_feeder(rng: random.Random) -> dict[int, list[str]]:
    """Roll 5 dice for the bird feeder."""
    faces = [
        ["fish"],
        ["fruit"],
        ["rodent"],
        ["invertebrate"],
        ["seed"],
        ["invertebrate", "seed"],
    ]
    return {i: rng.choice(faces) for i in range(5)}


@dataclass(slots=True)
class RoundGoalConfig:
    """Configuration for round goals and scoring mode."""

    scoring_mode: ScoringMode
    selected_goals: list[str]


@dataclass(slots=True)
class GameState:
    """The complete state of a Wingspan game."""

    players: list[Player] = field(default_factory=list, init=False)
    bird_deck: list[int] = field(default_factory=_load_bird_ids, init=False)
    discarded_birds: list[int] = field(default_factory=list, init=False)
    bonus_deck: list[int] = field(default_factory=_load_bonus_ids, init=False)
    discarded_bonuses: list[int] = field(default_factory=list, init=False)
    bird_tray: list[int] = field(default_factory=list, init=False)
    feeder: dict = field(default_factory=dict, init=False)
    round: int = field(default=1, init=False)
    current_player_index: int = field(default=0, init=False)
    game_phase: GamePhase = field(default=GamePhase.GAME_SETUP, init=False)
    action_data: ActionData = field(default_factory=ActionData, init=False)
    round_goal_config: RoundGoalConfig | None = field(default=None, init=False)
    rng: random.Random = field(default_factory=random.Random, init=False)


def initiate_state(
    n_players: int,
    scoring_mode: ScoringMode = ScoringMode.GREEN,
    seed: int | None = None,
) -> GameState:
    """Initialize a new game state with the given number of players."""
    if n_players not in [2, 3, 4, 5]:
        raise Exception("Forbidden number of players")

    s = GameState()
    if seed is not None:
        s.rng = random.Random(seed)

    s.rng.shuffle(s.bird_deck)
    s.rng.shuffle(s.bonus_deck)
    s.feeder = roll_feeder(s.rng)
    s.round_goal_config = RoundGoalConfig(
        scoring_mode=scoring_mode,
        selected_goals=select_round_goals(s.rng),
    )
    s.bird_tray = [s.bird_deck.pop() for _ in range(3)]
    s.players = [Player(i + 1) for i in range(n_players)]
    first_player = s.rng.randint(0, n_players - 1)
    for i, p in enumerate(s.players):
        if i == first_player:
            p.first_player = True
        p.bird_hand = [s.bird_deck.pop() for _ in range(5)]
        p.bonus_hand = [s.bonus_deck.pop() for _ in range(2)]
    s.current_player_index = first_player

    return s
