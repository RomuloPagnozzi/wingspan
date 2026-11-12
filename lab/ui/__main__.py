"""The lab UI: the self-play loop's progress, matches, nets and job queue in the browser. A prototype: far from
what we want, expect rough edges.

    uv run python -m lab.ui          # http://127.0.0.1:8770

It listens on this machine only: its queue runs commands. The pages are plain files in static/.
"""

import os
import signal
import subprocess
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from lab import ledger
from lab.ui import data, jobs

app = FastAPI()


@app.get("/api/overview")
def overview() -> dict:
    listed = {name: {k: a[k] for k in ("step", "label", "commands")} | {"confirm": a.get("confirm", False)}
              for name, a in jobs.actions().items()}  # fmt: skip
    pipelines = {name: p | {"commands": [c for a in p["actions"] for c in listed[a]["commands"]],
                            "confirm": any(listed[a]["confirm"] for a in p["actions"])}
                 for name, p in jobs.PIPELINES.items()}  # fmt: skip
    return ledger.plain(data.overview()) | {"jobs": jobs.load()[-30:], "actions": listed, "pipelines": pipelines}


@app.get("/api/log/{name}", response_class=PlainTextResponse)
def log(name: str, lines: int = 200) -> str:
    """The end of a log, with tqdm's progress bars (rewritten in place with \\r) reduced to their last state."""
    path = ledger.DATA / "logs" / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - 200_000))
        text = f.read().decode(errors="replace")
    return "\n".join(line.split("\r")[-1] for line in text.split("\n")[-lines:])


@app.post("/api/jobs/{action}")
def enqueue(action: str) -> list[dict]:
    if action not in jobs.actions() and action not in jobs.PIPELINES:
        raise HTTPException(404)
    return jobs.enqueue(action)


@app.post("/api/stop/laptop/{pid}")
def stop_process(pid: int) -> None:
    """Ctrl+C for a lab command on this machine (in-flight games finish, files close; again: quits at once). Only
    pids of lab commands: this is no way to signal anything else."""
    job = next((j for j in data.compute()[0]["jobs"] if j["pid"] == pid), None)
    if job is None:
        raise HTTPException(404, "not a running lab command")
    if job["queue_job"]:  # through its job, so a pipeline doesn't go on to its next step
        jobs.stop(job["queue_job"])
    else:
        os.kill(pid, signal.SIGINT)


@app.post("/api/stop/home-server")
def stop_home_server() -> str:
    """The home server's self-play container: no restart, then Ctrl+C. Only what the checklist does."""
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "homelab", data.HOME_STOP], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise HTTPException(502, out.stderr.strip() or "ssh failed")
    return out.stdout


@app.post("/api/jobs/{job_id}/stop")
def stop(job_id: str) -> None:
    jobs.stop(job_id)


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))

if __name__ == "__main__":
    threading.Thread(target=jobs.loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8770, log_level="warning")
