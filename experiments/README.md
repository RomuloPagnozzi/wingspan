# experiments

MCTS experiment configurations, results, and research notes. The runner lives in `lab/` — this directory is data + plans.

## Files

| File | Role |
|------|------|
| `ROADMAP.md` | big-picture project vision and phases |
| `BACKLOG.md` | prioritized next-up work, with inline engineering specs |
| `INBOX.md` | unprioritized idea capture |
| `EXPERIMENTS.md` | research philosophy, hypotheses, experiment catalog, and results |

## Subfolders

| Folder | Contents |
|--------|----------|
| `configs/` | YAML configs consumed by `python -m lab -c <path>` |
| `data/` | Parquet outputs: `games.parquet` and (optional) `decisions.parquet` |

## Usage

```bash
# Run a paired exploration-constant sweep
uv run python -m lab -c experiments/configs/paired_exploration_constant.yaml

# Smoke test (4 tiny games)
uv run python -m lab -c experiments/configs/test.yaml

# Inspect results
python -c "import pandas as pd; print(pd.read_parquet('experiments/data/games.parquet').head())"
```

See `EXPERIMENTS.md` for the paired-comparison design and the rationale behind each experiment.
