"""The lab UI's job queue: the commands of docs/SELFPLAY_LOOP.md, run one at a time (each uses every core).

A job is a list of shell commands and a log (experiments/data/logs/). It runs in a process of its own
(`python -m lab.ui.jobs <id>`, detached: it outlives the server), kept awake by caffeinate. Stopping one
is Ctrl+C: SIGINT to its process group, so a `lab` run finishes its in-flight games and closes its files.
A job enqueued `after` another runs only if that one succeeded: that is how a pipeline advances by itself.

The browser only names an action; the commands come from ACTIONS here. An action with `confirm` deletes
or overwrites something: the UI shows its commands and asks first.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from lab import ledger

REPO = Path(__file__).parents[2]
JOBS = ledger.DATA / "jobs"  # jobs.json (the queue) and <id>.exit (written by a job when it ends)
D = "experiments/data"
lock = threading.Lock()


def folders(g: int) -> list[str]:
    """The self-play folders of generation g: the laptop's and the home server's copy."""
    base = f"{D}/selfplay_g{g}" if g else f"{D}/selfplay"
    return [base, base + "_homelab"]


def actions() -> dict[str, dict]:
    """Every action for the current generation N: `step` is its step of docs/SELFPLAY_LOOP.md."""
    n = ledger.generation()
    candidate = Path(REPO / D / "models/policy_candidate.bin")
    net = ledger.net_id(candidate) if candidate.exists() else "none"
    selfplay = "uv run python -m lab -c experiments/selfplay.yaml --record-decisions --rotate-every 50 -o "
    sources = " ".join(f"{f}/*" for g in (n, n - 1) if g >= 0 for f in folders(g) if (REPO / f).exists())
    archive = f'"/Volumes/External Drive/wingspan/generation_{n - 1}"'

    def match(name: str) -> list[str]:  # a rerun replaces the folder's previous runs (the ledger keeps their results)
        return [f"rm -rf {D}/{name}", f"uv run python -m lab -c experiments/{name}.yaml --record-decisions -o {D}/{name}"]

    listed = {
        "prior_vs_search": {"step": 2, "label": f"Search vs prior on generation {n}",
                            "commands": [f"uv run python -m lab.prior_vs_search {folders(n)[0]} --games 300"]},
        "archive": {"step": 3, "label": f"Archive the nets and their matches to generation_{n - 1}/ on the drive", "confirm": True,
                    "commands": [f"mkdir -p {archive}/matches", f"cp -R {D}/models {archive}/",
                                 f"cp -R {D}/policy_match {D}/puct_match {D}/puct_value_match {archive}/matches/"]},
        "window": {"step": 3, "label": "Build the training window (40k games, newest first)", "confirm": True,
                   "commands": [f"rm -rf {D}/datasets/selfplay",
                                f"uv run python -m lab.dataset {sources} --max-games 40000 --out {D}/datasets/selfplay"]},
        "train_policy": {"step": 4, "label": "Train the candidate policy",
                         "commands": [f"uv run --group train python -m lab.train_policy {D}/datasets/selfplay --out {D}/models/policy_candidate.pt"]},
        "train_value": {"step": 4, "label": "Train the value net (replaces value.bin)", "confirm": True,
                        "commands": [f"uv run --group train python -m lab.train_value {D}/datasets/selfplay"]},
        "sanity": {"step": 6, "label": "Policy alone: candidate vs champion", "confirm": True, "commands": match("candidate_policy_match")},
        "decision": {"step": 6, "label": "PUCT: candidate vs champion (the decision)", "confirm": True, "commands": match("candidate_puct_match")},
        "promote": {"step": 6, "label": "Promote the candidate", "confirm": True,
                    "commands": [f"mv {D}/models/policy_candidate.pt {D}/models/policy.pt", f"mv {D}/models/policy_candidate.bin {D}/models/policy.bin",
                                 f"uv run python -m lab.ledger verdict result=promoted net={net}"]},
        "reject": {"step": 6, "label": "Reject the candidate",
                   "commands": [f"uv run python -m lab.ledger verdict result=rejected net={net}"]},
        "anchor_policy": {"step": 6, "label": "Anchor: policy alone vs the tree at 2000", "confirm": True, "commands": match("policy_match")},
        "anchor_puct": {"step": 6, "label": "Anchor: PUCT vs the tree at 2000", "confirm": True, "commands": match("puct_match")},
        "leaf": {"step": 6, "label": "Value net at the leaves", "confirm": True, "commands": match("puct_value_match")},
        "selfplay": {"step": 7, "label": f"Self-play, generation {n} (until stopped)", "commands": [selfplay + folders(n)[0]]},
        "selfplay_next": {"step": 7, "label": f"Start generation {n + 1} self-play (until stopped)", "confirm": True,
                          "commands": [selfplay + folders(n + 1)[0]]},
        "backup": {"step": 8, "label": "Back up experiments/data to the drive", "confirm": True,
                   "commands": [f'rsync -a --delete --exclude datasets --exclude .DS_Store {D}/ "/Volumes/External Drive/wingspan/data/"']},
    }  # fmt: skip
    return {name: a for name, a in listed.items() if candidate.exists() or name not in ("promote", "reject")}


# Actions enqueued together, each after the one before
PIPELINES = {
    "candidate": {"label": "Train the candidate, then both matches against the champion", "actions": ["train_policy", "sanity", "decision"]},
    "anchors": {"label": "Both anchors, then the leaf match", "actions": ["anchor_policy", "anchor_puct", "leaf"]},
}  # fmt: skip


def load() -> list[dict]:
    path = JOBS / "jobs.json"
    return json.loads(path.read_text()) if path.exists() else []


def save(jobs: list[dict]) -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    (JOBS / "jobs.tmp").write_text(json.dumps(jobs, indent=1))
    (JOBS / "jobs.tmp").rename(JOBS / "jobs.json")


def enqueue(name: str) -> list[dict]:
    """Add an action, or a pipeline's actions chained, to the queue."""
    available = actions()
    names = PIPELINES[name]["actions"] if name in PIPELINES else [name]
    with lock:
        jobs, added, after = load(), [], None
        for i, a in enumerate(names):
            job_id = f"{datetime.now():%Y%m%d-%H%M%S}-{i}"
            added.append({"id": job_id, "action": a, "label": available[a]["label"], "commands": available[a]["commands"],
                          "status": "queued", "after": after, "created": _now(), "log": f"{job_id}_{a}.log"})  # fmt: skip
            after = job_id
        save(jobs + added)
    return added


def stop(job_id: str) -> None:
    """Ctrl+C for a running job; a queued one is just dropped."""
    with lock:
        jobs = load()
        for job in jobs:
            if job["id"] == job_id and job["status"] == "running":
                os.killpg(job["pid"], signal.SIGINT)
            elif job["id"] == job_id and job["status"] == "queued":
                job["status"] = "cancelled"
        save(jobs)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def tick() -> None:
    """Close the running job if it ended; if nothing runs, start the next one whose turn it is."""
    with lock:
        jobs = load()
        before = json.dumps(jobs)
        status = {j["id"]: j["status"] for j in jobs}
        for job in jobs:
            exit_file = JOBS / f"{job['id']}.exit"
            if job["status"] == "running" and (exit_file.exists() or not _alive(job["pid"])):
                result = exit_file.read_text().strip() if exit_file.exists() else "lost"
                job |= {"status": {"0": "done", "stopped": "stopped"}.get(result, "failed"), "exit": result, "ended": _now()}
            elif job["status"] == "queued" and status.get(job["after"], "done") not in ("done", "queued", "running"):
                job["status"] = "skipped"  # the job before it failed or was stopped
            status[job["id"]] = job["status"]
        if "running" not in status.values():
            ready = next((j for j in jobs if j["status"] == "queued" and status.get(j["after"], "done") == "done"), None)
            if ready:
                runner = subprocess.Popen([sys.executable, "-m", "lab.ui.jobs", ready["id"]], cwd=REPO, start_new_session=True)
                ready |= {"status": "running", "pid": runner.pid, "started": _now()}
        if json.dumps(jobs) != before:
            save(jobs)


def loop() -> None:
    while True:
        tick()
        time.sleep(2)


def run(job_id: str) -> None:
    """The job's own process: its commands in turn, output to its log, the result to <id>.exit. It ignores
    Ctrl+C itself (its commands get it and shut down in their own way) and runs nothing more after one."""
    job = next(j for j in load() if j["id"] == job_id)
    stopped = []
    signal.signal(signal.SIGINT, lambda *_: stopped.append(True))
    awake = subprocess.Popen(["caffeinate", "-dis", "-w", str(os.getpid())], start_new_session=True)
    code = 0
    with open(ledger.DATA / "logs" / job["log"], "a") as log:
        for command in job["commands"]:
            log.write(f"$ {command}\n")
            log.flush()
            code = subprocess.call(command, shell=True, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            if code or stopped:
                break
    (JOBS / f"{job_id}.exit").write_text("stopped" if stopped else str(code))
    awake.terminate()


if __name__ == "__main__":
    run(sys.argv[1])
