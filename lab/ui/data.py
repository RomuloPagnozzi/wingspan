"""What the lab UI shows, read from experiments/data: the ledger (lab/ledger.py) for everything finished,
the games parquets for the self-play generations and for runs the ledger doesn't hold yet (running, or
played before the ledger existed). Parquet parts never change once closed, so each is read once.
"""

import json
import math
import os
import re
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import yaml

from lab import ledger
from lab.ui import jobs as queue
from lab.generators import count_games
from lab.summary import COLUMNS, PARTS, as_dict

DATA = ledger.DATA
DRIVE = Path("/Volumes/External Drive/wingspan")
TARGET_GAMES = 20_000  # a generation, docs/SELFPLAY_LOOP.md step 1
NOT_RUNS = {"datasets", "logs", "models", "cloud", "jobs"}
# What a match is for in the self-play loop, by its output folder (docs/SELFPLAY_LOOP.md step 6)
ROLES = {"candidate_policy_match": "sanity", "candidate_puct_match": "decision", "policy_match": "anchor_policy",
         "puct_match": "anchor_puct", "puct_value_match": "leaf"}  # fmt: skip

_parts: dict[tuple, pd.DataFrame] = {}
_cache: dict[str, tuple] = {}


def cached(name: str, key, compute):
    if _cache.get(name, (None,))[0] != key:
        _cache[name] = (key, compute())
    return _cache[name][1]


def _read(f: Path) -> pd.DataFrame | None:
    try:
        have = set(pq.read_schema(f).names)  # older runs lack duration_s
        table = pq.read_table(f, columns=[c for c in [*COLUMNS, "timestamp"] if c in have])
        return table.to_pandas().reindex(columns=[*COLUMNS, "timestamp"])
    except Exception:  # still being written
        return None


def games_of(dirs: list[Path]) -> pd.DataFrame:
    """The finished games under `dirs`; a file still being written (unreadable) is skipped. A generation is
    hundreds of parts: the ones not read yet are read in parallel."""
    keys = [(f, f.stat().st_mtime_ns) for f in sorted(f for d in dirs for f in d.rglob("games*.parquet"))]
    new = [k for k in keys if k not in _parts]
    with ThreadPoolExecutor(8) as pool:
        _parts.update({k: frame for k, frame in zip(new, pool.map(_read, [f for f, _ in new])) if frame is not None})
    frames = [_parts[k] for k in keys if k in _parts]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=[*COLUMNS, "timestamp"])


def is_open(run_dir: Path) -> bool:
    """A run is being written: a part of it changed in the last 10 minutes and it has an open one (a .tmp,
    or an unrotated parquet that can't be read yet). Crashed runs leave .tmp parts too, but old ones."""
    files = list(run_dir.glob("*.tmp")) + list(run_dir.glob("*.parquet"))
    recent = any(datetime.now().timestamp() - f.stat().st_mtime < 600 for f in files)
    unreadable = (run_dir / "games.parquet").exists() and games_of([run_dir]).empty
    return recent and (unreadable or any(run_dir.glob("*.tmp")))


def started(run_id: str) -> str:
    """A run id is a UUID7: its first 48 bits are the time it was made, in milliseconds."""
    return datetime.fromtimestamp(int(run_id.replace("-", "")[:12], 16) / 1000).isoformat(timespec="seconds")


def generations() -> list[dict]:
    by_gen: dict[int, list[Path]] = {}
    for d in sorted(DATA.iterdir()):
        if d.is_dir() and (g := ledger.generation_of(d.name)) is not None:
            by_gen.setdefault(g, []).append(d)
    return [cached(f"gen{g}", _signature(dirs), lambda: _generation(g, dirs)) for g, dirs in sorted(by_gen.items())]


def _signature(dirs: list[Path]) -> tuple:
    """Changes when a part is added or closed."""
    files = [f for d in dirs for f in d.rglob("games*")]
    return (len(files), max((f.stat().st_mtime_ns for f in files), default=0), datetime.now().hour)


def _generation(g: int, dirs: list[Path]) -> dict:
    games = games_of(dirs)
    per_game = games.drop_duplicates("game_id")
    now = pd.Timestamp.now()
    sources = []
    for d in dirs:
        t = games_of([d]).drop_duplicates("game_id").timestamp
        runs = [r for r in d.iterdir() if r.is_dir()]
        sources.append({
            "folder": d.name, "games": len(t), "runs": len(runs), "running": any(is_open(r) for r in runs),
            "first": t.min().isoformat() if len(t) else None, "last": t.max().isoformat() if len(t) else None,
            "per_hour": int((t > now - timedelta(hours=1)).sum()),  # a server's clock may be in another timezone
        })  # fmt: skip
    # Seat against seat: both run the same search, so 50% and ±0 points, or something is broken
    score = games.pivot(index="game_id", columns="arm_label", values="total_score").dropna()
    diff = score.iloc[:, 0] - score.iloc[:, 1] if score.shape[1] == 2 else pd.Series(dtype=float)
    wins = (diff > 0) + 0.5 * (diff == 0)
    ci = lambda x: float(1.96 * x.std() / math.sqrt(len(x)))
    hourly = per_game.set_index("timestamp").resample("1h").size().cumsum() if len(per_game) else pd.Series(dtype=int)
    return {
        "generation": g, "games": len(per_game), "deals": int(per_game.game_seed.nunique()),
        "worker_hours": float(per_game.duration_s.sum() / 3600), "sources": sources,
        "seats": {"arm": score.columns[0], "win_rate": float(wins.mean()), "win_ci": ci(wins), "score_diff": float(diff.mean()),
                  "diff_ci": ci(diff)} if len(diff) > 1 else None,
        "parts": {name: float(games[c].mean()) for c, name in PARTS.items()} if len(games) else {},
        "wins_first": float(games[games.is_first_player == True].is_winner.mean()) if len(games) else None,  # noqa: E712
        "timeline": [[t.isoformat(), int(n)] for t, n in hourly.items()],
    }  # fmt: skip


def _pooled(runs: list[dict]) -> dict:
    """Runs of one match (same folder, config and nets: more deals of the same question) as one result."""
    arms = []
    for key in dict.fromkeys((a["arm"], a["opponent"]) for r in runs for a in r["arms"]):
        rows = [a for r in runs for a in r["arms"] if (a["arm"], a["opponent"]) == key]
        n = sum(a["games"] for a in rows)
        arm = rows[0] | {"games": n, "seeds": sum(a["seeds"] for a in rows)}
        if len(rows) > 1:
            mean = lambda field: sum(a[field] * a["games"] for a in rows) / n
            ci = lambda field: math.sqrt(sum((a[field] * a["games"]) ** 2 for a in rows)) / n
            diffs = pd.Series([d for a in rows for d in a["seed_diffs"]])
            arm |= {"win_rate": mean("win_rate"), "win_ci": ci("win_ci"), "score_diff": mean("score_diff"), "diff_ci": ci("diff_ci"),
                    "s_per_game": mean("s_per_game"), "seed_diffs": diffs.tolist(), "per_seed_diff": diffs.mean(),
                    "per_seed_ci": 1.96 * diffs.std() / math.sqrt(len(diffs))}  # fmt: skip
        arms.append(arm)
    parts = []
    for label in dict.fromkeys(p["arm_label"] for r in runs for p in r["parts"]):
        rows = [p for r in runs for p in r["parts"] if p["arm_label"] == label]
        n = sum(p["games"] for p in rows)
        parts.append({k: sum((p[k] or 0) * p["games"] for p in rows) / n for k in rows[0] if k not in ("arm_label", "games")}
                     | {"arm_label": label, "games": n})  # fmt: skip
    last = runs[-1]
    totals = [r["total"] if "running" in r else r["games"] for r in runs]  # an unrecorded run: what its config plays
    return {
        "experiment": last["experiment"], "role": ROLES.get(last["experiment"], "experiment"),
        "description": last.get("description", ""), "generation": last["generation"], "time": last["time"],
        "runs": [r["run_id"] for r in runs], "nets": last.get("nets", {}), "config": last["config"],
        "games": sum(r["games"] for r in runs), "worker_hours": sum(r["worker_hours"] or 0 for r in runs),
        "total": None if None in totals else sum(totals),
        "running": any(r.get("running") for r in runs), "progress": all(r.get("progress", True) for r in runs), "recorded": all("running" not in r for r in runs),
        "arms": arms, "parts": parts,
    }  # fmt: skip


def _unrecorded(run_dir: Path) -> dict:
    """A run the ledger doesn't hold, shaped like its ledger event, from the games it has so far."""
    config = yaml.safe_load((run_dir / "config.yaml").read_text())
    games = games_of([run_dir])
    progress = run_dir / "progress.json"  # written by lab after every game; older runs have none
    played = json.loads(progress.read_text())["games"] if progress.exists() else 0
    summary = ledger.plain(as_dict(games))
    return summary | {
        "games": max(summary["games"], played), "time": games.timestamp.max().isoformat() if len(games) else started(run_dir.name), "generation": ledger.generation(),
        "experiment": run_dir.parent.name, "run_id": run_dir.name, "config": config, "nets": {},
        "description": (run_dir / "config.yaml").read_text().split("\n")[0].lstrip("# "),
        "running": is_open(run_dir), "total": count_games(config), "progress": progress.exists() or len(games) > 0,
    }  # fmt: skip


def matches(events: list[dict]) -> list[dict]:
    """Every match, oldest first: the ledger's runs, then the runs on disk it doesn't hold. Self-play runs
    are the generations, not matches."""
    recorded = {e["run_id"] for e in events if e["kind"] == "run"}
    runs = [e for e in events if e["kind"] == "run" and ledger.generation_of(e["experiment"]) is None]
    for d in sorted(DATA.iterdir()):
        if d.is_dir() and d.name not in NOT_RUNS and ledger.generation_of(d.name) is None:
            for run_dir in sorted(d.iterdir()):
                if run_dir.name not in recorded and (run_dir / "config.yaml").exists():
                    key = (len(list(run_dir.iterdir())), max(f.stat().st_mtime_ns for f in run_dir.iterdir()), is_open(run_dir))
                    runs.append(cached(str(run_dir), key, lambda: _unrecorded(run_dir)))
    groups: dict[str, list[dict]] = {}
    for r in runs:
        question = {k: v for k, v in r["config"].items() if k not in ("seeds", "num_workers")}
        groups.setdefault(json.dumps([r["experiment"], r["generation"], question, r.get("nets")], sort_keys=True), []).append(r)
    return sorted((_pooled(g) for g in groups.values()), key=lambda m: m["time"])


def _dataset(d: Path) -> dict:
    meta = json.loads((d / "meta.json").read_text())
    return {"name": d.name, "games": len(meta["games"]), "decisions": meta["n_decisions"],
            "window": Counter(meta.get("folders", [])), "gb": sum(f.stat().st_size for f in d.rglob("*.npy")) / 1e9,
            "built": datetime.fromtimestamp((d / "meta.json").stat().st_mtime).isoformat(timespec="seconds")}  # fmt: skip


def files() -> dict:
    """The nets and datasets on disk, the logs, and the machine."""
    models = [
        {"name": f.name, "net": cached(str(f), f.stat().st_mtime_ns, lambda: ledger.net_id(f)),
         "saved": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
        for f in sorted((DATA / "models").glob("*.bin"))
    ]  # fmt: skip
    datasets = [cached(str(m), m.stat().st_mtime_ns, lambda: _dataset(m.parent)) for m in sorted((DATA / "datasets").glob("*/meta.json"))]
    logs = sorted((DATA / "logs").glob("*.log"), key=lambda f: -f.stat().st_mtime)
    busy = subprocess.run(["pgrep", "-fl", "python.* -m lab"], capture_output=True, text=True).stdout.splitlines()
    return {
        "models": models, "datasets": datasets, "drive": DRIVE.exists(),
        "logs": [{"name": f.name, "changed": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")} for f in logs],
        "disk_free_gb": shutil.disk_usage(DATA).free / 1e9,
        "busy": sorted({cmd for line in busy if "python" in (cmd := line.partition(" ")[2]).partition(" ")[0] and "lab.ui" not in cmd}),  # not uv or
        # caffeinate wrapping it; a run's workers repeat its command line
    }  # fmt: skip


# Threads the loop's jobs are run on: 7 workers on the laptop's 8, 2 on the home server (3 overheat it):
# docs/SELFPLAY_LOOP.md step 7
USABLE = {"laptop": 7, "home server": 2}


# docs/SELFPLAY_LOOP.md step 1: no restart, then Ctrl+C (in-flight games finish)
HOME_STOP = "docker update --restart=no wingspan-selfplay && docker kill --signal=INT wingspan-selfplay"


def _is_lab(command: str) -> bool:
    return "python" in command.partition(" ")[0] and " -m lab" in command and "lab.ui" not in command


def _laptop() -> dict:
    """This machine: threads busy (ps's recent CPU share, summed over processes), and each lab command with
    the processes working for it (its workers are its children)."""
    procs = {}
    for line in subprocess.run(["ps", "-axo", "pid=,ppid=,pcpu=,rss=,command="], capture_output=True, text=True).stdout.splitlines():
        fields = line.split(None, 4)
        if len(fields) == 5:
            procs[int(fields[0])] = (int(fields[1]), float(fields[2].replace(",", ".")) / 100, int(fields[3]) / 1e6, fields[4])
    in_queue = {j["pid"]: j["id"] for j in queue.load() if j["status"] == "running"}  # a command run by the queue stops through its job
    jobs: dict[int, dict] = {}
    for pid, (_, cpu, gb, _) in procs.items():
        owner = pid
        while owner in procs and not _is_lab(procs[owner][3]):
            owner = procs[owner][0]
        if owner in procs:
            chain, up = [], owner
            while up in procs and up not in chain:
                chain.append(up)
                up = procs[up][0]
            job = jobs.setdefault(owner, {"pid": owner, "command": procs[owner][3], "processes": 0, "threads": 0.0, "gb": 0.0,
                                          "queue_job": next((in_queue[a] for a in chain if a in in_queue), None)})  # fmt: skip
            job |= {"processes": job["processes"] + 1, "threads": job["threads"] + cpu, "gb": job["gb"] + gb}
    threads = os.cpu_count()
    lab_threads = sum(j["threads"] for j in jobs.values())
    return {"name": "laptop", "threads": threads, "usable": USABLE["laptop"], "lab": min(lab_threads, threads),
            "busy": min(sum(p[1] for p in procs.values()), threads), "jobs": list(jobs.values())}  # fmt: skip


def _home_server() -> dict:
    """The home server over ssh (read only): its threads, load average and the self-play container."""
    ask = 'nproc; cut -d" " -f1 /proc/loadavg; docker ps -a --filter name=wingspan-selfplay --format "{{.State}}: {{.Status}}"'
    try:
        out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", "homelab", ask], capture_output=True, text=True, timeout=8)
        threads, load, *container = out.stdout.splitlines()
    except (subprocess.TimeoutExpired, ValueError):
        return {"name": "home server", "reachable": False}
    running = bool(container) and container[0].startswith("running")
    return {"name": "home server", "reachable": True, "threads": int(threads), "usable": USABLE["home server"], "busy": min(float(load), int(threads)),
            "lab": min(float(load), int(threads)) if running else 0.0,
            "stop": HOME_STOP if running else None,
            "jobs": [{"command": "Self-play (the wingspan-selfplay container)", "stoppable": running,
                     "status": re.sub(r"^\w+: | \(\d+\)", "", container[0]) if container else "no container"}]}  # fmt: skip


def compute() -> list[dict]:
    return [_laptop(), cached("home server", int(time.time() // 60), _home_server)]


def overview() -> dict:
    events = ledger.read()
    return {
        "now": datetime.now().isoformat(timespec="seconds"), "generation": ledger.generation(), "target_games": TARGET_GAMES,
        "generations": generations(), "matches": matches(events), "events": [e for e in events if e["kind"] != "run"],
        "compute": compute(), **files(),
    }  # fmt: skip
