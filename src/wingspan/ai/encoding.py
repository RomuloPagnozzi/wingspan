"""Turns a game state and its legal actions into numbers for the network.

    encode_obs(state, viewer)     -> Observation: me + opponents + shared (table, pending decision)
    encode_action(state, action)  -> one vector per legal action

Every number has a name. Each block is built as a dict (`*_features`), so any value in a vector
can be traced back to what it means; the vector is that dict's values, in `*_feature_names()`
order. For example, the non-zero features of the American Robin card:

    {'points': 0.11, 'egg_limit': 0.67, 'wingspan': 0.66, 'nest_bowl': 1.0,
     'habitat_forest': 1.0, 'habitat_grassland': 1.0,
     'cost_invertebrate': 0.17, 'cost_fruit': 0.17, 'cost_min_total': 0.33, 'cost_is_or': 1.0,
     'power_color_brown': 1.0, 'power_template_17': 1.0}

Every value is scaled into [0, 1] so no feature dominates the network just by its units.
Only what the viewer can legitimately see is encoded: opponents' hands and bonus cards are
zeros, and nothing depends on the deck order.

Left out in v1: power details (which food, which habitat, how many). The net sees a power's
color (when it fires) and template (what kind of effect), not its parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache

from wingspan.engine.core import (
    BIRD_REGISTRY,
    BONUS_REGISTRY,
    Action,
    BirdCard,
    Bonus,
    DrawCardsAction,
    EggMapAction,
    FoodMapAction,
    GamePhase,
    GameState,
    IdAction,
    NameAction,
    PlayBirdAction,
    ScoringMode,
    SelectDieAction,
    SelectInitialAction,
    SimpleAction,
    TradeAction,
    get_bird_power,
    get_bonus_card,
    init_registries,
    initiate_state,
)
from wingspan.engine.scoring import count_bonus_birds, evaluate_goal, score_bonus_card
from wingspan.engine.utils import find_leftmost_empty_spot, get_action_cubes_for_round

# =============================================================================
# Vocabularies: the options behind each one-hot group
# =============================================================================

FOODS = ("invertebrate", "seed", "fish", "fruit", "rodent")
NESTS = ("bowl", "cavity", "ground", "platform", "wild")
HABITATS = ("forest", "grassland", "wetland")  # also the board rows, top to bottom
BOARD_COLS = 5
SPOTS = tuple(f"{habitat}_{col}" for habitat in HABITATS for col in range(BOARD_COLS))
POWER_COLORS = ("brown", "white", "pink", "none")
POWER_TEMPLATES = tuple(range(22))  # 1..21 are the effect kinds, 0 means "no power"
BONUS_IDS = tuple(range(1, 27))
PLAYER_COUNTS = (2, 3, 4, 5)
ROUNDS = (1, 2, 3, 4)

# The 16 round goals, one per tile side (see `_build_goal_tiles` in engine/core/game.py).
GOALS = (
    "eggs_in_bowl", "bowl_birds_with_egg",
    "eggs_in_cavity", "cavity_birds_with_egg",
    "eggs_in_ground", "ground_birds_with_egg",
    "eggs_in_platform", "platform_birds_with_egg",
    "eggs_in_forest", "birds_in_forest",
    "eggs_in_grassland", "birds_in_grassland",
    "eggs_in_wetland", "birds_in_wetland",
    "total_birds", "sets_of_eggs",
)  # fmt: skip

# Every step a power can be waiting in (`PowerExecution.phase`); "none" when no power is
# mid-resolution. "end_turn_discard" is the end-of-turn discard prompt.
# The phases a decision can come up in. Left out: game_setup (its only action, start_setup, is
# forced) and game_over (no legal actions at all). A state in either encodes as all zeros here.
PHASES = tuple(
    p.value for p in GamePhase if p not in (GamePhase.GAME_SETUP, GamePhase.GAME_OVER)
)
POWER_STEPS = (
    "none", "select_die", "select_card", "select_bird", "choose_cache", "select_trade",
    "select_habitat", "select_gain", "select_food_type", "select_food", "select_draw",
    "select_discard", "select_bonus", "choose_starting_player", "choices",
    "awaiting_bird_play", "end_turn_discard",
)  # fmt: skip
# What a pending payment is for. The engine also sets "egg_paid"/"food_paid" for an instant after
# a payment, but the callback consumes them in the same step, so no decision ever sees them.
PAYMENT_KINDS = ("none", "egg", "food")

# Every kind of legal action: the action's class plus its `type` string, so
# "simple_lay_eggs" is the main-turn choice and "egg_map_lay_eggs" is where the eggs go.
# Left out: the setup steps ("simple_start_setup", "simple_end_setup"). They are always the only
# legal action, so nobody chooses them; like every single-legal step they are applied, not scored.
ACTION_KINDS = (
    # SimpleAction
    "simple_gain_food", "simple_lay_eggs",
    "simple_draw_cards", "simple_play_bird", "simple_trade_bird", "simple_trade_food",
    "simple_trade_egg", "simple_skip_trade", "simple_reroll_all", "simple_activate_power",
    "simple_skip_power", "simple_cache_food", "simple_supply_food",
    # IdAction
    "id_discard_bird", "id_discard_card", "id_discard_egg", "id_discard_egg_from",
    "id_tuck_card", "id_select_bird", "id_select_card", "id_power_5_bonus", "id_choose_player",
    # NameAction
    "name_discard_food", "name_select_food", "name_select_food_type", "name_select_habitat",
    # FoodMapAction, EggMapAction
    "food_map_pay_food", "food_map_gain_food_combo", "food_map_discard_food_combo",
    "egg_map_pay_eggs", "egg_map_lay_eggs", "egg_map_activate_eggs",
    # classes without a type string
    "play_bird_at", "select_die", "trade_food", "draw_combo", "select_initial_cards",
)  # fmt: skip
_TYPED_ACTIONS = {
    SimpleAction: "simple",
    IdAction: "id",
    NameAction: "name",
    FoodMapAction: "food_map",
    EggMapAction: "egg_map",
}
_UNTYPED_ACTIONS = {
    PlayBirdAction: "play_bird_at",
    SelectDieAction: "select_die",
    TradeAction: "trade_food",
    DrawCardsAction: "draw_combo",
    SelectInitialAction: "select_initial_cards",
}

# =============================================================================
# Scales: what each raw number is divided by to land in [0, 1]
# =============================================================================

# Card values: the largest in the card set.
MAX_POINTS = 9
MAX_EGG_LIMIT = 6
MAX_WINGSPAN_CM = 300  # the real maximum is 277
MAX_FOOD_PER_COST = 3  # no bird costs more than 3 food in total
MAX_BONUS_PER_BIRD = 2
MAX_BONUS_COUNT = 9  # largest upper_bound on any bonus card
MAX_BONUS_POINTS = 8
MAX_QUALIFYING_BIRDS = 5  # for "per bird" bonus cards, which have no upper bound

# Game-state values: caps chosen from the largest values seen in random and MCTS games.
# A value above its cap saturates at 1.0 (see `_scaled`) instead of leaving the range.
MAX_CACHED_PER_BIRD = 6
MAX_TUCKED_PER_BIRD = 6
MAX_FOOD_PER_TYPE = 8
MAX_HAND_SIZE = 12
MAX_BONUS_CARDS = 4
MAX_ACTION_CUBES = 8  # a round starts with 8, 7, 6 or 5; setup shows 9, which saturates
TOTAL_TURNS = sum(get_action_cubes_for_round(r) for r in ROUNDS)  # 26 turns per player
MAX_ACTION_YIELD = 4  # grassland, last spots
MAX_EGG_COST = 2  # eggs to pay when playing a bird on the right-hand spots
MAX_GOAL_POINTS = 7  # most a player can earn from one round goal (green, round 4)
MAX_PUBLIC_SCORE = 120  # points on the table (all but bonus cards); MCTS games end near 70-90
MAX_TRAY = 3
MAX_DICE = 5
MAX_DECK = 170
MAX_DISCARD = 60
MAX_PENDING = 5  # largest food/eggs/cards/discard count a phase or action involves
MAX_QUEUED_POWERS = 5
MAX_END_TURN_DISCARDS = 2
MAX_ACTION_BIRDS = 5  # kept birds at setup; most eggs laid in one action


def goal_cap(goal: str) -> int:
    """Largest count worth distinguishing for a goal."""
    if goal.startswith("eggs_in_"):
        return 15  # eggs on one nest type or in one habitat (random play reaches 18)
    if goal.endswith("_birds_with_egg"):
        return 8
    if goal.startswith("birds_in_"):
        return BOARD_COLS
    if goal == "total_birds":
        return len(SPOTS)
    return 10  # sets_of_eggs


def bonus_cap(bonus: Bonus) -> int:
    """Qualifying-bird count at which a bonus card pays its top reward."""
    return bonus.score_params.get("upper_bound", MAX_QUALIFYING_BIRDS)


# =============================================================================
# Helpers
# =============================================================================


def _scaled(value: float, cap: float) -> float:
    return min(value / cap, 1.0)


def _one_hot(prefix: str, value, options) -> dict[str, float]:
    """One column per option, 1.0 where it matches: _one_hot("nest", "bowl", NESTS) gives
    nest_bowl=1.0 and 0.0 for the rest. A value that is not an option gives all zeros.
    """
    return {f"{prefix}_{option}": float(value == option) for option in options}


def _summed(prefix: str, names, rows, cap: float = 1.0) -> dict[str, float]:
    """A set of cards as one group of columns: their feature rows added up, as a fraction of
    `cap` cards. No rows (an empty or hidden set) gives all zeros."""
    return {
        f"{prefix}_{name}": _scaled(sum(row[i] for row in rows), cap)
        for i, name in enumerate(names)
    }


# =============================================================================
# Cards: static, computed once
# =============================================================================


def bird_features(card: BirdCard) -> dict[str, float]:
    """Everything static about a bird."""
    power = get_bird_power(card.id)
    color = power.get("color")
    if color not in POWER_COLORS:  # the 6 birds without a power store a NaN color
        color = "none"
    template = (power.get("data") or {}).get("id", 0)

    # Some costs offer a choice ("1 invertebrate OR 1 fruit"), stored as several options.
    # Each food column holds its average across the options: a Robin is 0.5 invertebrate and
    # 0.5 fruit, a bird that needs both would be 1 and 1. `cost_is_or` tells the two apart;
    # when it is 0 there is a single option and the average is exact.
    options = [dict(option) for option in card.cost] or [{}]

    def avg_cost(food: str) -> float:
        return sum(o.get(food, 0) for o in options) / len(options) / MAX_FOOD_PER_COST

    return {
        "points": card.points / MAX_POINTS,
        "egg_limit": card.egg_limit / MAX_EGG_LIMIT,
        # log: the range is 10-277 cm but most birds sit in the low tens
        "wingspan": math.log(card.wingspan) / math.log(MAX_WINGSPAN_CM),
        # the 2 birds with a NaN nest get all zeros
        **_one_hot("nest", card.nest, NESTS),
        # multi-hot: a bird can live in several habitats
        **{f"habitat_{h}": float(h in card.habitats) for h in HABITATS},
        **{f"cost_{food}": avg_cost(food) for food in (*FOODS, "wild")},
        "cost_min_total": min(sum(o.values()) for o in options) / MAX_FOOD_PER_COST,
        "cost_is_or": float(len(options) > 1),
        **_one_hot("power_color", color, POWER_COLORS),
        **_one_hot("power_template", template, POWER_TEMPLATES),
    }


def bonus_features(bonus: Bonus) -> dict[str, float]:
    """Card identity (one-hot), its scoring parameters, and whether it depends on game state
    (eggs, habitats, hand size) rather than on a fixed list of qualifying birds."""
    p = bonus.score_params
    return {
        **_one_hot("bonus_card", bonus.id, BONUS_IDS),
        # "per_bird" cards pay a fixed amount per qualifying bird
        "per_bird_points": p.get("per_bird", 0) / MAX_BONUS_PER_BIRD,
        # threshold cards: lower_score at lower_bound birds, upper_score at upper_bound birds
        "lower_bound": p.get("lower_bound", 0) / MAX_BONUS_COUNT,
        "upper_bound": p.get("upper_bound", 0) / MAX_BONUS_COUNT,
        "lower_score": p.get("lower_score", 0) / MAX_BONUS_POINTS,
        "upper_score": p.get("upper_score", 0) / MAX_BONUS_POINTS,
        "depends_on_game_state": float(not bonus.valid_birds_ids),
    }


@cache
def bird_table() -> dict[int, list[float]]:
    """bird id -> feature vector, columns in `bird_feature_names()` order."""
    init_registries()
    return {i: list(bird_features(card).values()) for i, card in BIRD_REGISTRY.items()}


@cache
def bonus_table() -> dict[int, list[float]]:
    """bonus id -> feature vector, columns in `bonus_feature_names()` order."""
    init_registries()
    return {i: list(bonus_features(b).values()) for i, b in BONUS_REGISTRY.items()}


@cache
def bird_feature_names() -> tuple[str, ...]:
    init_registries()
    return tuple(bird_features(next(iter(BIRD_REGISTRY.values()))))


@cache
def bonus_feature_names() -> tuple[str, ...]:
    init_registries()
    return tuple(bonus_features(next(iter(BONUS_REGISTRY.values()))))


# =============================================================================
# One player, as a viewer sees them
# =============================================================================


def player_features(
    state: GameState, player_index: int, viewer_index: int
) -> dict[str, float]:
    """Everyone gets the same layout, so opponents can share weights with "me"; what the
    viewer cannot see is zeros rather than missing.

    Public: the board, food, hand size, bonus card count, round goals, cubes.
    Private to the player themself: which birds are in hand (`hand_*`), which bonus cards
    they hold (`held_*`) and how those are doing (`bonus_progress`, `bonus_points_now`).
    """
    player = state.players[player_index]
    visible = player_index == viewer_index
    birds = bird_table()
    bird_names = bird_feature_names()
    features: dict[str, float] = {}

    for habitat, row in zip(HABITATS, player.board):
        # One group of columns per spot. Where a spot is (its habitat, egg cost, resource) is
        # fixed, so it is carried by the column names, not by a value. Empty spots are zeros.
        for spot in row:
            slot = f"{habitat}_{spot.config.col}"
            bird = spot.bird
            features[f"{slot}_occupied"] = float(bird is not None)
            features[f"{slot}_eggs"] = bird.state.eggs / MAX_EGG_LIMIT if bird else 0.0
            features[f"{slot}_cached_food"] = (
                _scaled(bird.state.stashed_food, MAX_CACHED_PER_BIRD) if bird else 0.0
            )
            features[f"{slot}_tucked_cards"] = (
                _scaled(bird.state.tucked_cards, MAX_TUCKED_PER_BIRD) if bird else 0.0
            )
            features |= _summed(
                f"{slot}_bird", bird_names, [birds[bird.id]] if bird else []
            )

        # The row as a whole. What its action gives, and what a bird played here costs, depend
        # on its next empty spot (the engine's rule: `_route_main_turn` in phase_handlers.py).
        # A full row keeps the yield of its last spot and still offers the trade.
        next_spot = find_leftmost_empty_spot(row)
        features[f"{habitat}_birds"] = sum(s.bird is not None for s in row) / BOARD_COLS
        features[f"{habitat}_action_yield"] = (
            next_spot or row[-1]
        ).config.resource_amount / MAX_ACTION_YIELD
        # "trade one thing for one more": whether the row position allows it. Having
        # something to trade (cards, food, eggs) is separate and visible in hand/food/eggs.
        features[f"{habitat}_has_trade_option"] = float(
            next_spot is None or next_spot.config.extra_resource
        )
        features[f"{habitat}_next_egg_cost"] = (
            next_spot.config.egg_cost / MAX_EGG_COST if next_spot else 0.0
        )

    for food in FOODS:
        features[f"food_{food}"] = _scaled(player.food.get(food, 0), MAX_FOOD_PER_TYPE)

    # The hand as a fraction of a full hand: hand_nest_bowl is "bowl birds held / 12".
    features["hand_size"] = _scaled(len(player.bird_hand), MAX_HAND_SIZE)
    hand = [birds[b] for b in player.bird_hand] if visible else []
    features |= _summed("hand", bird_names, hand, MAX_HAND_SIZE)

    # Usually a single bonus card; with several, their features add up (capped at 1.0).
    features["bonus_card_count"] = _scaled(len(player.bonus_hand), MAX_BONUS_CARDS)
    bonus_cards = [get_bonus_card(b) for b in player.bonus_hand] if visible else []
    features |= _summed(
        "held", bonus_feature_names(), [bonus_table()[b.id] for b in bonus_cards]
    )
    # Qualifying birds as a fraction of the count that earns the top reward, and the points
    # the card(s) would pay right now.
    features["bonus_progress"] = _scaled(
        sum(count_bonus_birds(b, player) / bonus_cap(b) for b in bonus_cards), 1.0
    )
    features["bonus_points_now"] = _scaled(
        sum(score_bonus_card(b, player) for b in bonus_cards), MAX_BONUS_POINTS
    )

    # Round goals: points already banked, and progress on the goals still to be scored
    # (0 once a round is over). In green scoring only the comparison with the opponent
    # matters, which the net gets from having both players' blocks.
    for r, points in zip(ROUNDS, player.score.round_goals):
        features[f"round_goal_points_{r}"] = _scaled(points, MAX_GOAL_POINTS)
    for r, goal in zip(ROUNDS, state.round_goal_config.selected_goals):
        scored = r < state.round or state.game_phase == GamePhase.GAME_OVER
        count = 0 if scored else evaluate_goal(state, player, goal)
        features[f"goal_progress_r{r}"] = _scaled(count, goal_cap(goal))

    # Points everyone can count right now. Recomputed from the board because `player.score`
    # is only refreshed at the end of a turn (and not at all in MCTS rollouts).
    on_board = [s.bird for row in player.board for s in row if s.bird]
    features["score_now"] = _scaled(
        sum(
            b.card.points + b.state.eggs + b.state.stashed_food + b.state.tucked_cards
            for b in on_board
        )
        + sum(player.score.round_goals),
        MAX_PUBLIC_SCORE,
    )

    # Turns are counted, not just scaled: a cube is one turn, so 5 cubes means exactly 5 more
    # turns this round. The cube is spent when the main action completes (food taken, eggs
    # laid...), before its powers run: while choosing, these still include the turn in
    # progress, so one_turn_left_* means "this is my last turn"; during powers they don't.
    # The game total is this round's cubes plus every later round's full allotment.
    cubes = player.action_cubes
    turns_left = min(cubes, MAX_ACTION_CUBES) + sum(
        get_action_cubes_for_round(r) for r in range(state.round + 1, ROUNDS[-1] + 1)
    )
    features["action_cubes"] = _scaled(cubes, MAX_ACTION_CUBES)
    features["turns_left_game"] = turns_left / TOTAL_TURNS
    features["one_turn_left_in_round"] = float(cubes == 1)
    features["one_turn_left_in_game"] = float(turns_left == 1)
    features["first_player"] = float(player.first_player)
    return features


# =============================================================================
# The table: what everyone sees, whoever is looking
# =============================================================================


def public_features(state: GameState) -> dict[str, float]:
    """Everything that is not tied to one player. The bird deck and the discard pile
    contribute only their sizes."""
    features: dict[str, float] = {}

    # The tray as a fraction of its 3 slots, like the hand.
    features["tray_size"] = len(state.bird_tray) / MAX_TRAY
    tray = [bird_table()[b] for b in state.bird_tray]
    features |= _summed("tray", bird_feature_names(), tray, MAX_TRAY)

    # The feeder: how many dice offer each food (the invertebrate/seed die counts for both).
    dice = list(state.feeder.values())
    features["feeder_dice"] = len(dice) / MAX_DICE
    for food in FOODS:
        features[f"feeder_{food}"] = sum(food in die for die in dice) / MAX_DICE
    # Same rule as `get_collect_food_actions`: all dice showing the same face allows a reroll
    features["feeder_can_reroll"] = float(
        len(dice) > 0 and len({tuple(sorted(die)) for die in dice}) == 1
    )

    features["deck_size"] = _scaled(len(state.bird_deck), MAX_DECK)
    features["discard_size"] = _scaled(len(state.discarded_birds), MAX_DISCARD)

    features |= _one_hot("round", state.round, ROUNDS)
    # All four goals are known from the start: goal_r2_total_birds means "round 2 is scored
    # on total birds".
    for r, goal in zip(ROUNDS, state.round_goal_config.selected_goals):
        features |= _one_hot(f"goal_r{r}", goal, GOALS)
    features["scoring_green"] = float(
        state.round_goal_config.scoring_mode == ScoringMode.GREEN
    )
    return features


# =============================================================================
# The pending decision: what the game is asking right now
# =============================================================================


def pending_features(state: GameState, viewer_index: int) -> dict[str, float]:
    """Which phase, how many of what are still needed, which power is mid-resolution and
    what is being paid for.

    All public except `paying_for_*`, the bird a player has chosen to play but not placed
    yet: it is still in their hand, so only they see it. Meant for the player to move: the
    network is only asked about decisions, which the viewer makes.
    """
    pending = state.action_data
    to_move = state.current_player_index == viewer_index
    features: dict[str, float] = {}

    features |= _one_hot("phase", state.game_phase.value, PHASES)
    # Whose turn it is. The viewer is the player choosing (nothing else is encoded), so there
    # is no "is it my move" column. This one is 0 while an effect of someone else's turn asks
    # the viewer to choose: an opponent's pink power firing, or a power every player answers.
    owner = pending.action_player_index
    features["viewer_owns_turn"] = float(
        (state.current_player_index if owner is None else owner) == viewer_index
    )

    for counter in (
        "food_needed",
        "eggs_needed",
        "cards_needed",
        "amount_to_discard",
        "base_amount",
    ):
        features[counter] = _scaled(getattr(pending, counter), MAX_PENDING)
    features["powers_left"] = _scaled(
        len(pending.powers_queue) - pending.current_power_index, MAX_QUEUED_POWERS
    )
    features["end_turn_discards"] = _scaled(
        len(pending.end_turn_effects), MAX_END_TURN_DISCARDS
    )

    # The power being resolved, or else the one waiting for "activate or skip"
    running = pending.get_current_execution()
    power = running or pending.get_current_queued_power()
    features |= _one_hot(
        "active_power_template", power.power_id if power else 0, POWER_TEMPLATES
    )
    features |= _one_hot(
        "power_step", (running and running.phase) or "none", POWER_STEPS
    )

    cost = pending.pending_cost
    payment = cost.cost_type if cost else "none"
    features |= _one_hot("payment", payment, PAYMENT_KINDS)
    features["payment_egg_amount"] = (
        _scaled(cost.amount, MAX_EGG_COST) if payment == "egg" else 0.0
    )
    paying_for = (
        [bird_table()[cost.callback_action.bird_id]]
        if cost and to_move and isinstance(cost.callback_action, PlayBirdAction)
        else []
    )
    features |= _summed("paying_for", bird_feature_names(), paying_for)
    return features


# =============================================================================
# The full observation
# =============================================================================


def shared_features(state: GameState, viewer_index: int) -> dict[str, float]:
    """Everything that is not about one player: the table, the pending decision, and how
    many players are in the game (the dynamics change with the count)."""
    return {
        **public_features(state),
        **pending_features(state, viewer_index),
        **_one_hot("players", len(state.players), PLAYER_COUNTS),
    }


@dataclass(frozen=True)
class Observation:
    """What a viewer can see, in the pieces the network consumes.

    `me` and every entry of `opponents` share one layout (`player_feature_names()`), so one
    encoder with shared weights can read all of them. Opponents are listed clockwise from
    the viewer. `shared` follows `shared_feature_names()`.

    `hand` and `tray` list the same cards again as bird ids (rows of `bird_table()`), for a
    set encoder: summing raw card features (the `hand_*` and `tray_*` columns) loses which
    properties belong to the same card, so a grassland-bowl + wetland-cavity hand looks like
    wetland-bowl + grassland-cavity. A net that transforms each card before summing keeps
    that. Opponents' hands are hidden, so only the viewer's own is listed. EXP-010 compares
    the two.
    """

    me: list[float]
    opponents: list[list[float]]
    shared: list[float]
    hand: list[int]
    tray: list[int]

    def flat(self) -> list[float]:
        """One vector for a plain MLP. Its length grows with the number of opponents."""
        return [*self.me, *(v for opp in self.opponents for v in opp), *self.shared]


def encode_obs(state: GameState, viewer_index: int) -> Observation:
    n = len(state.players)
    clockwise = [(viewer_index + offset) % n for offset in range(1, n)]
    return Observation(
        me=encode_player(state, viewer_index, viewer_index),
        opponents=[encode_player(state, i, viewer_index) for i in clockwise],
        shared=list(shared_features(state, viewer_index).values()),
        hand=sorted(state.players[viewer_index].bird_hand),  # a set: order means nothing
        tray=sorted(state.bird_tray),
    )


# =============================================================================
# Actions
# =============================================================================


def action_kind(action: Action) -> str:
    prefix = _TYPED_ACTIONS.get(type(action))
    return f"{prefix}_{action.type}" if prefix else _UNTYPED_ACTIONS[type(action)]


def action_bird_ids(action: Action) -> list[int]:
    """The birds an action names, sorted, once per egg for an egg distribution.

    The `action_bird_*` columns average these, which loses which properties belong to the
    same bird (keeping a grassland-bowl + wetland-cavity pair looks like keeping wetland-bowl
    + grassland-cavity). A set encoder over these ids keeps it; EXP-010 compares the two.
    """
    match action:
        # Bird ids and bonus ids overlap, so the type decides what an IdAction's id means
        case IdAction(type="power_5_bonus" | "choose_player"):
            return []
        case IdAction(id=i) | PlayBirdAction(bird_id=i):
            return [i]
        case EggMapAction(items=items):
            return sorted(b for b, n in items for _ in range(n))
        case DrawCardsAction(tray_birds=birds) | SelectInitialAction(kept_birds=birds):
            return sorted(birds)
    return []


def action_features(state: GameState, action: Action) -> dict[str, float]:
    """One legal action of the player to move, as that player sees it.

    The kind says what is being done; the other columns say to what: which birds, which
    bonus card, which board spot or habitat, which foods, how many eggs or cards. Columns
    that do not apply to the kind are zero.
    """
    bird_ids = action_bird_ids(action)
    spots: list[str] = []  # board spots the action plays at or acts on, once per egg
    bonus_id = habitat = None
    foods: dict[str, int] = {}  # food named, gained, paid or discarded
    foods_given: dict[str, int] = {}  # food handed over in a trade
    eggs = deck_cards = 0
    targets_self = False

    match action:
        case IdAction(type="power_5_bonus", id=i):
            bonus_id = i
        case IdAction(type="choose_player", id=i):
            targets_self = i == state.current_player_index
        case NameAction(type="select_habitat", name=name):
            habitat = name
        case NameAction(name=name):
            foods = {name: 1}
        case PlayBirdAction(row=row, col=col):
            spots = [f"{HABITATS[row]}_{col}"]
        case SelectDieAction(food_type=food):
            foods = {food: 1}
        case TradeAction(from_type=given, to_type=gained):
            foods_given, foods = {given: 1}, {gained: 1}
        case FoodMapAction(items=items):
            foods = dict(items)
        case EggMapAction():
            eggs = len(bird_ids)
        case DrawCardsAction(deck_count=n):
            deck_cards = n
        case SelectInitialAction(kept_bonus=bonus):
            bonus_id = bonus
        case SimpleAction():
            pass  # the kind says it all

    # Birds already on the mover's board are also located by spot, so the net can line the
    # action up with that spot's observation columns (its eggs, row, goal progress).
    # Card ids are unique, so cards in hand or the tray are simply not found here.
    mover = state.players[state.current_player_index]
    board = {
        s.bird.id: f"{habitat}_{s.config.col}"
        for habitat, row in zip(HABITATS, mover.board)
        for s in row
        if s.bird
    }
    spots += [board[b] for b in bird_ids if b in board]

    features = _one_hot("action", action_kind(action), ACTION_KINDS)
    # The average bird (weighted by eggs), so a single bird keeps its features at full scale
    features |= _summed(
        "action_bird",
        bird_feature_names(),
        [bird_table()[b] for b in bird_ids],
        max(len(bird_ids), 1),
    )
    features["action_bird_count"] = _scaled(len(set(bird_ids)), MAX_ACTION_BIRDS)
    features |= _summed(
        "action",
        bonus_feature_names(),
        [bonus_table()[bonus_id]] if bonus_id else [],
    )
    for s in SPOTS:
        features[f"action_spot_{s}"] = _scaled(spots.count(s), MAX_PENDING)
    features |= _one_hot("action_habitat", habitat, HABITATS)
    for food in FOODS:
        features[f"action_food_{food}"] = _scaled(foods.get(food, 0), MAX_PENDING)
    for food in FOODS:
        features[f"action_food_given_{food}"] = _scaled(
            foods_given.get(food, 0), MAX_PENDING
        )
    features["action_eggs"] = _scaled(eggs, MAX_PENDING)
    features["action_deck_cards"] = _scaled(deck_cards, MAX_PENDING)
    features["action_targets_self"] = float(targets_self)
    return features


# =============================================================================
# Vectors and their column names
# =============================================================================


def encode_player(
    state: GameState, player_index: int, viewer_index: int
) -> list[float]:
    return list(player_features(state, player_index, viewer_index).values())


def encode_public(state: GameState) -> list[float]:
    return list(public_features(state).values())


def encode_pending(state: GameState, viewer_index: int) -> list[float]:
    return list(pending_features(state, viewer_index).values())


def encode_action(state: GameState, action: Action) -> list[float]:
    return list(action_features(state, action).values())


def _any_state() -> GameState:
    """The column names do not depend on the state, so any state will do to read them."""
    return initiate_state(2, seed=0)


@cache
def player_feature_names() -> tuple[str, ...]:
    return tuple(player_features(_any_state(), 0, 0))


@cache
def public_feature_names() -> tuple[str, ...]:
    return tuple(public_features(_any_state()))


@cache
def pending_feature_names() -> tuple[str, ...]:
    return tuple(pending_features(_any_state(), 0))


@cache
def shared_feature_names() -> tuple[str, ...]:
    return tuple(shared_features(_any_state(), 0))


@cache
def action_feature_names() -> tuple[str, ...]:
    return tuple(action_features(_any_state(), SimpleAction("gain_food")))
