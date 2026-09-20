# lab

Experiment framework: strategies that play the game, simulation harness, and result storage.

## Files

| File | Role |
|------|------|
| `__main__.py` | CLI entry point: load YAML config, drive games, write results |
| `simulation.py` | run one game end to end and return a `GameResult` |
| `generators.py` | yield `(strategies, game_seed)` pairs for continuous or paired modes |
| `data.py` | `GameResult` / `DecisionRecord` dataclasses + incremental Parquet writers |
| `analysis.py` | build per-run `report.html` + the central `analysis.html` index |

## Subpackages

| Package | Role |
|---------|------|
| `strategies/` | game-playing strategies (Random, MCTS) registered by name |
| `tune/` | Optuna hyperparameter search over `MCTSConfig` (`python -m lab.tune`) |
| `benchmarks/` | performance benchmarks and determinism regression tests |
| `tools/` | one-off maintenance scripts (e.g. merging a continuation run) |

## Dependencies

```
strategies/    <- game.core, game.actions, game.engine
data.py        <- stdlib, pyarrow, pandas, uuid6
simulation.py  <- game.*, strategies, data.py
generators.py  <- strategies
__main__.py    <- strategies, data.py, simulation.py, generators.py
benchmarks/    <- game.*, strategies
analysis.py    <- pandas, matplotlib, seaborn (standalone)
tune/          <- optuna, lab.generators, lab.simulation, lab.data
tools/         <- pandas, pyarrow, lab.data
```

## Usage

```bash
# Run an experiment defined in YAML (-c is required)
uv run python -m lab -c path/to/config.yaml

# List the matchups a config would run, without executing
uv run python -m lab --list -c path/to/config.yaml

# Also record per-decision data for RL training
uv run python -m lab -c path/to/config.yaml --record-decisions

# Rebuild every per-run report + the analysis.html index
uv run python -m lab.analysis

# Hyperparameter search (writes to experiments/tuning/<study_name>/)
uv run python -m lab.tune -c path/to/tuning_config.yaml
```

Each run gets its own directory under `experiments/data/<run_id>/` (or `-o <dir>`), holding a copy of
its `config.yaml`, `games.parquet` (one row per game+player), `decisions.parquet` (only with
`--record-decisions`), and the generated `report.html`. See `experiments/README.md` for the config
schema and the label convention.
