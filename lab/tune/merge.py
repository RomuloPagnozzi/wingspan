"""Collapse per-trial parquet folders into one file per kind at the study root.

After a study, `study_dir/` looks like:
    study_dir/<run_id>/games.parquet
    study_dir/<run_id>/decisions.parquet
This module concatenates them into `study_dir/games.parquet` and
`study_dir/decisions.parquet`, then removes the per-run folders.

The `run_id` column is preserved on every row, so a merged file is fully
self-describing — trials.csv remains the join key into Optuna's metadata.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow.parquet as pq

DEFAULT_KINDS = ("games", "decisions")


def _merge_one_kind(study_dir: Path, kind: str) -> int:
    """Concat all `<run_id>/<kind>.parquet` into `<study_dir>/<kind>.parquet`.

    Returns number of source files merged (0 if none found).
    """
    sources = sorted(study_dir.glob(f"*/{kind}.parquet"))
    if not sources:
        return 0

    out_path = study_dir / f"{kind}.parquet"
    writer: pq.ParquetWriter | None = None
    try:
        for src in sources:
            table = pq.read_table(src)
            if writer is None:
                writer = pq.ParquetWriter(out_path, table.schema, compression="snappy")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    return len(sources)


def merge_study(
    study_dir: Path,
    kinds: tuple[str, ...] = DEFAULT_KINDS,
    delete_sources: bool = True,
) -> dict[str, int]:
    """Merge per-trial parquets into one file per kind at the study root.

    Returns {kind: n_files_merged}. With `delete_sources=True`, per-run
    folders that only held the merged kinds are removed afterward.
    """
    study_dir = Path(study_dir)
    if not study_dir.is_dir():
        raise FileNotFoundError(f"study dir not found: {study_dir}")

    counts = {kind: _merge_one_kind(study_dir, kind) for kind in kinds}

    if delete_sources and any(counts.values()):
        merged_names = {f"{k}.parquet" for k in kinds}
        for sub in study_dir.iterdir():
            if not sub.is_dir():
                continue
            leftover = [p for p in sub.iterdir() if p.name not in merged_names]
            if leftover:
                continue
            shutil.rmtree(sub)

    return counts
