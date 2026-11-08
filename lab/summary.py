"""Per-arm results of finished or running runs, from their games parquets.

For every arm and opponent: games, win rate (ties count half), mean score difference, and the score
difference averaged per seed over seeds the arm played from both seats (the position swap cancels
seat and deal luck, so this is the precise comparison), all with 95% intervals; plus seconds per game.
When one label is every game's opponent (a `vs_reference` run), only arm-vs-that-label rows are shown;
otherwise (`paired`) each pair once.

    uv run python -m lab.summary DIR [DIR ...]    # run dirs, or folders holding run dirs
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

COLUMNS = ["game_id", "game_seed", "arm_label", "player_position", "total_score", "is_winner", "duration_s"]


def load_games(paths: list[Path]) -> pd.DataFrame:
    """Every games*.parquet under `paths` (runs still in progress included: their finished parts)."""
    files = sorted(f for p in paths for f in Path(p).rglob("games*.parquet"))
    if not files:
        return pd.DataFrame(columns=COLUMNS)
    frames = [pd.read_parquet(f).reindex(columns=COLUMNS) for f in files]  # older runs lack duration_s
    return pd.concat(frames, ignore_index=True)


def _ci(values: pd.Series) -> float:
    return 1.96 * values.std() / math.sqrt(len(values)) if len(values) > 1 else math.nan


def summarize(games: pd.DataFrame) -> pd.DataFrame:
    """One row per (arm, opponent) of 2-player games; see the module docstring."""
    two = games[games.groupby("game_id").game_id.transform("size") == 2]
    other = two.rename(columns={"arm_label": "opponent", "total_score": "opp_score", "player_position": "opp_pos"})
    rows = two.merge(other[["game_id", "opponent", "opp_score", "opp_pos"]], on="game_id")
    rows = rows[rows.player_position != rows.opp_pos]
    rows = rows.assign(
        diff=rows.total_score - rows.opp_score,
        points=rows.is_winner.astype(float) + 0.5 * ~rows.groupby("game_id").is_winner.transform("any"),
    )

    opponents = set(rows.opponent)
    shared = [o for o in opponents if (rows.opponent == o).groupby(rows.game_id).any().all()]
    if shared and len(set(rows.arm_label)) > 2:  # a reference everyone plays
        rows = rows[rows.opponent == shared[0]]
    else:  # each pair once
        rows = rows[rows.arm_label < rows.opponent]

    out = []
    for (arm, opp), r in rows.groupby(["arm_label", "opponent"], sort=False):
        per_seed = r.groupby("game_seed").filter(lambda g: len(g) == 2).groupby("game_seed")["diff"].mean()
        out.append({
            "arm": arm, "opponent": opp, "games": len(r),
            "win_rate": r.points.mean(), "win_ci": 1.96 * math.sqrt(r.points.var() / len(r)) if len(r) > 1 else math.nan,
            "score_diff": r["diff"].mean(), "diff_ci": _ci(r["diff"]),
            "seeds": len(per_seed), "per_seed_diff": per_seed.mean() if len(per_seed) else math.nan,
            "per_seed_ci": _ci(per_seed), "s_per_game": r.duration_s.mean(),
        })
    return pd.DataFrame(out)


def format_summary(table: pd.DataFrame) -> str:
    if table.empty:
        return "no finished 2-player games yet"
    lines = [f"{'arm':<18}{'vs':<14}{'games':>6}{'win rate':>15}{'score diff':>15}{'seeds':>7}{'per-seed diff':>16}{'s/game':>8}"]
    for r in table.itertuples():
        per_seed = f"{r.per_seed_diff:+.1f} ± {r.per_seed_ci:.1f}" if r.seeds > 1 else "-"
        seconds = "-" if math.isnan(r.s_per_game) else f"{r.s_per_game:.1f}" if r.s_per_game < 10 else f"{r.s_per_game:.0f}"
        lines.append(
            f"{r.arm:<18}{r.opponent:<14}{r.games:>6}{r.win_rate:>8.1%} ±{r.win_ci:>4.0%}"
            f"{r.score_diff:>+8.1f} ±{r.diff_ci:>4.1f}{r.seeds:>7}{per_seed:>16}{seconds:>8}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-arm results of runs (win rate, score difference, cost)")
    parser.add_argument("paths", nargs="+", type=Path, help="run dirs, or folders holding run dirs")
    args = parser.parse_args()
    games = load_games(args.paths)
    print(f"{games.game_id.nunique()} games")
    print(format_summary(summarize(games)))


if __name__ == "__main__":
    main()
