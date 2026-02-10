# Wingspan

Building the strongest possible Wingspan player through MCTS and deep reinforcement learning.

Managed with [uv](https://docs.astral.sh/uv/).

## Structure

| Path | Role |
|------|------|
| `game/` | complete game engine: state, rules, actions, scoring |
| `tests/` | pytest suite covering the full game engine |
| `play.py` | WIP interactive client for testing the game (Textual TUI) |

## Usage

```bash
uv run pytest tests/   # run tests
uv run python play.py  # launch interactive TUI
```
