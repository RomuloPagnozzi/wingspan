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
    arm_label: str
    strategy_name: str
    strategy_seed: int
    strategy_config: dict[str, str]
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


def game_result_to_rows(result: GameResult, run_id: str) -> list[dict]:
    """Convert GameResult to list of row dicts (one per player)."""
    rows = []
    for player in result.players:
        rows.append(
            {
                "run_id": run_id,
                "game_id": result.game_id,
                "timestamp": result.timestamp,
                "game_seed": result.game_seed,
                "player_count": result.player_count,
                "total_decisions": result.total_decisions,
                "player_position": player.player_position,
                "is_first_player": player.is_first_player,
                "is_winner": player.is_winner,
                "arm_label": player.arm_label,
                "strategy_name": player.strategy_name,
                "strategy_seed": player.strategy_seed,
                "strategy_config": player.strategy_config,
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


def decisions_to_rows(game_decisions: GameDecisions, run_id: str) -> list[dict]:
    """Convert GameDecisions to list of row dicts (one per decision)."""
    rows = []
    for idx, decision in enumerate(game_decisions.decisions):
        outcome = game_decisions.player_outcomes.get(decision.player_position, 0.0)
        rows.append(
            {
                "run_id": run_id,
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
        ("run_id", pa.string()),
        ("game_id", pa.string()),
        ("timestamp", pa.timestamp("us")),
        ("game_seed", pa.int64()),
        ("player_count", pa.int32()),
        ("total_decisions", pa.int32()),
        ("player_position", pa.int32()),
        ("is_first_player", pa.bool_()),
        ("is_winner", pa.bool_()),
        ("arm_label", pa.string()),
        ("strategy_name", pa.string()),
        ("strategy_seed", pa.int64()),
        ("strategy_config", pa.map_(pa.string(), pa.string())),
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
        ("run_id", pa.string()),
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
    """Append-only parquet writer for game results.

    Each run gets its own folder `data_dir/<run_id>/` containing the run's
    games, decisions, and config. The games go into `games.parquet`.
    """

    def __init__(self, data_dir: Path, run_id: str):
        self.run_id = run_id
        self.dir = data_dir / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "games.parquet"
        self._writer: pq.ParquetWriter | None = None

    def _ensure_writer(self):
        if self._writer is None:
            self._writer = pq.ParquetWriter(
                self.path, GAMES_SCHEMA, compression="snappy"
            )

    def add_game(self, result: GameResult):
        self._ensure_writer()
        assert self._writer is not None
        rows = game_result_to_rows(result, self.run_id)
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
    """Append-only parquet writer for per-decision RL training data.

    Each run gets its own folder `data_dir/<run_id>/`; decisions go into
    `decisions.parquet` inside it.
    """

    def __init__(self, data_dir: Path, run_id: str):
        self.run_id = run_id
        self.dir = data_dir / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "decisions.parquet"
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
        rows = decisions_to_rows(game_decisions, self.run_id)
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


def generate_run_id() -> str:
    """Generate a unique run ID using UUID7 (time-ordered)."""
    return str(uuid7())


def generate_game_id() -> str:
    """Generate a unique game ID using UUID7 (time-ordered)."""
    return str(uuid7())


def read_runs(data_dir: Path | str, kind: str):
    """Concat one parquet kind (\"games\" or \"decisions\") across every run.

    Layout: `data_dir/<run_id>/<kind>.parquet`. This wraps a per-file
    `pd.read_parquet` loop because `pd.read_parquet(<dir>)` goes through
    `pyarrow.dataset`, which currently refuses to merge files containing
    `map` columns (`strategy_config`, `visit_counts`, `mcts_action_values`).
    """
    import pandas as pd

    files = sorted(Path(data_dir).glob(f"*/{kind}.parquet"))
    if not files:
        raise FileNotFoundError(f"No {kind}.parquet files under {data_dir}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
