# lab

Experiment framework: simulation harness, result storage, analysis and tuning. Strategies come from `wingspan.ai`.

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
| `tune/` | Optuna hyperparameter search over `MCTSConfig` (`python -m lab.tune`) |
| `benchmarks/` | performance benchmarks and determinism regression tests |
| `tools/` | one-off maintenance scripts (e.g. merging a continuation run) |

## Dependencies

```
data.py        <- stdlib, pyarrow, pandas, uuid6
simulation.py  <- wingspan.engine.*, wingspan.ai, data.py
generators.py  <- wingspan.ai
__main__.py    <- wingspan.ai, data.py, simulation.py, generators.py
benchmarks/    <- wingspan.engine.*, wingspan.ai
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
