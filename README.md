# Wingspan

Building the strongest possible Wingspan player through MCTS and deep reinforcement learning.

Managed with [uv](https://docs.astral.sh/uv/).

## Structure

| Path | Role |
|------|------|
| `game/` | complete game engine: state, rules, actions, scoring |
| `lab/` | experiment framework: strategies, run harness, analysis, tuning |
| `experiments/` | experiment outputs (run data, reports, tuning studies) |
| `tests/` | pytest suite covering the full game engine |
| `play.py` | WIP interactive client for testing the game (Textual TUI) |

## Planning docs

| File | Role |
|------|------|
| `ROADMAP.md` | big-picture project vision and phases |
| `EXPERIMENTS.md` | research philosophy, experiment catalog, and results |
| `INBOX.md` | unprioritized idea capture |

## Usage

```bash
uv run pytest tests/                       # run tests
uv run python play.py                      # launch interactive TUI
uv run python -m lab -c path/to/cfg.yaml   # run an experiment
uv run python -m lab.analysis              # rebuild reports + analysis.html
```

See `experiments/README.md` for the config schema and run layout.
