# Wingspan

Building the strongest possible Wingspan player through MCTS and deep reinforcement learning.

Managed with [uv](https://docs.astral.sh/uv/).

## Structure

| Path | Role |
|------|------|
| `src/wingspan/engine/` | complete game engine: state, rules, actions, scoring |
| `src/wingspan/ai/` | AI players shipped with the app (random, tuned MCTS) |
| `src/wingspan/web/` | browser UI: FastAPI server + vanilla JS client |
| `lab/` | research: run harness, analysis, tuning |
| `experiments/` | experiment outputs (run data, reports, tuning studies) |
| `tests/` | pytest suite covering the full game engine |
| `docs/` | rules, roadmap, experiment catalog, idea inbox |

## Usage

```bash
uv sync                                    # everything (dev + lab + web groups)
uv run pytest                              # run tests
uv run wingspan                            # play in the browser vs tuned MCTS (--ai random, --players 3, ...)
uv run python -m lab -c path/to/cfg.yaml   # run an experiment
uv run python -m lab.analysis              # rebuild reports + analysis.html
```

## Deploy

The Docker image holds only the engine, AI and web server (no research deps):

```bash
docker build -t wingspan .
docker run -p 8000:8000 wingspan           # http://localhost:8000
```

Games live in memory, so run a single instance. Pass server flags after the image name,
e.g. `docker run -p 8000:8000 wingspan wingspan --host 0.0.0.0 --port 8000 --no-browser --sims 800`.
AI moves run in a process pool sized to the CPU count (`--workers`).

See `experiments/README.md` for the config schema and run layout.
