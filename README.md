# Wingspan

Building the strongest possible Wingspan player through MCTS and deep reinforcement learning.

Managed with [uv](https://docs.astral.sh/uv/).

## Structure

| Path | Role |
|------|------|
| `src/wingspan/engine/` | complete game engine: state, rules, actions, scoring |
| `src/wingspan/ai/` | AI players shipped with the app (random, tuned MCTS) |
| `src/wingspan/web/` | browser UI: FastAPI server, SQLite store, vanilla JS client |
| `deploy/` | production compose file, server settings template, nightly backup script |
| `lab/` | research: run harness, analysis, tuning |
| `experiments/` | experiment outputs (run data, reports, tuning studies) |
| `tests/` | pytest suite covering the full game engine |
| `docs/` | rules, roadmap, experiment catalog, idea inbox |

## Usage

```bash
uv sync                                    # everything (dev + lab + web groups)
uv run pytest                              # run tests
uv run wingspan                            # play in the browser vs the champion bot (--sims 50 for a fast one, ...)
uv run python -m lab -c path/to/cfg.yaml   # run an experiment
uv run python -m lab.analysis              # rebuild reports + analysis.html
```

## Web app

A menu (new game: 1-4 opponents, green/blue goal board; continue; your games; everyone's games;
a humans-vs-AI leaderboard) and the game itself. Opponents come from the bot roster in
`src/wingspan/ai/bots.yaml`: new games face its `champion`, and each game records the bot and its
exact params. Games are stored in SQLite as seed + actions (the lab's format) and replayed to resume.

Pictures: players upload their own (optional; otherwise their initial shows). The server re-encodes
each upload as a 256 px WebP and stores it in SQLite under a random id. Bot pictures live in
`src/wingspan/web/static/bots/<bot id>.webp`: square, about 256 px, shown cropped to a circle.

## Deploy

Production is self-hosted: a container on a server you can SSH into, bound to localhost and reached
only through Cloudflare Tunnel, behind Cloudflare Access (Google sign-in + an email allowlist). The
app verifies Access's signed token and uses its email as the player's identity, so inviting someone is
adding their email to the Access policy. Set `DEPLOY_HOST` in `.env` (see `.env.example`), then:

```bash
make setup                  # once: /srv/wingspan, its .env (Cloudflare values), nightly backups
make deploy                 # build for the server's CPU, ship the image over SSH, restart
make logs                   # recent server logs
make backup                 # pull a consistent copy of the live database to ~/Backups/wingspan
make reports                # players' bug reports, each with the command to reopen that moment
make debug ID=<game> [AT=<move>]   # open that copy locally, read-only, in the owner's seat
```

See `experiments/README.md` for the config schema and run layout.
