# State Copy Functions Documentation

Custom state copy functions in `game/core/custom_copy.py` provide ~20x performance improvement over `deepcopy` by:

1. Using `object.__new__(Class)` to skip `__init__` and default factory calls
2. Directly assigning attributes without introspection
3. Sharing immutable objects by reference instead of copying them
4. Avoiding the memo dictionary overhead of `deepcopy`

## Table of Contents

- [Copy Strategy Reference](#copy-strategy-reference)
- [Function Documentation](#function-documentation)
  - [_copy_bird_state](#_copy_bird_state)
  - [_copy_placed_bird](#_copy_placed_bird)
  - [_copy_spot](#_copy_spot)
  - [_copy_score_state](#_copy_score_state)
  - [_copy_player](#_copy_player)
  - [_copy_queued_power](#_copy_queued_power)
  - [_copy_cost_payment](#_copy_cost_payment)
  - [_copy_action_data](#_copy_action_data)
  - [copy_state](#copy_state)

---

## Copy Strategy Reference

| Type | Strategy | Rationale |
|------|----------|-----------|
| `int`, `bool`, `str` | Direct assignment | Immutable in Python |
| `Enum` | Direct assignment | Immutable |
| `tuple` | Direct assignment | Immutable |
| Frozen dataclass | Direct assignment | Immutable by definition |
| `list` of immutables | `list(original)` | New container, contents are immutable |
| `dict` with immutable values | `dict(original)` | New container, contents are immutable |
| `set` of immutables | `set(original)` | New container, contents are immutable |
| Mutable dataclass | Custom copy function | Must recursively copy |
| `list` of mutables | `[copy(x) for x in original]` | Must copy each element |
| `dict` with mutable values | Recursive copy | Must copy each value |

---

## Function Documentation

### `_copy_bird_state`

**Source class: `BirdState`**
```python
@dataclass(slots=True)
class BirdState:
    eggs: int = 0
    stashed_food: int = 0
    tucked_cards: int = 0
```

**Copy implementation:**
```python
def _copy_bird_state(bs: BirdState) -> BirdState:
    return BirdState(bs.eggs, bs.stashed_food, bs.tucked_cards)
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `eggs` | `int` | Direct pass to constructor | Immutable |
| `stashed_food` | `int` | Direct pass to constructor | Immutable |
| `tucked_cards` | `int` | Direct pass to constructor | Immutable |

Uses constructor instead of `object.__new__()` because the overhead difference is negligible for such a small class with no default factories.

---

### `_copy_placed_bird`

**Source class: `PlacedBird`**
```python
@dataclass(slots=True, eq=False, repr=False)
class PlacedBird:
    id: int
    state: BirdState = field(default_factory=BirdState)
```

**Copy implementation:**
```python
def _copy_placed_bird(pb: PlacedBird | None) -> PlacedBird | None:
    if pb is None:
        return None
    return PlacedBird(pb.id, _copy_bird_state(pb.state))
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `id` | `int` | Direct pass to constructor | Immutable |
| `state` | `BirdState` | `_copy_bird_state()` | Mutable dataclass |

Handles `None` because a `Spot` may or may not have a bird placed on it.

---

### `_copy_spot`

**Source class: `Spot`**
```python
@dataclass(slots=True)
class Spot:
    row: int
    col: int
    habitat: str
    resource: str
    resource_amount: int
    extra_resource: bool
    egg_cost: int
    bird: PlacedBird | None = None
```

**Copy implementation:**
```python
def _copy_spot(spot: Spot) -> Spot:
    new_spot = object.__new__(Spot)
    new_spot.row = spot.row
    new_spot.col = spot.col
    new_spot.habitat = spot.habitat
    new_spot.resource = spot.resource
    new_spot.resource_amount = spot.resource_amount
    new_spot.extra_resource = spot.extra_resource
    new_spot.egg_cost = spot.egg_cost
    if spot.bird is None:
        new_spot.bird = None
    else:
        new_spot.bird = _copy_placed_bird(spot.bird)
    return new_spot
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `row` | `int` | Direct assignment | Immutable |
| `col` | `int` | Direct assignment | Immutable |
| `habitat` | `str` | Direct assignment | Immutable (interned string) |
| `resource` | `str` | Direct assignment | Immutable (interned string) |
| `resource_amount` | `int` | Direct assignment | Immutable |
| `extra_resource` | `bool` | Direct assignment | Immutable |
| `egg_cost` | `int` | Direct assignment | Immutable |
| `bird` | `PlacedBird \| None` | `_copy_placed_bird()` | Mutable |

---

### `_copy_score_state`

**Source class: `ScoreState`**
```python
@dataclass(slots=True)
class ScoreState:
    bird_points: int = 0
    egg_points: int = 0
    cached_food: int = 0
    tucked_cards: int = 0
    round_goals: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    bonus_scores: dict[int, int] = field(default_factory=dict)
```

**Copy implementation:**
```python
def _copy_score_state(score: ScoreState) -> ScoreState:
    new_score = object.__new__(ScoreState)
    new_score.bird_points = score.bird_points
    new_score.egg_points = score.egg_points
    new_score.cached_food = score.cached_food
    new_score.tucked_cards = score.tucked_cards
    new_score.round_goals = list(score.round_goals)
    new_score.bonus_scores = dict(score.bonus_scores)
    return new_score
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `bird_points` | `int` | Direct assignment | Immutable |
| `egg_points` | `int` | Direct assignment | Immutable |
| `cached_food` | `int` | Direct assignment | Immutable |
| `tucked_cards` | `int` | Direct assignment | Immutable |
| `round_goals` | `list[int]` | `list()` shallow copy | New list; contents are immutable |
| `bonus_scores` | `dict[int, int]` | `dict()` shallow copy | New dict; keys and values are immutable |

---

### `_copy_player`

**Source class: `Player`**
```python
@dataclass(slots=True)
class Player:
    id: int
    bird_hand: list[int] = field(default_factory=list, init=False)
    bonus_hand: list[int] = field(default_factory=list, init=False)
    food: dict[str, int] = field(default_factory=init_food, init=False)
    board: list[list[Spot]] = field(default_factory=build_board, init=False, repr=False)
    action_cubes: int = field(default=9, init=False)
    first_player: bool = field(default=False, init=False)
    used_pink_powers: set[int] = field(default_factory=set, init=False)
    score: ScoreState = field(default_factory=ScoreState, init=False)
```

**Copy implementation:**
```python
def _copy_player(player: Player) -> Player:
    new_player = object.__new__(Player)
    new_player.id = player.id
    new_player.bird_hand = list(player.bird_hand)
    new_player.bonus_hand = list(player.bonus_hand)
    new_player.food = dict(player.food)
    new_player.action_cubes = player.action_cubes
    new_player.first_player = player.first_player
    new_player.used_pink_powers = set(player.used_pink_powers)
    new_player.board = [[_copy_spot(spot) for spot in row] for row in player.board]
    new_player.score = _copy_score_state(player.score)
    return new_player
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `id` | `int` | Direct assignment | Immutable |
| `bird_hand` | `list[int]` | `list()` shallow copy | Contents are immutable bird IDs |
| `bonus_hand` | `list[int]` | `list()` shallow copy | Contents are immutable bonus IDs |
| `food` | `dict[str, int]` | `dict()` shallow copy | Keys and values are immutable |
| `action_cubes` | `int` | Direct assignment | Immutable |
| `first_player` | `bool` | Direct assignment | Immutable |
| `used_pink_powers` | `set[int]` | `set()` shallow copy | Contents are immutable bird IDs |
| `board` | `list[list[Spot]]` | Nested list comprehension with `_copy_spot()` | Mutable nested structure |
| `score` | `ScoreState` | `_copy_score_state()` | Mutable dataclass |

`object.__new__()` is critical here because `Player.__init__` would call default factories for all fields (`build_board()`, `init_food()`, etc.), which is expensive.

---

### `_copy_queued_power`

**Source class: `QueuedPower`**
```python
@dataclass(slots=True)
class QueuedPower:
    power_id: int
    bird_id: int
    spot_row: int
    spot_col: int
    player_index: int
    power_data: dict[str, Any]
```

**Copy implementation:**
```python
def _copy_queued_power(qp: QueuedPower) -> QueuedPower:
    return QueuedPower(
        power_id=qp.power_id,
        bird_id=qp.bird_id,
        spot_row=qp.spot_row,
        spot_col=qp.spot_col,
        player_index=qp.player_index,
        power_data=qp.power_data,
    )
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `power_id` | `int` | Direct pass to constructor | Immutable |
| `bird_id` | `int` | Direct pass to constructor | Immutable |
| `spot_row` | `int` | Direct pass to constructor | Immutable |
| `spot_col` | `int` | Direct pass to constructor | Immutable |
| `player_index` | `int` | Direct pass to constructor | Immutable |
| `power_data` | `dict[str, Any]` | Direct reference | Registry data, never modified |

`power_data` is shared by reference because it originates from `POWER_REGISTRY` and is never modified during gameplay.

---

### `_copy_cost_payment`

**Source class: `CostPayment`**
```python
@dataclass(slots=True)
class CostPayment:
    cost_type: str
    amount: int | dict[str, int] | list[dict[str, int]]
    callback_phase: GamePhase
    callback_action: Action
```

**Copy implementation:**
```python
def _copy_cost_payment(cp: CostPayment | None) -> CostPayment | None:
    if cp is None:
        return None
    if isinstance(cp.amount, int):
        new_amount = cp.amount
    elif isinstance(cp.amount, dict):
        new_amount = dict(cp.amount)
    else:
        new_amount = [dict(d) for d in cp.amount]
    return CostPayment(
        cost_type=cp.cost_type,
        amount=new_amount,
        callback_phase=cp.callback_phase,
        callback_action=cp.callback_action,
    )
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `cost_type` | `str` | Direct pass | Immutable |
| `amount` | `int \| dict[str, int] \| list[dict[str, int]]` | Type-dependent | See below |
| `callback_phase` | `GamePhase` | Direct pass | Enum, immutable |
| `callback_action` | `Action` | Direct pass | Frozen dataclass, immutable |

**Amount field handling:**
- `int`: Direct assignment (immutable)
- `dict[str, int]`: `dict()` shallow copy (keys/values immutable)
- `list[dict[str, int]]`: List comprehension with `dict()` for each element

---

### `_copy_action_data`

**Source class: `ActionData`**
```python
@dataclass(slots=True)
class ActionData:
    powers_queue: list[QueuedPower] = field(default_factory=list)
    current_power_index: int = 0
    action_player_index: int | None = None
    execution_stack: list[PowerExecution] = field(default_factory=list)
    pending_cost: CostPayment | None = None
    end_turn_effects: list[EndTurnEffect] = field(default_factory=list)
    food_needed: int = 0
    eggs_needed: int = 0
    cards_needed: int = 0
    base_amount: int = 0
    gained_rodent: bool = False
    amount_to_discard: int = 0
    pending_callback: tuple[GamePhase, Action] | None = None
```

**Copy implementation:**
```python
def _copy_action_data(ad: ActionData) -> ActionData:
    new_ad = object.__new__(ActionData)
    new_ad.powers_queue = [_copy_queued_power(qp) for qp in ad.powers_queue]
    new_ad.current_power_index = ad.current_power_index
    new_ad.action_player_index = ad.action_player_index
    new_ad.execution_stack = [copy.deepcopy(pe) for pe in ad.execution_stack]
    new_ad.pending_cost = _copy_cost_payment(ad.pending_cost)
    new_ad.end_turn_effects = list(ad.end_turn_effects)
    new_ad.food_needed = ad.food_needed
    new_ad.eggs_needed = ad.eggs_needed
    new_ad.cards_needed = ad.cards_needed
    new_ad.base_amount = ad.base_amount
    new_ad.gained_rodent = ad.gained_rodent
    new_ad.amount_to_discard = ad.amount_to_discard
    new_ad.pending_callback = ad.pending_callback
    return new_ad
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `powers_queue` | `list[QueuedPower]` | List comp with `_copy_queued_power()` | Mutable elements |
| `current_power_index` | `int` | Direct assignment | Immutable |
| `action_player_index` | `int \| None` | Direct assignment | Immutable |
| `execution_stack` | `list[PowerExecution]` | `copy.deepcopy()` | Mutable context dict; small objects, rare |
| `pending_cost` | `CostPayment \| None` | `_copy_cost_payment()` | Mutable if not None |
| `end_turn_effects` | `list[EndTurnEffect]` | `list()` shallow copy | Elements have only immutable fields |
| `food_needed` | `int` | Direct assignment | Immutable |
| `eggs_needed` | `int` | Direct assignment | Immutable |
| `cards_needed` | `int` | Direct assignment | Immutable |
| `base_amount` | `int` | Direct assignment | Immutable |
| `gained_rodent` | `bool` | Direct assignment | Immutable |
| `amount_to_discard` | `int` | Direct assignment | Immutable |
| `pending_callback` | `tuple[GamePhase, Action] \| None` | Direct assignment | Tuple and Action are both immutable |

---

### `copy_state`

**Source class: `GameState`**
```python
@dataclass(slots=True)
class GameState:
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
```

**Copy implementation:**
```python
def copy_state(state: GameState) -> GameState:
    new_state = object.__new__(GameState)
    new_state.players = [_copy_player(p) for p in state.players]
    new_state.bird_deck = list(state.bird_deck)
    new_state.discarded_birds = list(state.discarded_birds)
    new_state.bonus_deck = list(state.bonus_deck)
    new_state.discarded_bonuses = list(state.discarded_bonuses)
    new_state.bird_tray = list(state.bird_tray)
    new_state.feeder = {k: list(v) for k, v in state.feeder.items()}
    new_state.round = state.round
    new_state.current_player_index = state.current_player_index
    new_state.game_phase = state.game_phase
    new_state.action_data = _copy_action_data(state.action_data)
    new_state.round_goal_config = state.round_goal_config
    new_state.rng = random.Random()
    new_state.rng.setstate(state.rng.getstate())
    return new_state
```

**Field analysis:**

| Field | Type | Copy Strategy | Rationale |
|-------|------|---------------|-----------|
| `players` | `list[Player]` | List comp with `_copy_player()` | Mutable elements |
| `bird_deck` | `list[int]` | `list()` shallow copy | Contents are immutable IDs |
| `discarded_birds` | `list[int]` | `list()` shallow copy | Contents are immutable IDs |
| `bonus_deck` | `list[int]` | `list()` shallow copy | Contents are immutable IDs |
| `discarded_bonuses` | `list[int]` | `list()` shallow copy | Contents are immutable IDs |
| `bird_tray` | `list[int]` | `list()` shallow copy | Contents are immutable IDs |
| `feeder` | `dict[int, list[str]]` | Dict comp with `list()` for values | Keys immutable, values are mutable lists |
| `round` | `int` | Direct assignment | Immutable |
| `current_player_index` | `int` | Direct assignment | Immutable |
| `game_phase` | `GamePhase` | Direct assignment | Enum, immutable |
| `action_data` | `ActionData` | `_copy_action_data()` | Mutable dataclass |
| `round_goal_config` | `RoundGoalConfig \| None` | Direct assignment | Set once at game init, never modified |
| `rng` | `random.Random` | New instance with copied state | Mutable; `getstate()`/`setstate()` preserves exact PRNG position |

**Note on `round_goal_config`:** This is assigned directly without copying because `RoundGoalConfig` contains a `ScoringMode` enum and a `list[str]` of goal names. Both are set once during game initialization and never modified during gameplay.
