# lab

Experiment framework: simulation harness, result storage, analysis and tuning. Strategies come from `wingspan.ai`.

## Files

| File | Role |
|------|------|
| `__main__.py` | CLI entry point: load YAML config, drive games, write results |
| `simulation.py` | play one game end to end (`GameResult`, decisions), and many in a worker pool (`play_games`) |
| `generators.py` | yield `(strategies, game_seed, labels)` for the continuous, paired and vs_reference modes; config validation |
| `data.py` | `GameResult` / `DecisionRecord` dataclasses + incremental Parquet writers |
| `summary.py` | per-arm results from games parquets: win rate, score difference, per-seed paired difference, s/game |
| `analysis.py` | build per-run `report.html` + the central `analysis.html` index |
| `dataset.py` | replay recorded games into training tensors |

## Subpackages

| Package | Role |
|---------|------|
| `tune/` | Optuna hyperparameter search over any strategy's params, vs any reference (`python -m lab.tune`) |
| `benchmarks/` | performance benchmarks and determinism regression tests |
| `tools/` | one-off maintenance scripts (e.g. merging a continuation run) |

## Dependencies

```
data.py        <- stdlib, pyarrow, pandas, uuid6
simulation.py  <- wingspan.engine.*, wingspan.ai, data.py
generators.py  <- wingspan.ai
summary.py     <- pandas
__main__.py    <- wingspan.ai, data.py, simulation.py, generators.py, summary.py
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

# Also record per-decision data (legal moves, visits, Q per move): do this for experiments too
uv run python -m lab -c path/to/config.yaml --record-decisions

# Per-arm results of runs, anytime
uv run python -m lab.summary experiments/data/<run-id-or-folder>

# Rebuild every per-run report + the analysis.html index
uv run python -m lab.analysis

# Hyperparameter search (writes to experiments/tuning/<study_name>/)
uv run python -m lab.tune -c path/to/tuning_config.yaml
```

Each run gets its own directory under `experiments/data/<run_id>/` (or `-o <dir>`), holding a copy of
its `config.yaml`, `games.parquet` (one row per game+player), `decisions.parquet` (only with
`--record-decisions`), and the generated `report.html`. See `experiments/README.md` for the config
schema and the label convention.
