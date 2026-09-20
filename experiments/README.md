# experiments

Experiment outputs. The runner lives in `lab/`; the planning and research docs live at the repo root
(`ROADMAP.md`, `INBOX.md`, `EXPERIMENTS.md`).

## Layout

Everything lives under `data/`, one directory per run, named by the run's ULID:

```
data/
  analysis.html                  # index: dropdown over every run's report
  019eb2ca-.../
    config.yaml                  # the config this run was launched with (copied at start)
    games.parquet                # one row per (game, player)
    decisions.parquet            # one row per decision (only with --record-decisions)
    report.html                  # generated per-run report
tuning/
  mcts_joint_v1/                 # one directory per Optuna study
    config.yaml                  # the tuning config
    study.db                     # optuna sqlite storage (resumable)
    trials.csv                   # per-trial params + win rate
    games.parquet                # games from every trial, merged
    best_params.yaml             # winning config + win rate + source run id
```

Runs are **self-contained**: the runner copies the source YAML into the run directory, so a run is
always interpretable from its own folder and nothing depends on where the config was authored.

`data/` is gitignored — runs exist only on the machine that produced them.

## Authoring a config

Configs are ad-hoc: write the YAML anywhere (scratch dir, home, `/tmp`) and pass it with `-c`. There
is no configs directory in the repo — the copy inside the run dir is the one that persists.

**Label convention:** the first `#` comment line of a config becomes the run's label in the
`analysis.html` dropdown. Without it the dropdown falls back to the bare ULID, which is unreadable.
Always start a config with a one-line description:

```yaml
# widening_k_sweep @2000 sims
mode: vs_reference
```

Keep it short and specific — parameter swept plus the setting that distinguishes it from neighbours
(`@2000 sims`, `@100 games`).

## Usage

```bash
# Run an experiment (-c is required, repeat to queue several)
uv run python -m lab -c path/to/config.yaml

# Preview the matchups without running them
uv run python -m lab --list -c path/to/config.yaml

# Also record per-decision data (for RL training)
uv run python -m lab -c path/to/config.yaml --record-decisions

# Rebuild every per-run report + the analysis.html index
uv run python -m lab.analysis

# Inspect results
python -c "import pandas as pd; print(pd.read_parquet('experiments/data/<run-id>/games.parquet').head())"
```

Hyperparameter search is a separate entry point, writing to `tuning/<study_name>/`:

```bash
uv run python -m lab.tune -c path/to/tuning_config.yaml
```

Studies are resumable — rerunning against an existing `study.db` continues where it left off.

## Config schema

`mode:` selects one of three modes (default `continuous`). Every arm carries a mandatory, unique
`label` — it identifies the arm in `games.parquet` and in the reports.

### `vs_reference`

Each arm plays the fixed project-wide reference opponent (`REFERENCE_PARAMS` in `lab/generators.py`),
with shared seeds and position swapping. Win rates across *any* vs_reference experiment are on a
common scale. Scales linearly in number of arms.

```yaml
# widening_k_sweep @2000 sims
mode: vs_reference

num_workers: 4

base:                          # shared strategy params for every arm
  strategy: mcts
  simulations: 2000
  exploration_constant: 1.41
  value_function: score_delta
  determinize: true
  widening_alpha: 0.5

compare:
  parameter: widening_k        # required when arms use `value`
  reference_label: "reference" # required; must not collide with an arm label
  values:
    - {value: 0.25, label: "k=0.25"}
    - {value: 0.5,  label: "k=0.5"}
    - {value: 0.75, label: "k=0.75"}

seeds:
  count: 50                    # number of seed pairs
  start: 1                     # starting seed (reproducibility)
```

At least 1 arm. Total games = `len(values) × seeds.count × 2` (the ×2 is the position swap).

### `paired`

Direct A-vs-B head-to-head with shared seeds. Highest statistical power per binary question, but
scales pairwise — expensive beyond 2 arms. Use for specific A/B questions or to tiebreak two arms
that came out close in a `vs_reference` sweep.

Arms may use `overrides` (a mapping) instead of `value` to vary several fields at once; with
`overrides` on every arm, `compare.parameter` is not needed.

```yaml
# tuned_1500 vs ref_2k @100 games
mode: paired

num_workers: 4

base:
  strategy: mcts
  determinize: true

compare:
  values:
    - label: ref_2k
      overrides:
        simulations: 2000
        exploration_constant: 1.41
        value_function: score_delta
    - label: tuned_1500
      overrides:
        simulations: 1500
        exploration_constant: 2.27
        value_function: absolute_score
        widening_alpha: 0.83
        widening_k: 1.7

seeds:
  count: 50
  start: 100
```

At least 2 arms. Total games = `C(len(values), 2) × seeds.count × 2`.

### `continuous`

Open-ended matchups with no fixed seeds; runs until Ctrl+C. For exploratory generation, smoke runs,
or accumulating games when the paired design isn't needed.

```yaml
# exploratory: sim-count matchups
mode: continuous

defaults:                      # merged into every strategy spec
  value_function: score_delta
  num_workers: 8
  games_per_round: 5           # games per matchup per cycle

matchups:                      # each matchup is a list of >= 2 strategy specs
  - - {strategy: mcts, simulations: 500,  label: mcts_500}
    - {strategy: mcts, simulations: 1000, label: mcts_1000}
```

---

See `EXPERIMENTS.md` for the paired-comparison design and the rationale behind each experiment.
