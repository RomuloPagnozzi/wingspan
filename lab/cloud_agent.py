"""Runs on the rented server and makes it independent of the laptop (see lab/cloud.py).

    python -m lab.cloud_agent run      # the session: generate, upload, stop at the deadline, self-destroy
    python -m lab.cloud_agent guard    # a backup, every 10 min: destroy if still up an hour past the deadline

`run` starts one endless self-play run whose files rotate every few hundred games, uploads every
finished part to object storage each minute with a status.json, and at the deadline (or when
control/stop appears) stops the run gracefully: in-flight games finish and the last part is
closed. Then it uploads, and destroys the server through the Vultr API with a key restricted to
managing servers. A crashed run is restarted once; crashing twice within 10 minutes ends the
session early rather than paying for a broken setup.

The control folder ($WINGSPAN_CONTROL, default /root/wingspan/control) holds:
    agent.json   run name, lab config, rotation, first seed, upload command, server id
    deadline     ISO time in UTC; `lab.cloud extend` rewrites it
    stop         optional: present means wrap up now
Secrets (the restricted API key, storage keys) come from the environment, never from these files.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq
import yaml

CONTROL = Path(os.environ.get("WINGSPAN_CONTROL", "/root/wingspan/control"))
STOP_GRACE = 20 * 60  # in-flight games get this long to finish after the stop signal
GUARD_SLACK = timedelta(hours=1)


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def settings() -> dict:
    return json.loads((CONTROL / "agent.json").read_text())


def deadline() -> datetime:
    return datetime.fromisoformat((CONTROL / "deadline").read_text().strip())


def parts(runs: Path, table: str) -> list[Path]:
    """Closed, complete parts only: the one still being written is a .tmp."""
    return sorted(runs.glob(f"*/{table}_*.parquet"))


def games_saved(runs: Path) -> tuple[int, int | None]:
    """(games in closed parts, highest seed among them)."""
    files = parts(runs, "games")
    if not files:
        return 0, None
    seeds = [s for f in files for s in pq.read_table(f, columns=["game_seed", "game_id"]).to_pandas().drop_duplicates("game_id").game_seed]
    return len(seeds), max(seeds)


def start_lab(cfg: dict, runs: Path) -> subprocess.Popen:
    """An endless run starting after the highest seed already saved, so no deal repeats."""
    _, top = games_saved(runs)
    first = cfg["seed"] if top is None else top + 1
    config = yaml.safe_load((CONTROL / cfg["config"]).read_text())
    config["seeds"] = {"start": first}  # no count: endless
    path = CONTROL / "running.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    log(f"starting self-play from seed {first}")
    cmd = [*cfg["python"], "-m", "lab", "-c", str(path), "--record-decisions",
           "--rotate-every", str(cfg["rotate"]), "-o", str(runs)]  # fmt: skip
    return subprocess.Popen(cmd, cwd=cfg["workdir"], stdout=open(CONTROL / "lab.log", "a"), stderr=subprocess.STDOUT,
                            start_new_session=True)  # fmt: skip


def stop_lab(lab: subprocess.Popen) -> None:
    """Like Ctrl+C: the lab finishes in-flight games and closes its files."""
    if lab.poll() is not None:
        return
    os.killpg(lab.pid, signal.SIGINT)
    try:
        lab.wait(STOP_GRACE)
    except subprocess.TimeoutExpired:
        log("in-flight games did not finish in time: killing them")
        os.killpg(lab.pid, signal.SIGKILL)
        lab.wait()


def upload(cfg: dict, runs: Path, state: str, started: datetime, extra: dict | None = None) -> None:
    games, top = games_saved(runs)
    hours = (datetime.now(timezone.utc) - started).total_seconds() / 3600
    status = dict(run=cfg["run"], state=state, games=games, highest_seed=top, games_per_hour=round(games / hours) if hours > 0.05 else None,
                  deadline=deadline().isoformat(), updated=datetime.now(timezone.utc).isoformat(), **(extra or {}))  # fmt: skip
    (runs / "status.json").write_text(json.dumps(status, indent=2))
    out = subprocess.run(cfg["upload"], shell=True, cwd=cfg["workdir"], capture_output=True, text=True)
    if out.returncode:
        log(f"upload failed ({out.returncode}): {out.stderr[-500:]}")


def destroy(cfg: dict) -> bool:
    if "dry_run_file" in cfg["destroy"]:  # rehearsal: record instead of deleting
        Path(cfg["destroy"]["dry_run_file"]).write_text(datetime.now(timezone.utc).isoformat())
        return True
    req = urllib.request.Request(f"https://api.vultr.com/v2/bare-metals/{cfg['destroy']['server_id']}", method="DELETE",
                                 headers={"Authorization": f"Bearer {os.environ['VULTR_SELF_DESTRUCT_KEY']}"})  # fmt: skip
    try:
        urllib.request.urlopen(req, timeout=60)
        return True
    except Exception as e:  # keep trying; the guard is the backup
        log(f"self-destroy failed: {e}")
        return False


def run() -> None:
    cfg = settings()
    runs = Path(cfg["workdir"]) / "runs"
    runs.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc)
    lab, crashes = start_lab(cfg, runs), []
    reason = None
    while reason is None:
        time.sleep(cfg.get("interval", 60))
        upload(cfg, runs, "running", started)
        if datetime.now(timezone.utc) >= deadline():
            reason = "deadline"
        elif (CONTROL / "stop").exists():
            reason = "stop requested"
        elif lab.poll() is not None:
            crashes = [t for t in crashes if time.time() - t < 600] + [time.time()]
            log(f"self-play exited unexpectedly (code {lab.returncode}); see control/lab.log")
            if len(crashes) >= 2:
                reason = "self-play keeps crashing"
            else:
                lab = start_lab(cfg, runs)
    log(f"wrapping up: {reason}")
    stop_lab(lab)
    upload(cfg, runs, "finished", started, {"reason": reason})
    log("final upload done; destroying the server")
    while not destroy(cfg):
        time.sleep(60)


def guard() -> None:
    """Independent of `run`: destroy the server if it is still up an hour past the deadline."""
    if datetime.now(timezone.utc) > deadline() + GUARD_SLACK:
        log("guard: an hour past the deadline and still running: destroying")
        destroy(settings())


if __name__ == "__main__":
    {"run": run, "guard": guard}[sys.argv[1]]()
