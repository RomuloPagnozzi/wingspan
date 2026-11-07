"""Screenshots of the web UI at the explainer's decisions, from the viewer's seat.

Writes the recorded game into a throwaway games database, runs the real server on it in
--debug mode (read-only; you sit in the human seat; `<id>@<move>` opens the game at that
move) and captures each decision with headless Chrome. build.py embeds the results.

    uv run python lab/explainer/screenshots.py
"""

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pandas as pd
from PIL import Image

from wingspan.ai.bots import BOTS, CHAMPION
from wingspan.engine.actions import get_actions
from wingspan.engine.core import initiate_state
from wingspan.engine.engine import transition_state
from wingspan.web.session import Session, bot_seat, human_seat
from wingspan.web.store import Store, now

HERE = Path(__file__).parent
DATA = Path("experiments/tuning/mcts_joint_v2")
GAME_ROW, WANT, VIEWER = 200000, (115, 116, 117, 118), 1  # same game and decisions as build.py
PORT = 8799
CHROME = os.environ.get(
    "CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
SIZE = (1440, 1010)  # tall enough for the hand under the prompt bar


def full_history(gd: pd.DataFrame) -> tuple[list[str], dict[int, int]]:
    """Every applied action (forced ones included, as the web app records them), and how
    many had been applied when each wanted decision came up."""
    state = initiate_state(2, seed=int(gd.game_seed.iloc[0]))
    recorded = iter(gd.itertuples())
    history, cuts = [], {}
    while actions := get_actions(state):
        if len(actions) == 1:
            action = actions[0]
        else:
            row = next(recorded)
            if row.decision_idx in WANT:
                assert state.current_player_index == VIEWER, row.decision_idx
                cuts[row.decision_idx] = len(history)
            action = {str(a): a for a in actions}[row.action_taken]
        history.append(str(action))
        state = transition_state(state, action)
    return history, cuts


def write_game(db: Path, gid: str, history: list[str], seed: int):
    # Seat 0 is the bot, seat 1 the human: the viewer is player 2, as in the explainer
    seats = [bot_seat(BOTS[CHAMPION]), human_seat("you@localhost", "You")]
    session = Session(seats, seed=seed, history=history)  # fails here if the replay diverges
    summary = {"id": gid, "created": now(), "updated": now(), "status": "finished",
               "round": 4, "scoring": "green", "seats": seats, "result": session.results()}  # fmt: skip
    doc = {"created": now(), "config": session.config, "actions": history}
    Store(str(db)).save(gid, doc, summary)


def serve(db: Path) -> subprocess.Popen:
    server = subprocess.Popen(
        [sys.executable, "-m", "wingspan.web.server", "--db", str(db), "--debug",
         "--no-browser", "--workers", "1", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz")
            return server
        except OSError:
            time.sleep(0.5)
    server.kill()
    raise RuntimeError("the web server did not start")


def capture(url: str, out: Path, profile: Path):
    png = out.with_suffix(".png")
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--user-data-dir={profile}", f"--window-size={SIZE[0]},{SIZE[1]}",
         "--virtual-time-budget=8000", f"--screenshot={png}", url],
        check=True, capture_output=True, timeout=120,
    )  # fmt: skip
    Image.open(png).save(out, "WEBP", quality=82)
    png.unlink()


def main():
    d = pd.read_parquet(DATA / "decisions.parquet")
    gid = d.game_id.iloc[GAME_ROW]
    gd = d[d.game_id == gid].sort_values("decision_idx")
    history, cuts = full_history(gd)

    out_dir = HERE / "shots"
    out_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "games.db"
        write_game(db, "explainer", history, int(gd.game_seed.iloc[0]))
        server = serve(db)
        try:
            for idx in WANT:
                url = f"http://127.0.0.1:{PORT}/game.html?g=explainer@{cuts[idx]}"
                capture(url, out_dir / f"decision-{idx}.webp", Path(tmp) / "chrome")
                print(f"#{idx} (move {cuts[idx]}) -> shots/decision-{idx}.webp")
        finally:
            server.terminate()


if __name__ == "__main__":
    main()
