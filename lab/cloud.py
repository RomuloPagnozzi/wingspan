"""Generate self-play games on a rented Vultr server that runs on its own until a deadline.

    uv run python -m lab.cloud status                  # servers, cost so far, credit, storage
    uv run python -m lab.cloud deploy --hours 12       # dry run: what it would create and cost
    uv run python -m lab.cloud deploy --hours 12 --yes # create the server (and, once, storage + key)
    #   then add the server's IP to Vultr > Account > API > Access Control (printed by deploy)
    uv run python -m lab.cloud setup                   # install code + agent, check upload and self-destroy
    uv run python -m lab.cloud start                   # begin; from here the laptop can be off
    uv run python -m lab.cloud progress                # games, games/hour, deadline (read from storage)
    uv run python -m lab.cloud extend --hours 6        # move the deadline later
    uv run python -m lab.cloud stop                    # wrap up now: finish games, upload, self-destroy
    uv run python -m lab.cloud fetch                   # download the results
    uv run python -m lab.cloud destroy                 # emergency: delete the server right away
    uv run python -m lab.cloud cleanup [--storage]     # after fetching: delete the runner key (and storage)

The server runs lab/cloud_agent.py: one endless self-play run whose files rotate every few hundred
games, each finished part uploaded to object storage within a minute, and at the deadline a graceful
stop, a final upload and self-destruction with an API key restricted to managing servers. A guard
on the server destroys it an hour past the deadline if the agent has died. On Vultr a stopped
server keeps billing: only deletion stops it.

Local state, including the storage and runner keys, is in experiments/data/cloud/state.json (not in
git). The main API key is read from .env (VULTR=...) and never leaves the laptop.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.vultr.com/v2"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "experiments/data/cloud/state.json"
SSH_KEY = Path.home() / ".ssh/wingspan_cloud_ed25519"
PLAN, REGION, OS_UBUNTU_2404 = "vbm-24c-384gb-amd5", "fra", 2284
STORAGE_REGION, STORAGE_TIER = "ams", "Standard"  # nearest object storage to Frankfurt
REMOTE = "/root/wingspan"
UV, UVX = "/root/.local/bin/uv", "/root/.local/bin/uvx"
HOURS_PER_MONTH = 672  # Vultr's dashboard prices an hour at monthly / 672
WORKERS, ROTATE = 47, 200  # parallel games on 48 threads; games per uploaded part (~35 min)


# --- Vultr API and local state -----------------------------------------------------------


def api_key() -> str:
    if key := os.environ.get("VULTR"):
        return key
    for line in (ROOT / ".env").read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "VULTR":
            return value.strip().strip("'\"")
    sys.exit("no VULTR key in the environment or .env")


def api(method: str, path: str, body: dict | None = None, ok404: bool = False) -> dict:
    req = urllib.request.Request(
        API + path, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )  # fmt: skip
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return {}
        body = e.read().decode()[:300]
        hint = ("\nThe API key only accepts listed IP addresses: add this one under Vultr dashboard > Account > "
                "API > Access Control." if "Unauthorized IP" in body else "")  # fmt: skip
        sys.exit(f"Vultr API {method} {path}: HTTP {e.code} {body}{hint}")


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))
    STATE.chmod(0o600)  # it holds the storage and runner keys


def need(state: dict, key: str) -> dict:
    if key not in state:
        sys.exit(f"no {key} recorded in {STATE}: run `deploy` first")
    return state[key]


def price_per_hour(plan: str) -> float:
    plans = api("GET", "/plans-metal?per_page=500")["plans_metal"]
    return next(p["monthly_cost"] for p in plans if p["id"] == plan) / HOURS_PER_MONTH


# --- ssh and storage ---------------------------------------------------------------------


def ssh_args(ip: str) -> list[str]:
    return ["ssh", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15", f"root@{ip}"]


def ssh(server: dict, command: str, check: bool = True) -> str:
    out = subprocess.run(ssh_args(server["ip"]) + [command], capture_output=True, text=True)
    if check and out.returncode:
        sys.exit(f"ssh failed ({out.returncode}): {command[:200]}\n{out.stderr[-1000:]}")
    return out.stdout


def write_remote(server: dict, path: str, text: str) -> None:
    subprocess.run(ssh_args(server["ip"]) + [f"cat > {path}"], input=text, text=True, check=True)


def rsync(*args: str) -> None:
    subprocess.run(["rsync", "-az", "-e", f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=accept-new", *args], check=True)


def s3(storage: dict, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
    """The AWS command line (run through uvx, nothing installed) against the bucket."""
    env = os.environ | {"AWS_ACCESS_KEY_ID": storage["access_key"], "AWS_SECRET_ACCESS_KEY": storage["secret_key"]}
    cmd = ["uvx", "--from", "awscli", "aws", "s3", *args, "--endpoint-url", f"https://{storage['host']}"]
    return subprocess.run(cmd, env=env, capture_output=capture, text=True)


# --- one-time resources: the runner key and the storage ------------------------------------


def ensure_runner_key(state: dict) -> None:
    """An API user allowed only to manage servers: the key the server uses to destroy itself."""
    if "runner" in state:
        return
    user = next((u for u in api("GET", "/users")["users"] if u["name"] == "wingspan-runner"), None)
    if user is None:
        email = api("GET", "/account")["account"]["email"].replace("@", "+wingspan-runner@", 1)
        user = api("POST", "/users", {
            "name": "wingspan-runner", "email": email, "password": secrets.token_urlsafe(24) + "aA1!",
            "api_enabled": True, "acls": ["subscriptions"],
        })["user"]  # fmt: skip
    # A user's default key is only ever shown masked; a key created for it is shown in full, once
    key = api("POST", f"/users/{user['id']}/apikeys", {"name": "wingspan-self-destroy"})["api_key"]["api_key"]
    state["runner"] = {"user_id": user["id"], "key": key}
    save_state(state)
    print(f"created the restricted runner key (user {user['email']}, may manage servers only)")


def ensure_storage(state: dict) -> None:
    if "storage" in state:
        return
    cluster = next(c for c in api("GET", "/object-storage/clusters")["clusters"] if c["region"] == STORAGE_REGION)
    tier = next(t for t in api("GET", "/object-storage/tiers")["tiers"] if t["sales_name"] == STORAGE_TIER)
    obj = api("POST", "/object-storage", {"cluster_id": cluster["id"], "tier_id": tier["id"], "label": "wingspan"})["object_storage"]
    for _ in range(60):
        obj = api("GET", f"/object-storage/{obj['id']}")["object_storage"]
        if obj["status"] == "active":
            break
        time.sleep(10)
    else:
        sys.exit(f"object storage {obj['id']} not active after 10 minutes; check the dashboard")
    state["storage"] = {"id": obj["id"], "host": obj["s3_hostname"], "access_key": obj["s3_access_key"],
                        "secret_key": obj["s3_secret_key"], "bucket": f"wingspan-{secrets.token_hex(4)}"}  # fmt: skip
    save_state(state)
    print(f"created object storage {obj['id']} at {obj['s3_hostname']}")


# --- commands ----------------------------------------------------------------------------


def cmd_status(args) -> None:
    account = api("GET", "/account")["account"]
    print(f"credit: ${-account['balance']:.2f}" if account["balance"] < 0 else f"balance owed: ${account['balance']:.2f}")
    servers = api("GET", "/bare-metals")["bare_metals"]
    if not servers:
        print("no bare metal servers running")
    for s in servers:
        up = (datetime.now(timezone.utc) - datetime.fromisoformat(s["date_created"])).total_seconds() / 3600
        print(f"server {s['id']}  {s['label']}  {s['plan']}  {s['region']}  {s['status']}  {s['main_ip']}  "
              f"up {up:.1f} h  ~${up * price_per_hour(s['plan']):.2f} so far")  # fmt: skip
    for o in api("GET", "/object-storage")["object_storages"]:
        print(f"storage {o['id']}  {o['label']}  {o['s3_hostname']}  {o['status']}")
    state = load_state()
    if "run" in state:
        print(f"last run: {state['run']['name']}, deadline {state['run']['deadline']}")


def cmd_deploy(args) -> None:
    state = load_state()
    if api("GET", "/bare-metals")["bare_metals"] and not args.allow_existing:
        sys.exit("a bare metal server already exists; see `status` (or pass --allow-existing)")
    if args.plan not in api("GET", f"/regions/{args.region}/availability").get("available_plans", []):
        sys.exit(f"{args.plan} is not in stock in {args.region}")
    price = price_per_hour(args.plan)
    print(f"server: {args.plan} in {args.region}, ~${price:.3f}/h; destroys itself after {args.hours} h: "
          f"at most ~${price * args.hours:.2f} (+ up to 1 h if the guard has to step in)")  # fmt: skip
    if "storage" not in state:
        print(f"once: object storage ({STORAGE_TIER}, {STORAGE_REGION}), ~$18/month prorated, kept for later runs")
    if "runner" not in state:
        print("once: an API user allowed to manage servers only, whose key the server uses to destroy itself")
    if not args.yes:
        return print("dry run: nothing created. Add --yes to create (billing starts).")
    ensure_runner_key(state)
    ensure_storage(state)
    if not SSH_KEY.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "wingspan-cloud", "-f", str(SSH_KEY)], check=True)
    public = SSH_KEY.with_suffix(".pub").read_text().strip()
    key_id = next((k["id"] for k in api("GET", "/ssh-keys")["ssh_keys"] if k["ssh_key"].split()[:2] == public.split()[:2]), None)
    key_id = key_id or api("POST", "/ssh-keys", {"name": "wingspan-cloud", "ssh_key": public})["ssh_key"]["id"]
    server = api("POST", "/bare-metals", {
        "region": args.region, "plan": args.plan, "os_id": OS_UBUNTU_2404, "sshkey_id": [key_id],
        "label": "wingspan-selfplay", "hostname": "wingspan", "activation_email": False,
    })["bare_metal"]  # fmt: skip
    created = datetime.now(timezone.utc)
    state["server"] = {"id": server["id"], "ip": None, "plan": args.plan, "price_per_hour": price, "created": created.isoformat()}
    state["run"] = {"name": args.name, "deadline": (created + timedelta(hours=args.hours)).isoformat(),
                    "seed": args.seed if args.seed is not None else int(created.timestamp())}  # fmt: skip
    save_state(state)  # at once: whatever happens next, `destroy` can find it
    print(f"created {server['id']}; waiting for it to boot (bare metal takes several minutes)")
    for _ in range(90):
        s = api("GET", f"/bare-metals/{server['id']}")["bare_metal"]
        if s["status"] == "active" and s["main_ip"] not in ("", "0.0.0.0"):
            state["server"]["ip"] = s["main_ip"]
            save_state(state)
            break
        time.sleep(20)
    else:
        sys.exit("not active after 30 minutes: check `status`; `destroy` deletes it")
    print(f"\nactive at {state['server']['ip']}. Now add {state['server']['ip']}/32 to Vultr > Account > API > "
          f"Access Control (so it can destroy itself), then run `setup`.")  # fmt: skip


UNITS = {
    "wingspan-agent.service": """[Unit]
Description=Wingspan self-play session (lab/cloud_agent.py)
After=network-online.target
[Service]
WorkingDirectory={remote}
EnvironmentFile={remote}/control/secrets.env
Environment=WINGSPAN_CONTROL={remote}/control
ExecStart={uv} run --no-sync python -m lab.cloud_agent run
Restart=on-failure
RestartSec=30
StandardOutput=append:{remote}/control/agent.log
StandardError=inherit
""",
    "wingspan-guard.service": """[Unit]
Description=Wingspan guard: destroy the server an hour past its deadline
[Service]
Type=oneshot
WorkingDirectory={remote}
EnvironmentFile={remote}/control/secrets.env
Environment=WINGSPAN_CONTROL={remote}/control
ExecStart={uv} run --no-sync python -m lab.cloud_agent guard
StandardOutput=append:{remote}/control/agent.log
""",
    "wingspan-guard.timer": """[Unit]
Description=Run the Wingspan guard every 10 minutes
[Timer]
OnBootSec=10min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
""",
}


def agent_settings(state: dict) -> dict:
    """lab/cloud_agent.py's agent.json for this run."""
    server, storage, run = state["server"], state["storage"], state["run"]
    return {
        "run": run["name"], "workdir": REMOTE, "config": "selfplay.yaml", "rotate": ROTATE, "seed": run["seed"],
        "python": [UV, "run", "--no-sync", "python"], "destroy": {"server_id": server["id"]},
        "upload": f"{UVX} --from awscli aws s3 sync runs s3://{storage['bucket']}/{run['name']} --exclude '*.tmp' "
                  f"--only-show-errors --endpoint-url https://{storage['host']}",
    }  # fmt: skip


def cmd_setup(args) -> None:
    state = load_state()
    server, storage, runner, run = need(state, "server"), need(state, "storage"), need(state, "runner"), need(state, "run")
    ssh(server, "command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh) >/dev/null")
    rsync("--delete", "--exclude=.git", "--exclude=.venv", "--exclude=.env", "--exclude=experiments/", "--exclude=__pycache__",
          "--exclude=lab/explainer/", "--exclude=control/", "--exclude=runs/", f"{ROOT}/", f"root@{server['ip']}:{REMOTE}/")  # fmt: skip
    ssh(server, f"cd {REMOTE} && {UV} sync --frozen -q --no-default-groups --group lab && {UV} run --no-sync python -c 'import lab.cloud_agent'")
    # control files; secrets only in secrets.env (0600)
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()
    run["code"] = git("rev-parse", "HEAD") + (" + uncommitted changes" if git("status", "--porcelain") else "")
    config = (ROOT / args.config).read_text().replace("num_workers: 7", f"num_workers: {WORKERS}")
    config += f"code_version: {json.dumps(run['code'])}  # the server has no git; written by lab.cloud setup\n"
    env = (f"AWS_ACCESS_KEY_ID={storage['access_key']}\nAWS_SECRET_ACCESS_KEY={storage['secret_key']}\n"
           f"VULTR_SELF_DESTRUCT_KEY={runner['key']}\n")  # fmt: skip
    ssh(server, f"mkdir -p {REMOTE}/control && chmod 700 {REMOTE}/control")
    files = {"agent.json": json.dumps(agent_settings(state), indent=2), "selfplay.yaml": config,
             "deadline": run["deadline"], "secrets.env": env}  # fmt: skip
    for name, text in files.items():
        write_remote(server, f"{REMOTE}/control/{name}", text)
    ssh(server, f"chmod 600 {REMOTE}/control/secrets.env")
    for name, text in UNITS.items():
        write_remote(server, f"/etc/systemd/system/{name}", text.format(remote=REMOTE, uv=UV))
    ssh(server, "systemctl daemon-reload")
    save_state(state)
    print(f"code ({run['code']}) and agent installed. Checking, from the server, the two things it must be able to do:")
    check(server, storage)


def check(server: dict, storage: dict) -> None:
    """From the server itself: upload to the bucket, and use the self-destruct key (on a server id
    that does not exist: a 404 proves the key and the IP are accepted without deleting anything)."""
    aws = f"set -a; . {REMOTE}/control/secrets.env; {UVX} --from awscli aws --endpoint-url https://{storage['host']} s3"
    out = ssh(server, f"{aws} mb s3://{storage['bucket']} 2>&1 | grep -v BucketAlready; echo ok > /tmp/probe && "
                      f"{aws} cp /tmp/probe s3://{storage['bucket']}/probe --only-show-errors && "
                      f"{aws} rm s3://{storage['bucket']}/probe --only-show-errors && echo UPLOAD_OK", check=False)  # fmt: skip
    upload_ok = "UPLOAD_OK" in out
    code = ssh(server, f"set -a; . {REMOTE}/control/secrets.env; curl -s -o /dev/null -w '%{{http_code}}' -X DELETE "
                       "-H \"Authorization: Bearer $VULTR_SELF_DESTRUCT_KEY\" "
                       f"{API}/bare-metals/00000000-0000-0000-0000-000000000000", check=False).strip()  # fmt: skip
    print(f"  upload to storage:  {'OK' if upload_ok else 'FAILED: ' + out[-300:]}")
    print({"404": "  self-destroy key:   OK (accepted from the server)",
           "401": f"  self-destroy key:   REJECTED: add {server['ip']}/32 to Vultr > Account > API > Access Control, then rerun `setup`",
           "403": "  self-destroy key:   REJECTED: the runner user lacks the right to manage servers"}.get(code, f"  self-destroy key:   unexpected HTTP {code}"))  # fmt: skip
    if upload_ok and code == "404":
        print("ready: `start` begins the run; after that the laptop can be off.")
    else:
        print("NOT ready: do not `start` until both checks pass (the server could not save results or stop itself).")


def cmd_start(args) -> None:
    state = load_state()
    ssh(need(state, "server"), "systemctl enable --now wingspan-guard.timer && systemctl start wingspan-agent")
    state["run"]["started"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print(f"started; deadline {state['run']['deadline']}. Watch with `progress` (games are counted as each "
          f"{ROTATE}-game part is uploaded, the first after ~35 min).")  # fmt: skip


def cmd_progress(args) -> None:
    state = load_state()
    storage, run = need(state, "storage"), need(state, "run")
    out = s3(storage, "cp", f"s3://{storage['bucket']}/{run['name']}/status.json", "-", capture=True)
    if out.returncode:
        print("no status uploaded yet (it appears a minute after `start`)")
    else:
        s = json.loads(out.stdout)
        print(f"{s['run']}: {s['state']}{' (' + s['reason'] + ')' if s.get('reason') else ''}, {s['games']} games saved, "
              f"{s['games_per_hour']} games/h, deadline {s['deadline']}, updated {s['updated']}")  # fmt: skip
    server = state.get("server")
    if server and api("GET", f"/bare-metals/{server['id']}", ok404=True):
        up = (datetime.now(timezone.utc) - datetime.fromisoformat(server["created"])).total_seconds() / 3600
        print(f"server up {up:.1f} h, ~${up * server['price_per_hour']:.2f} so far")
    else:
        print("server: gone (destroyed)")


def cmd_extend(args) -> None:
    state = load_state()
    server, run = need(state, "server"), need(state, "run")
    new = datetime.fromisoformat(run["deadline"]) + timedelta(hours=args.hours)
    write_remote(server, f"{REMOTE}/control/deadline", new.isoformat())
    run["deadline"] = new.isoformat()
    save_state(state)
    print(f"deadline moved to {new:%Y-%m-%d %H:%M} UTC (~${args.hours * server['price_per_hour']:.2f} more at most)")


def cmd_stop(args) -> None:
    ssh(need(load_state(), "server"), f"touch {REMOTE}/control/stop")
    print("asked to wrap up: within a minute it stops, finishes in-flight games (up to ~10 min), uploads, self-destroys")


def cmd_fetch(args) -> None:
    state = load_state()
    storage, run = need(state, "storage"), need(state, "run")
    dest = STATE.parent / run["name"]
    s3(storage, "sync", f"s3://{storage['bucket']}/{run['name']}", str(dest), "--only-show-errors")
    print(f"results in {dest}; build a dataset with:\n"
          f"  uv run python -m lab.dataset {dest.relative_to(ROOT)}/*/ --out experiments/data/datasets/{run['name']}")  # fmt: skip


def cmd_destroy(args) -> None:
    server = need(load_state(), "server")
    api("DELETE", f"/bare-metals/{server['id']}", ok404=True)
    print(f"deleted server {server['id']} (results already uploaded stay in storage; `fetch` them)")


def cmd_cleanup(args) -> None:
    state = load_state()
    if api("GET", "/bare-metals")["bare_metals"]:
        sys.exit("a server is still running: `stop` or `destroy` it first")
    if "runner" in state:
        api("DELETE", f"/users/{state.pop('runner')['user_id']}", ok404=True)
        print("deleted the restricted runner key")
    if args.storage and "storage" in state:
        api("DELETE", f"/object-storage/{state.pop('storage')['id']}", ok404=True)
        print("deleted the object storage and everything in it")
    save_state(state)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    d = sub.add_parser("deploy")
    d.add_argument("--hours", type=float, required=True, help="the server destroys itself this long after creation")
    d.add_argument("--name", default=f"selfplay-{datetime.now():%Y%m%d}", help="run name: folder in storage and locally")
    d.add_argument("--seed", type=int, default=None, help="first game seed (default: from the clock, so runs never overlap)")
    d.add_argument("--plan", default=PLAN)
    d.add_argument("--region", default=REGION)
    d.add_argument("--yes", action="store_true", help="really create it; otherwise a dry run")
    d.add_argument("--allow-existing", action="store_true")
    s = sub.add_parser("setup")
    s.add_argument("--config", default="experiments/selfplay.yaml")
    for name in ("start", "progress", "stop", "fetch", "destroy"):
        sub.add_parser(name)
    e = sub.add_parser("extend")
    e.add_argument("--hours", type=float, required=True)
    c = sub.add_parser("cleanup")
    c.add_argument("--storage", action="store_true", help="also delete the object storage and its contents")
    args = p.parse_args()
    globals()[f"cmd_{args.command}"](args)


if __name__ == "__main__":
    main()
