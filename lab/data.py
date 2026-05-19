"""Data storage for experiment results using parquet format."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid6 import uuid7

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass
class PlayerResult:
    """Result for a single player in a game."""

    player_position: int
    is_first_player: bool
    is_winner: bool
    strategy_name: str
    simulations: int | None
    exploration_constant: float | None
    value_function: str | None
    strategy_seed: int | None
    total_score: int
    bird_points: int
    egg_points: int
    cached_food: int
    tucked_cards: int
    round_goals: int
    bonus_scores: int
    food_tokens: int


@dataclass
class GameResult:
    """Complete result of a single game."""

    game_id: str
    timestamp: datetime
    player_count: int
    players: list[PlayerResult]
    game_seed: int
    total_decisions: int = 0


@dataclass
class DecisionRecord:
    """A single decision point during a game - one row for RL training."""

    player_position: int
    strategy_seed: int
    round: int
    game_phase: str
    action_taken: str
    legal_actions: list[str]
    visit_counts: dict[str, int] | None = None
    mcts_root_value: float | None = None
    mcts_action_values: dict[str, float] | None = None


@dataclass
class GameDecisions:
    """All decisions from a single game, to be written after game ends."""

    game_id: str
    game_seed: int
    player_outcomes: dict[int, float]
    decisions: list[DecisionRecord] = field(default_factory=list)

    def add_decision(self, record: DecisionRecord) -> None:
        self.decisions.append(record)


def game_result_to_rows(result: GameResult) -> list[dict]:
    """Convert GameResult to list of row dicts (one per player)."""
    rows = []
    for player in result.players:
        rows.append(
            {
                "game_id": result.game_id,
                "timestamp": result.timestamp,
                "game_seed": result.game_seed,
                "player_count": result.player_count,
                "total_decisions": result.total_decisions,
                "player_position": player.player_position,
                "is_first_player": player.is_first_player,
                "is_winner": player.is_winner,
                "strategy_name": player.strategy_name,
                "simulations": player.simulations,
                "exploration_constant": player.exploration_constant,
                "value_function": player.value_function,
                "strategy_seed": player.strategy_seed,
                "total_score": player.total_score,
                "bird_points": player.bird_points,
                "egg_points": player.egg_points,
                "cached_food": player.cached_food,
                "tucked_cards": player.tucked_cards,
                "round_goals": player.round_goals,
                "bonus_scores": player.bonus_scores,
                "food_tokens": player.food_tokens,
            }
        )
    return rows


def decisions_to_rows(game_decisions: GameDecisions) -> list[dict]:
    """Convert GameDecisions to list of row dicts (one per decision)."""
    rows = []
    for idx, decision in enumerate(game_decisions.decisions):
        outcome = game_decisions.player_outcomes.get(decision.player_position, 0.0)
        rows.append(
            {
                "game_id": game_decisions.game_id,
                "decision_idx": idx,
                "player_position": decision.player_position,
                "round": decision.round,
                "game_phase": decision.game_phase,
                "game_seed": game_decisions.game_seed,
                "strategy_seed": decision.strategy_seed,
                "action_taken": decision.action_taken,
                "legal_actions": decision.legal_actions,
                "visit_counts": decision.visit_counts,
                "mcts_root_value": decision.mcts_root_value,
                "mcts_action_values": decision.mcts_action_values,
                "outcome": outcome,
            }
        )
    return rows


GAMES_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("timestamp", pa.timestamp("us")),
        ("game_seed", pa.int64()),
        ("player_count", pa.int32()),
        ("total_decisions", pa.int32()),
        ("player_position", pa.int32()),
        ("is_first_player", pa.bool_()),
        ("is_winner", pa.bool_()),
        ("strategy_name", pa.string()),
        ("simulations", pa.int32()),
        ("exploration_constant", pa.float64()),
        ("value_function", pa.string()),
        ("strategy_seed", pa.int64()),
        ("total_score", pa.int32()),
        ("bird_points", pa.int32()),
        ("egg_points", pa.int32()),
        ("cached_food", pa.int32()),
        ("tucked_cards", pa.int32()),
        ("round_goals", pa.int32()),
        ("bonus_scores", pa.int32()),
        ("food_tokens", pa.int32()),
    ]
)

DECISIONS_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("decision_idx", pa.int32()),
        ("player_position", pa.int32()),
        ("round", pa.int32()),
        ("game_phase", pa.string()),
        ("game_seed", pa.int64()),
        ("strategy_seed", pa.int64()),
        ("action_taken", pa.string()),
        ("legal_actions", pa.list_(pa.string())),
        ("visit_counts", pa.map_(pa.string(), pa.int32())),
        ("mcts_root_value", pa.float64()),
        ("mcts_action_values", pa.map_(pa.string(), pa.float64())),
        ("outcome", pa.float64()),
    ]
)


class GamesWriter:
    """Incremental parquet writer for game results."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "games.parquet"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._writer: pq.ParquetWriter | None = None

    def _ensure_writer(self):
        if self._writer is None:
            self._writer = pq.ParquetWriter(
                self.path, GAMES_SCHEMA, compression="snappy"
            )

    def add_game(self, result: GameResult):
        self._ensure_writer()
        assert self._writer is not None
        rows = game_result_to_rows(result)
        table = pa.Table.from_pylist(rows, schema=GAMES_SCHEMA)
        self._writer.write_table(table)

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DecisionsWriter:
    """Incremental parquet writer for per-decision RL training data."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "decisions.parquet"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._writer: pq.ParquetWriter | None = None

    def _ensure_writer(self):
        if self._writer is None:
            self._writer = pq.ParquetWriter(
                self.path, DECISIONS_SCHEMA, compression="snappy"
            )

    def add_game_decisions(self, game_decisions: GameDecisions):
        if not game_decisions.decisions:
            return
        self._ensure_writer()
        assert self._writer is not None
        rows = decisions_to_rows(game_decisions)
        table = pa.Table.from_pylist(rows, schema=DECISIONS_SCHEMA)
        self._writer.write_table(table)

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def generate_game_id() -> str:
    """Generate a unique game ID using UUID7 (time-ordered)."""
    return str(uuid7())
