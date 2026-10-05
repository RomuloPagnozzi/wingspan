"""Web server for playing Wingspan in the browser against AI opponents.

    uv run wingspan                                 # you vs tuned MCTS, opens the browser
    uv run wingspan --players 3 --sims 300 --ai random
    uv run wingspan --host 0.0.0.0 --no-browser     # serve to others (Docker)

Each game lives in memory under a random id (the page URL carries it as ?g=<id>).
The browser drives the game: it posts the index of a legal action for you, and
calls /step to advance AI moves one at a time so they show up in the log as they
happen. AI moves run in a process pool so a long MCTS search never blocks other games.
"""

import argparse
import asyncio
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
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from wingspan.engine.core import init_registries

from .session import Session, catalog

STATIC = Path(__file__).parent / "static"
DEFAULT_PARAMS = Path(__file__).parent.parent / "ai" / "default_params.yaml"
MAX_GAMES = 500
IDLE_SECONDS = 6 * 3600


def choose_action(strategy, state, actions):
    """Runs in a worker process. Returns the strategy so its RNG state carries over."""
    return strategy.select_action(state, actions), strategy


@dataclass
class Game:
    session: Session
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)


class NewGame(BaseModel):
    players: int | None = Field(None, ge=2, le=5)
    ai: Literal["mcts", "random"] | None = None
    scoring: Literal["green", "blue"] | None = None


class Act(BaseModel):
    index: int
    version: int  # the state version the client chose from


def create_app(args) -> FastAPI:
    ai_params = yaml.safe_load(Path(args.params).read_text())["params"]
    if args.sims is not None:
        ai_params["simulations"] = args.sims
    games: dict[str, Game] = {}
    cards = json.dumps(catalog()).encode()

    @asynccontextmanager
    async def lifespan(app):
        with ProcessPoolExecutor(args.workers, initializer=init_registries) as pool:
            app.state.pool = pool
            if args.open_browser:
                webbrowser.open(f"http://127.0.0.1:{args.port}")
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"  # pick up new ui/ files right away
        # No keep-alive: a proxy in between (e.g. Docker Desktop) can hide the server closing an idle
        # connection, and the browser's next POST then dies on it (browsers only retry GETs).
        response.headers["Connection"] = "close"
        return response

    def get(gid: str) -> Game:
        if gid not in games:
            raise HTTPException(404, "game not found")
        game = games[gid]
        game.touched = time.monotonic()
        return game

    def view(gid: str) -> dict:
        return {"id": gid, **games[gid].session.view()}

    def evict():
        now = time.monotonic()
        for gid in [g for g, game in games.items() if now - game.touched > IDLE_SECONDS]:
            del games[gid]
        while len(games) >= MAX_GAMES:
            del games[min(games, key=lambda g: games[g].touched)]

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "games": len(games)}

    @app.get("/api/cards")
    def get_cards():
        return Response(cards, media_type="application/json")

    @app.post("/api/games")
    def new_game(body: NewGame | None = None):
        body = body or NewGame()
        evict()
        gid = secrets.token_urlsafe(8)
        ai = body.ai or args.ai
        games[gid] = Game(
            Session(
                players=body.players or args.players,
                ai=ai,
                scoring=body.scoring or args.scoring,
                ai_params=ai_params if ai == "mcts" else None,
                seed=args.seed,
            )
        )
        return view(gid)

    @app.get("/api/games/{gid}")
    def get_game(gid: str):
        get(gid)
        return view(gid)

    @app.post("/api/games/{gid}/act")
    async def act(gid: str, body: Act):
        game = get(gid)
        async with game.lock:
            s = game.session
            if body.version != s.version:
                raise HTTPException(409, "the game moved on (another tab?)")
            if not s.human_turn() or not 0 <= body.index < len(s.actions):
                raise HTTPException(409, "not a legal action right now")
            s.act(body.index)
        return view(gid)

    @app.post("/api/games/{gid}/step")
    async def step(gid: str):
        game = get(gid)
        async with game.lock:
            s = game.session
            if (p := s.ai_player()) is not None:
                action, s.ai[p] = await asyncio.get_running_loop().run_in_executor(
                    app.state.pool, choose_action, s.ai[p], s.state, s.actions
                )
                s.ai_act(action)
        return view(gid)

    app.mount("/", StaticFiles(directory=STATIC, html=True))
    return app


def main():
    parser = argparse.ArgumentParser(description="Play Wingspan in the browser")
    parser.add_argument("--players", type=int, default=2, choices=[2, 3, 4, 5])
    parser.add_argument("--ai", default="mcts", choices=["random", "mcts"])
    parser.add_argument("--scoring", default="green", choices=["green", "blue"], help="goal board side")
    parser.add_argument("--params", default=DEFAULT_PARAMS, help="MCTS params yaml")
    parser.add_argument("--sims", type=int, default=None, help="override MCTS simulations")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="AI worker processes")
    parser.add_argument("--no-browser", dest="open_browser", action="store_false")
    args = parser.parse_args()

    print(f"Wingspan running at http://{args.host}:{args.port}  (Ctrl+C to quit)")
    uvicorn.run(create_app(args), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
