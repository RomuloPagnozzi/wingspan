# lab

Experiment framework: strategies that play the game, simulation harness, and result storage.

## Files

| File | Role |
|------|------|
| `__main__.py` | CLI entry point: load YAML config, drive games, write results |
| `simulation.py` | run one game end to end and return a `GameResult` |
| `generators.py` | yield `(strategies, game_seed)` pairs for continuous or paired modes |
| `data.py` | `GameResult` / `DecisionRecord` dataclasses + incremental Parquet writers |
| `analysis.py` | legacy plotting helpers (CSV-era — see `experiments/TODO.md`) |

## Subpackages

| Package | Role |
|---------|------|
| `strategies/` | game-playing strategies (Random, MCTS) registered by name |
| `benchmarks/` | performance benchmarks and determinism regression tests |

## Dependencies

```
strategies/    <- game.core, game.actions, game.engine
data.py        <- stdlib, pyarrow, pandas, uuid6
simulation.py  <- game.*, strategies, data.py
generators.py  <- strategies
__main__.py    <- strategies, data.py, simulation.py, generators.py
benchmarks/    <- game.*, strategies
analysis.py    <- pandas, matplotlib, seaborn (standalone)
```

## Usage

```bash
# Run an experiment defined in YAML
uv run python -m lab -c experiments/configs/config.yaml

# List the matchups a config would run, without executing
uv run python -m lab --list -c experiments/configs/config.yaml

# Also record per-decision data for RL training
uv run python -m lab -c experiments/configs/config.yaml --record-decisions
```

Output Parquet files land in `experiments/data/` (or `-o <dir>`):

- `games.parquet` — one row per (game, player)
- `decisions.parquet` — one row per decision (only when `--record-decisions`)
