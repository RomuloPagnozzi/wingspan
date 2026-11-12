"""The project's history: one JSON line per event, appended to experiments/data/ledger.jsonl.

Nets are overwritten, datasets rebuilt and matches rerun; what they measured stays here. Each event has
`time`, `kind` and `generation` (the newest self-play generation on disk when it was written: the iteration
it belongs to), then its own numbers:

    run               a finished `lab` run: its config, its nets and lab.summary's results
    dataset           a training window built: games per source folder
    train_policy      a policy net trained: per-epoch errors and the validation table
    train_value       a value net trained: per-epoch errors, validation against the score-gap line
    prior_vs_search   how often the search kept the policy's top move, per phase
    verdict           a candidate promoted or rejected

A net is named by `net_id`, a hash of its exported file: it ties a match to the training that made the net
it played, whatever the file was called at the time. The lab UI (lab/ui) reads everything from here.

    uv run python -m lab.ledger verdict result=promoted net=3fa9c1d2    # an event by hand
"""

import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).parent.parent / "experiments" / "data"
LEDGER = DATA / "ledger.jsonl"


def generation_of(folder: str) -> int | None:
    """The generation a self-play folder holds: selfplay and selfplay_homelab are 0, selfplay_g2* is 2."""
    m = re.fullmatch(r"selfplay(?:_g(\d+))?(?:_homelab)?", folder)
    return int(m.group(1) or 0) if m else None


def generation() -> int:
    """The newest self-play generation on disk."""
    return max((g for d in DATA.glob("selfplay*") if (g := generation_of(d.name)) is not None), default=0)


def net_id(path: Path | str) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]


def nets_in(config) -> dict[str, str]:
    """The net files a config names (any string ending in .bin that exists), with their ids."""
    if isinstance(config, dict):
        config = list(config.values())
    if isinstance(config, list):
        return {k: v for item in config for k, v in nets_in(item).items()}
    if isinstance(config, str) and config.endswith(".bin") and Path(config).exists():
        return {config: net_id(config)}
    return {}


def plain(x):
    """JSON types only: numpy scalars and paths converted, NaN as null."""
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if hasattr(x, "item"):  # numpy scalar
        x = x.item()
    if isinstance(x, float):
        return None if math.isnan(x) else x
    return x if isinstance(x, (str, int, bool, type(None))) else str(x)


def record(kind: str, **fields) -> None:
    event = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "generation": generation(), **fields}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(plain(event)) + "\n")


def read() -> list[dict]:
    return [json.loads(line) for line in LEDGER.read_text().splitlines()] if LEDGER.exists() else []


if __name__ == "__main__":
    record(sys.argv[1], **dict(arg.split("=", 1) for arg in sys.argv[2:]))
