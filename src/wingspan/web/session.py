"""A single game against AI opponents, and its JSON view for the browser client."""

import math
from dataclasses import asdict

from wingspan.engine.actions import get_actions
from wingspan.engine.core import (
    BIRD_REGISTRY,
    BONUS_REGISTRY,
    GamePhase,
    SimpleAction,
    IdAction,
    NameAction,
    PlayBirdAction,
    SelectDieAction,
    TradeAction,
    FoodMapAction,
    EggMapAction,
    DrawCardsAction,
    SelectInitialAction,
    ScoringMode,
    get_bird_power,
    init_registries,
    initiate_state,
)
from wingspan.engine.engine import transition_state
from wingspan.engine.scoring import count_bonus_birds, evaluate_goal, goal_scores, score_bonus_card
from wingspan.ai import create_strategy

HUMAN = 0
HABITATS = ("forest", "grassland", "wetland")
CUBE_ROWS = {
    "play_bird": -1,
    "gain_food": 0,
    "lay_eggs": 1,
    "draw_cards": 2,
}  # -1: "Play a bird" row


# =============================================================================
# Card catalog (sent once)
# =============================================================================


def _clean(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def catalog() -> dict:
    init_registries()
    birds = {}
    for b in BIRD_REGISTRY.values():
        p = get_bird_power(b.id)
        birds[b.id] = {
            "id": b.id,
            "name": b.name,
            "habitats": list(b.habitats),
            "cost": [[list(fc) for fc in alt] for alt in b.cost],
            "points": b.points,
            "nest": _clean(b.nest) or "none",
            "eggs": b.egg_limit,
            "wingspan": b.wingspan,
            "power": (
                {"text": p["text"], "color": p["color"], "trigger": p["trigger"]}
                if _clean(p.get("text"))
                else None
            ),
        }
    bonuses = {
        b.id: {
            "id": b.id,
            "name": b.name.replace("_", " ").title(),
            "condition": b.condition,
            "params": b.score_params,
        }
        for b in BONUS_REGISTRY.values()
    }
    return {"birds": birds, "bonuses": bonuses}


# =============================================================================
# Action descriptions ([token] syntax is rendered as icons by the client)
# =============================================================================

SIMPLE_LABELS = {
    "start_setup": "Start setup",
    "end_setup": "Finish setup",
    "play_bird": "Play a bird",
    "gain_food": "Gain food",
    "lay_eggs": "Lay eggs",
    "draw_cards": "Draw cards",
    "trade_bird": "Discard a [card] for +1 [die]",
    "trade_food": "Discard a food for +1 [egg]",
    "trade_egg": "Discard an [egg] for +1 [card]",
    "skip_trade": "No thanks",
    "reroll_all": "Reroll the birdfeeder",
    "skip_power": "Skip",
    "activate_power": "Activate",
    "cache_food": "Cache it on this bird",
    "supply_food": "Keep it in supply",
}

ID_VERBS = {
    "discard_card": "Discard",
    "discard_bird": "Discard",
    "discard_egg": "Discard [egg] from",
    "discard_egg_from": "Discard [egg] from",
    "select_card": "Take",
    "select_bird": "Choose",
    "tuck_card": "Tuck",
}


def _food_map(items) -> str:
    return " ".join(f"[{food}]" * n for food, n in items if n) or "nothing"


def _egg_map(items) -> str:
    return ", ".join(f"{n}[egg] {BIRD_REGISTRY[b].name}" for b, n in items if n)


def describe(a) -> str:
    bird = lambda i: BIRD_REGISTRY[i].name  # noqa: E731
    match a:
        case SimpleAction(t):
            return SIMPLE_LABELS.get(t, t.replace("_", " ").capitalize())
        case IdAction("choose_player", i):
            return f"Player {i + 1}"
        case IdAction("power_5_bonus", i):
            return f"Keep bonus: {BONUS_REGISTRY[i].name.replace('_', ' ').title()}"
        case IdAction(t, i):
            return f"{ID_VERBS.get(t, t)} {bird(i)}"
        case NameAction("select_habitat", h):
            return f"[{h}]"
        case NameAction(t, food):
            verb = "Discard" if t.startswith("discard") else "Take"
            return f"{verb} [{food}]"
        case PlayBirdAction(b, row, col):
            return f"Play {bird(b)} in [{HABITATS[row]}]"
        case SelectDieAction(_, food):
            return f"Take [{food}]"
        case TradeAction(f, t):
            return f"Trade [{f}] → [{t}]"
        case FoodMapAction(t, items):
            verb = {"pay_food": "Pay", "discard_food_combo": "Discard"}.get(t, "Gain")
            return f"{verb} {_food_map(items)}"
        case EggMapAction(t, items):
            verb = "Pay" if t == "pay_eggs" else "Lay"
            return f"{verb} {_egg_map(items)}"
        case DrawCardsAction(tray, deck):
            parts = [bird(b) for b in tray] + (
                [f"{deck}[card] from deck"] if deck else []
            )
            return "Draw " + ", ".join(parts)
        case SelectInitialAction(kept, bonus):
            return f"Keep {len(kept)} birds + {BONUS_REGISTRY[bonus].name}"
    return str(a)


def bonus_progress(bonus_id: int, player) -> dict:
    bonus = BONUS_REGISTRY[bonus_id]
    return {
        "count": count_bonus_birds(bonus, player),
        "score": score_bonus_card(bonus, player),
    }


def action_json(i: int, a) -> dict:
    d = asdict(a)
    for k in ("items", "tray_birds", "kept_birds"):
        if k in d:
            d[k] = [list(x) if isinstance(x, tuple) else x for x in d[k]]
    return {"i": i, "t": type(a).__name__, "label": describe(a), **d}


# =============================================================================
# Session
# =============================================================================


class Session:
    def __init__(
        self,
        players: int = 2,
        ai: str = "mcts",
        scoring: str = "green",
        ai_params: dict | None = None,
        seed: int | None = None,
    ):
        self.ai_name = ai
        self.state = initiate_state(players, ScoringMode(scoring), seed=seed)
        self.ai = {i: create_strategy(ai, **(ai_params or {})) for i in range(1, players)}
        self.log: list[dict] = []
        self.version = 0  # bumped by every applied action; clients echo it to avoid acting on a stale view
        self.last_round = 0
        # Action cubes placed this round, per player: the board row of each main action (CUBE_ROWS)
        self.cubes: list[list[int]] = [[] for _ in range(players)]
        # Goal counts frozen at the moment each round was scored (boards keep changing afterwards)
        self.final_counts: dict[int, list[int]] = {}
        self.actions = get_actions(self.state)
        self.skip_trivial()

    def apply(self, action):
        self.version += 1
        s = self.state
        if s.round != self.last_round and s.game_phase == GamePhase.MAIN_TURN:
            self.last_round = s.round
            self.log.append({"round": s.round})
        if action.__class__ is not SimpleAction or "setup" not in action.type:
            self.log.append({"p": s.current_player_index, "text": describe(action)})
        self.track_cube(action)
        round_before = s.round
        self.state = transition_state(s, action)
        self.actions = get_actions(self.state)
        if (
            self.state.round != round_before
            or self.state.game_phase == GamePhase.GAME_OVER
        ):
            if round_before not in self.final_counts:
                self.final_counts[round_before] = self.goal_counts(round_before)
        if self.state.round != round_before:
            self.cubes = [[] for _ in self.cubes]

    def goal_counts(self, round_num: int) -> list[int]:
        s = self.state
        goal = s.round_goal_config.selected_goals[round_num - 1]
        return [evaluate_goal(s, p, goal) for p in s.players]

    def goal_json(self, round_num: int) -> dict:
        """A round goal's standings: final once scored, otherwise the points if scored now."""
        s = self.state
        if round_num in self.final_counts:
            counts = self.final_counts[round_num]
            points = [p.score.round_goals[round_num - 1] for p in s.players]
            status = "final"
        else:
            counts = self.goal_counts(round_num)
            projected = goal_scores(s, round_num)
            points = [projected.get(p.id, 0) for p in s.players]
            status = "live" if round_num == s.round else "preview"
        return {
            "name": s.round_goal_config.selected_goals[round_num - 1],
            "counts": counts,
            "points": points,
            "status": status,
        }

    def track_cube(self, action):
        """Record which row the acting player's cube goes on, like on the physical board."""
        s = self.state
        if (
            s.game_phase == GamePhase.MAIN_TURN
            and isinstance(action, SimpleAction)
            and action.type in CUBE_ROWS
        ):
            self.cubes[s.current_player_index].append(CUBE_ROWS[action.type])

    def human_turn(self) -> bool:
        return bool(self.actions) and self.state.current_player_index == HUMAN

    def act(self, index: int):
        assert self.human_turn()
        self.apply(self.actions[index])
        self.skip_trivial()

    def ai_player(self) -> int | None:
        """The AI to move next, if it's an AI's turn."""
        if self.actions and not self.human_turn():
            return self.state.current_player_index
        return None

    def ai_act(self, action):
        self.apply(action)
        self.skip_trivial()

    def skip_trivial(self):
        """Auto-apply the human's bookkeeping-only setup actions."""
        while self.human_turn() and self.actions[0] in (
            SimpleAction("start_setup"),
            SimpleAction("end_setup"),
        ):
            self.apply(self.actions[0])

    # -------------------------------------------------------------------------

    def view(self) -> dict:
        s = self.state
        me = self.human_turn()
        goals = s.round_goal_config
        assert goals
        return {
            "version": self.version,
            "round": s.round,
            "phase": s.game_phase.value,
            "current": s.current_player_index,
            "turn_player": (
                s.action_data.action_player_index
                if s.game_phase == GamePhase.ACTIVATE_POWERS
                and s.action_data.action_player_index is not None
                else s.current_player_index
            ),
            "human": HUMAN,
            "game_over": s.game_phase == GamePhase.GAME_OVER,
            "scoring_mode": goals.scoring_mode.value,
            "goals": [self.goal_json(r) for r in range(1, 5)],
            "feeder": {str(k): v for k, v in s.feeder.items()},
            "tray": list(s.bird_tray),
            "deck": len(s.bird_deck),
            "players": [self.player_json(i, p) for i, p in enumerate(s.players)],
            "actions": (
                [action_json(i, a) for i, a in enumerate(self.actions)] if me else []
            ),
            "prompt": self.prompt() if me else None,
            # Where you'd stand on each offered bonus card right now (power 5)
            "bonus_offer": {
                a.id: bonus_progress(a.id, s.players[HUMAN])
                for a in self.actions
                if me and isinstance(a, IdAction) and a.type == "power_5_bonus"
            },
            "focus": self.focus(),
            "log": self.log[-120:],
        }

    def player_json(self, i: int, p) -> dict:
        board = [
            [
                (
                    None
                    if spot.bird is None
                    else {
                        "id": spot.bird.id,
                        "eggs": spot.bird.state.eggs,
                        "cached": spot.bird.state.stashed_food,
                        "tucked": spot.bird.state.tucked_cards,
                    }
                )
                for spot in row
            ]
            for row in p.board
        ]
        birds = [b for row in board for b in row if b]
        bonus = {b: bonus_progress(b, p) for b in p.bonus_hand}
        score = {
            "birds": sum(BIRD_REGISTRY[b["id"]].points for b in birds),
            "bonus": sum(v["score"] for v in bonus.values()),
            "goals": sum(p.score.round_goals),
            "eggs": sum(b["eggs"] for b in birds),
            "cached": sum(b["cached"] for b in birds),
            "tucked": sum(b["tucked"] for b in birds),
        }
        score["total"] = sum(score.values())
        visible = i == HUMAN or self.state.game_phase == GamePhase.GAME_OVER
        return {
            "name": "You" if i == HUMAN else f"{self.ai_name.upper()} {i + 1}",
            "ai": i != HUMAN,
            "first": p.first_player,
            "cubes": 9
            - self.state.round
            - len(self.cubes[i]),  # matches the cubes drawn on the board
            "cubes_total": 9 - self.state.round,
            "cubes_used": self.cubes[i],
            "food": p.food,
            "hand": list(p.bird_hand) if visible else len(p.bird_hand),
            "bonus": list(p.bonus_hand) if visible else len(p.bonus_hand),
            "bonus_progress": bonus if visible else {},
            "round_goals": list(p.score.round_goals),
            "board": board,
            "score": score,
        }

    def focus(self) -> dict | None:
        """The bird whose power is currently resolving, if any."""
        ad = self.state.action_data
        if self.state.game_phase != GamePhase.ACTIVATE_POWERS:
            return None
        src = ad.get_current_execution() or ad.get_current_queued_power()
        if src is None:
            return None
        return {
            "bird": src.bird_id,
            "player": src.player_index,
            "row": src.spot_row,
            "col": src.spot_col,
            "queued": not ad.execution_stack,
        }

    def prompt(self) -> str:
        s, ad = self.state, self.state.action_data
        match s.game_phase:
            case GamePhase.SELECT_INITIAL_CARDS:
                return "Keep any birds and 1 bonus card — discard 1 food per bird kept"
            case GamePhase.DISCARD_FOOD:
                return f"Discard {ad.amount_to_discard} food"
            case GamePhase.MAIN_TURN:
                return "Choose an action"
            case GamePhase.COLLECT_FOOD:
                return f"Take {ad.food_needed} [die] from the birdfeeder"
            case GamePhase.LAY_EGGS:
                return f"Lay {ad.eggs_needed} [egg]"
            case GamePhase.DRAW_CARDS:
                return f"Draw {ad.cards_needed} [card] from the tray or deck"
            case GamePhase.PLAY_BIRD:
                return "Pick a bird from your hand, then a habitat"
            case GamePhase.PAY_FOOD_COST:
                return "Pay the food cost"
            case GamePhase.PAY_EGG_COST:
                return f"Pay {ad.pending_cost and ad.pending_cost.amount} [egg]"
            case GamePhase.EXTRA_FOOD_ACTION:
                return "Discard a [card] to gain 1 more [die]?"
            case GamePhase.EXTRA_LAY_EGGS_ACTION:
                return "Discard a food to lay 1 more [egg]?"
            case GamePhase.EXTRA_CARD_DRAW_ACTION:
                return "Discard an [egg] to draw 1 more [card]?"
            case GamePhase.SELECT_BIRD_TO_DISCARD:
                return "Discard a [card] from your hand"
            case GamePhase.SELECT_FOOD_TO_DISCARD:
                return "Discard a food"
            case GamePhase.SELECT_EGG_TO_DISCARD:
                return "Discard an [egg]"
            case GamePhase.END_TURN:
                return "Discard a [card] from your hand"
            case GamePhase.ACTIVATE_POWERS:
                f = self.focus()
                assert f
                name = BIRD_REGISTRY[f["bird"]].name
                text = get_bird_power(f["bird"])["text"]
                verb = "Activate" if f["queued"] else "Resolve"
                return f"{verb} {name}: {text}"
        return s.game_phase.value.replace("_", " ").capitalize()
