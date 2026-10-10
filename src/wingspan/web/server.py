"""Web server for playing Wingspan in the browser against AI opponents.

    uv run wingspan                                 # local: SQLite in ./games.db, opens the menu
    uv run wingspan --sims 50                       # a weaker, faster champion for testing
    uv run wingspan --db copy.db --debug            # inspect a copy of the live database (make debug)

Players are identified by email: from Cloudflare Access in production (--auth cloudflare, which
reads CF_ACCESS_TEAM_DOMAIN / CF_ACCESS_AUD), a fixed --user locally. Each game is a document in
the store, saved after every move and replayed on demand (see store.py). The browser drives the
game: it posts the index of a legal action for its seat, and calls /step to advance AI moves one at
a time. AI moves run in a process pool, first come first served, so games take turns on the CPU.
"""

import argparse
import asyncio
import io
import json
import os
import secrets
import time
import webbrowser
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import uvicorn
from PIL import Image, ImageOps
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from wingspan.ai.bots import BOTS, CHAMPION
from wingspan.engine.core import init_registries

from .auth import CloudflareAccess, DevUser
from .leaderboard import is_abandoned, leaderboard
from .session import Session, bot_seat, catalog, human_seat
from .store import Store, now

STATIC = Path(__file__).parent / "static"
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".svg")
APP_VERSION = os.environ.get("APP_VERSION", "dev")
MAX_LIVE_GAMES = 200  # in memory; the rest are replayed from the store when opened


def images(folder: str) -> list[str]:
    """Static image paths in a folder (the bots' pictures)."""
    d = STATIC / folder
    return (
        sorted(
            f"{folder}/{p.name}" for p in d.iterdir() if p.suffix.lower() in IMAGE_TYPES
        )
        if d.is_dir()
        else []
    )


def bot_avatar(bot_id: str) -> str | None:
    """A bot's picture is static/bots/<bot id>.<png|jpg|...>, if there is one."""
    return next((p for p in images("bots") if Path(p).stem == bot_id), None)


def avatar_image(data: bytes) -> bytes:
    """A player's upload, re-encoded by us: centered square, 256px WebP. Anything that isn't an image
    fails to decode, and nothing from the original file (metadata, GPS) survives."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, (256, 256), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=85)
    return out.getvalue()


def choose_action(strategy, state, actions):
    """Runs in a worker process. Returns the strategy so its RNG state carries over."""
    return strategy.select_action(state, actions), strategy


@dataclass
class Game:
    session: Session
    created: str = field(default_factory=now)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)


class NewGame(BaseModel):
    opponents: int = Field(1, ge=1, le=4)
    scoring: Literal["green", "blue"] = "green"


class Act(BaseModel):
    index: int
    version: int  # the state version the client chose from


class Report(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    game: str | None = Field(None, max_length=40)  # the game it happened in, if any
    version: int | None = (
        None  # the move number when reported: `make debug ID=<game> AT=<version>` reopens it there
    )
    context: dict = Field(
        default_factory=dict
    )  # what the client showed (phase, prompt, board viewed, ...)


class Name(BaseModel):
    # Names are rendered as HTML by the client: letters (any language), digits, space, dot, dash only
    name: str = Field(min_length=1, max_length=20, pattern=r"^[\w .-]+$")


def create_app(args) -> FastAPI:
    bot = {**BOTS[args.bot]}
    if args.sims is not None and bot["strategy"] == "mcts":
        bot["params"] = {
            **bot["params"],
            "simulations": args.sims,
        }  # recorded as played
    store = Store(args.db, readonly=args.debug)
    if args.auth == "cloudflare":
        identify = CloudflareAccess(
            os.environ["CF_ACCESS_TEAM_DOMAIN"], os.environ["CF_ACCESS_AUD"]
        )
    else:
        identify = DevUser(args.user)
    games: dict[str, Game] = {}
    cards = json.dumps(catalog()).encode()

    @asynccontextmanager
    async def lifespan(app):
        with ProcessPoolExecutor(args.workers, initializer=init_registries) as pool:
            app.state.pool = pool
            if args.open_browser:
                webbrowser.open(f"http://127.0.0.1:{args.port}/")
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def middleware(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            request.state.uid = await asyncio.to_thread(identify, request)
            if not request.state.uid:
                return JSONResponse({"detail": "not signed in"}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault(
            "Cache-Control", "no-cache"
        )  # pick up new static files right away
        # No keep-alive: a proxy in between (e.g. Docker Desktop) can hide the server closing an idle
        # connection, and the browser's next POST then dies on it (browsers only retry GETs).
        response.headers["Connection"] = "close"
        return response

    # -------------------------------------------------------------------------
    # Games: in memory while played, persisted after every move

    async def get(gid: str) -> Game:
        # In --debug, "<id>@<move>" opens a game as it was at that move (e.g. where a bug was reported)
        base, _, at = gid.partition("@") if args.debug else (gid, "", "")
        if gid not in games and (doc := await asyncio.to_thread(store.load, base)):
            try:
                session = Session(
                    **doc["config"],
                    history=doc["actions"][: int(at)] if at else doc["actions"],
                )
            except (
                KeyError,
                ValueError,
            ):  # played under different rules (can't be replayed), or a bad @move
                session = None
            if session and gid not in games:
                games[gid] = Game(session, created=doc["created"])
        if gid not in games:
            raise HTTPException(404, "game not found")
        game = games[gid]
        game.touched = time.monotonic()
        return game

    def summary(gid: str, game: Game) -> dict:
        s = game.session
        return {
            "id": gid,
            "created": game.created,
            "updated": now(),
            "status": "finished" if s.game_over else "in_progress",
            "round": s.state.round,
            "scoring": s.config["scoring"],
            "seats": [
                {k: v for k, v in seat.items() if k in ("kind", "uid", "name", "bot")}
                for seat in s.seats
            ],
            "result": s.results(),
        }

    async def save(gid: str):
        game = games[gid]
        s = game.session
        names = [p["name"] for p in s.view(None)["players"]]
        doc = {
            "app_version": APP_VERSION,
            "created": game.created,
            "config": s.config,
            "actions": s.history,
            # For reading in a database browser; not needed to resume
            "log": [
                (
                    f"{names[e['p']]}: {e['text']}"
                    if "text" in e
                    else f"--- round {e['round']} ---"
                )
                for e in s.log
            ],
        }
        await asyncio.to_thread(store.save, gid, doc, summary(gid, game))

    def seat(request: Request, game: Game) -> int | None:
        """The requester's seat, or None for a spectator. In --debug you sit in the owner's seat."""
        if args.debug:
            return next(
                i for i, x in enumerate(game.session.seats) if x["kind"] == "human"
            )
        return game.session.seat_of(request.state.uid)

    def avatar_url(avatar_id: str | None) -> str | None:
        return f"/api/avatar/{avatar_id}" if avatar_id else None

    def look(seat: dict, profiles: dict) -> dict:
        """How a seat appears now: seats keep the name from game creation, players and bots get renamed."""
        if seat["kind"] == "human":
            profile = profiles.get(seat["uid"], {})
            return {
                "name": profile.get("name") or seat["name"],
                "avatar": avatar_url(profile.get("avatar")),
            }
        return {
            "name": BOTS.get(seat["bot"], seat)["name"],
            "avatar": bot_avatar(seat["bot"]),
        }

    def view(request: Request, gid: str) -> dict:
        game = games[gid]
        profiles = store.profiles()
        looks = [look(s, profiles) for s in game.session.seats]
        return {"id": gid, **game.session.view(seat(request, game), looks)}

    def evict():
        while len(games) >= MAX_LIVE_GAMES:
            del games[min(games, key=lambda g: games[g].touched)]

    # -------------------------------------------------------------------------
    # API

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "live_games": len(games), "version": APP_VERSION}

    @app.get("/api/cards")
    def get_cards():
        return Response(cards, media_type="application/json")

    @app.get("/api/me")
    def me(request: Request):
        uid = request.state.uid
        profile = store.profiles().get(uid, {})
        return {
            "uid": uid,
            "name": profile.get("name"),
            "avatar": avatar_url(profile.get("avatar")),
            "bot": {
                "id": bot["id"],
                "name": bot["name"],
                "avatar": bot_avatar(bot["id"]),
                "champion": bot["id"] == CHAMPION,
            },
            "debug": args.debug,
        }

    @app.post("/api/me")
    def set_name(request: Request, body: Name):
        if not body.name.strip():
            raise HTTPException(422, "name can't be blank")
        store.set_name(request.state.uid, body.name.strip())
        return me(request)

    @app.post("/api/me/avatar")
    async def upload_avatar(request: Request):
        """The picture is the raw request body (the browser already shrinks it)."""
        if request.state.uid not in store.profiles():
            raise HTTPException(409, "choose a display name first")
        data = await request.body()
        if len(data) > 5_000_000:
            raise HTTPException(413, "picture too large")
        try:
            image = await asyncio.to_thread(avatar_image, data)
        except Exception:
            raise HTTPException(422, "not an image we can read")
        store.set_avatar(request.state.uid, image)
        return me(request)

    @app.delete("/api/me/avatar")
    def remove_avatar(request: Request):
        store.set_avatar(request.state.uid, None)
        return me(request)

    @app.post("/api/reports")
    def report_bug(request: Request, body: Report):
        report = {
            **body.model_dump(),
            "app_version": APP_VERSION,
            "user_agent": request.headers.get("user-agent", "")[:300],
        }
        if len(json.dumps(report)) > 20_000:
            raise HTTPException(413, "report too large")
        store.add_report(request.state.uid, report)
        return {"ok": True}

    @app.get("/api/avatar/{avatar_id}")
    def get_avatar(avatar_id: str):
        image = store.avatar(avatar_id)
        if image is None:
            raise HTTPException(404, "no such picture")
        # A new upload gets a new id, so this one never changes
        return Response(
            image,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @app.get("/api/games")
    def list_games(request: Request, scope: Literal["mine", "all"] = "mine"):
        profiles = store.profiles()
        out = []
        for g in store.summaries():
            if scope == "mine" and not any(
                s.get("uid") == request.state.uid for s in g["seats"]
            ):
                continue
            for s in g["seats"]:
                s.update(look(s, profiles))
            out.append({**g, "abandoned": is_abandoned(g)})
        return out[:200]

    @app.get("/api/leaderboard")
    def get_leaderboard():
        profiles = store.profiles()
        names = {uid: p["name"] for uid, p in profiles.items()}
        board = leaderboard(
            store.summaries(),
            names,
            {bot_id: b["name"] for bot_id, b in BOTS.items()},
            CHAMPION,
        )
        for row in board["players"]:
            row["avatar"] = profiles.get(row["id"], {}).get("avatar")
        for row in board["bots"]:
            row["avatar"] = bot_avatar(row["id"])
        return {**board, "champion": BOTS[CHAMPION]["name"]}

    @app.post("/api/games")
    async def new_game(request: Request, body: NewGame):
        uid = request.state.uid
        name = store.profiles().get(uid, {}).get("name")
        if not name:
            raise HTTPException(409, "choose a display name first")
        evict()
        gid = secrets.token_urlsafe(8)
        seats = [human_seat(uid, name)] + [bot_seat(bot) for _ in range(body.opponents)]
        games[gid] = Game(Session(seats, scoring=body.scoring, seed=args.seed))
        await save(gid)
        return view(request, gid)

    @app.get("/api/games/{gid}")
    async def get_game(request: Request, gid: str):
        await get(gid)
        return view(request, gid)

    @app.post("/api/games/{gid}/act")
    async def act(request: Request, gid: str, body: Act):
        game = await get(gid)
        async with game.lock:
            s, me = game.session, seat(request, game)
            if body.version != s.version:
                raise HTTPException(409, "the game moved on (another tab?)")
            if me is None or not s.turn_of(me) or not 0 <= body.index < len(s.actions):
                raise HTTPException(409, "not a legal action right now")
            s.act(me, body.index)
            await save(gid)
        return view(request, gid)

    @app.post("/api/games/{gid}/step")
    async def step(request: Request, gid: str):
        game = await get(gid)
        async with game.lock:
            s = game.session
            if seat(request, game) is None:
                raise HTTPException(403, "only players advance the AI")
            if (p := s.ai_player()) is not None:
                action, s.ai[p] = await asyncio.get_running_loop().run_in_executor(
                    app.state.pool, choose_action, s.ai[p], s.state, s.actions
                )
                s.ai_act(action)
                await save(gid)
        return view(request, gid)

    app.mount("/", StaticFiles(directory=STATIC, html=True))
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Wingspan in the browser")
    parser.add_argument(
        "--bot",
        default=CHAMPION,
        choices=list(BOTS),
        help="AI opponent for new games (bots.yaml)",
    )
    parser.add_argument(
        "--sims", type=int, default=None, help="override MCTS simulations"
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--db", default="games.db", help="SQLite database file")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="read-only database; you sit in each game's owner seat",
    )
    parser.add_argument("--auth", default="dev", choices=["dev", "cloudflare"])
    parser.add_argument(
        "--user", default="you@localhost", help="the signed-in email with --auth dev"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--workers", type=int, default=os.cpu_count(), help="AI worker processes"
    )
    parser.add_argument("--no-browser", dest="open_browser", action="store_false")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    print(f"Wingspan running at http://{args.host}:{args.port}  (Ctrl+C to quit)")
    uvicorn.run(create_app(args), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
