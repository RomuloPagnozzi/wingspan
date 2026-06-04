"""Merge a continuation run's parquets back into the original run.

Reads games/decisions from each source run, overwrites every row's run_id
with the canonical one, concatenates per kind, and writes the result to
`<data_dir>/<canonical_run_id>/{games,decisions}.parquet` (snappy).

Usage (edit the constants and run, or import and call merge_runs()):

    uv run python -m lab.tools.merge_runs
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from lab.data import GAMES_SCHEMA, DECISIONS_SCHEMA

DATA_DIR = Path("experiments/data")
CANONICAL_RUN_ID = "019e61cc-cc47-72f2-aaa4-a239c0195fd7"
SOURCE_RUN_IDS = [
    "019e61cc-cc47-72f2-aaa4-a239c0195fd7",
    "019e6445-05f4-7b7c-9481-fd63a21f75d5",
]


def _concat(kind: str, schema: pa.Schema) -> None:
    frames: list[pd.DataFrame] = []
    for rid in SOURCE_RUN_IDS:
        path = DATA_DIR / rid / f"{kind}.parquet"
        if not path.exists():
            print(f"  skip: no {kind} parquet in {rid}")
            continue
        df = pd.read_parquet(path)
        print(f"  {rid}/{kind}: {len(df)} rows")
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)
    merged["run_id"] = CANONICAL_RUN_ID

    out = DATA_DIR / CANONICAL_RUN_ID / f"{kind}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pandas(merged, schema=schema, preserve_index=False),
        out,
        compression="snappy",
    )
    print(f"  -> {out}  ({len(merged)} rows)")


def main() -> None:
    print("Merging games...")
    _concat("games", GAMES_SCHEMA)
    print("Merging decisions...")
    _concat("decisions", DECISIONS_SCHEMA)


if __name__ == "__main__":
    main()
