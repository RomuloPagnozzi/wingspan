# lab

Experiments, tuning and the training pipeline. Strategies come from `wingspan.ai`.

| File | Role |
|---|---|
| `__main__.py` | run a YAML config: play the games, write games/decisions parquets, print the summary |
| `generators.py` | the games each mode plays (`continuous`, `paired`, `vs_reference`); config validation |
| `simulation.py` | play one game (`simulate_game`), or many in a worker pool (`play_games`) |
| `data.py` | `GameResult` / `DecisionRecord` and the incremental parquet writers |
| `summary.py` | per-arm results: win rate, score difference, per-seed paired difference, s/game |
| `tune/` | Optuna search over any strategy's params against a reference |
| `dataset.py` | replay recorded games into training arrays |
| `train_value.py` | train the value net on a dataset |
| `cloud.py`, `cloud_agent.py` | self-play on a rented server (outdated, see docs/INBOX.md) |
| `explainer/` | interactive page explaining the encoder (outdated, see docs/INBOX.md) |

## Usage

```bash
uv run python -m lab -c experiments/selfplay.yaml --record-decisions -o experiments/data/selfplay
uv run python -m lab --list -c CONFIG               # what a config would play
uv run python -m lab.summary experiments/data/DIR   # results of runs (also while they run)
uv run python -m lab.tune -c TUNING.yaml            # Optuna study -> experiments/tuning/<study_name>/
uv run python -m lab.dataset experiments/data/selfplay/* --out experiments/data/datasets/selfplay
uv run --group train python -m lab.train_value experiments/data/datasets/selfplay
```

Always pass `--record-decisions`: legal moves, visits and Q per move are what any later analysis needs.
Long runs: prefix with `caffeinate -dis`. Ctrl+C once lets in-flight games finish; twice quits.

Each run writes `<output dir>/<run_id>/`: `config.yaml` (copied), `code_version.txt`, `games.parquet` (one
row per game and player, with `duration_s`) and `decisions.parquet`; with `--rotate-every N`, numbered
parts (`games_0000.parquet`, ...) so a long run can be read or copied while it goes on.

## Configs

The first `#` line of a config is its description. Every arm has a unique `label`; strategy specs are
`{strategy: <name>, <params>...}` (`mcts_rs`, `mcts`, `random`). YAML anchors under `x-` keys
can hold shared specs. `seeds: {start, count}`: `start` an int or `clock` (new deals every run), no `count`
runs until Ctrl+C. `blue_share`: share of games scored with the blue round-goal side (default 0).

**`vs_reference`**: every arm plays `compare.reference` on each seed, from both seats. Seed-major: every
arm plays a seed before the next starts, so arms stay balanced whenever the run stops.

```yaml
# exploration constant of the tree at 10k simulations, vs the tuned tree at 1500
mode: vs_reference
num_workers: 7
base: {strategy: mcts_rs, simulations: 10000}
compare:
  reference_label: tree_1500
  reference: {strategy: mcts_rs}
  parameter: exploration_constant            # arms with `value`; or `overrides: {...}` per arm
  values:
    - {label: c0.3, value: 0.3}
    - {label: c1.1, value: 1.1}
seeds: {start: clock}
```

**`paired`**: every pair of arms plays each seed from both seats (same shape, no reference). Most power per
A-vs-B question; pairs grow quadratically with arms.

**`continuous`**: `matchups` (lists of specs, merged over `defaults`) played until stopped, or one game per
seed with `seeds`. Self-play data: `experiments/selfplay.yaml`.

**Tuning** (`lab.tune`): `base` is the candidate's spec (`strategy` defaults to `mcts`), `space` the sampled
params, `reference` the opponent, `seeds: {start, count}` the same deals for every trial. Unknown params are
an error.

```yaml
study_name: tree_10k
n_trials: 30
num_workers: 7
seeds: {start: 40001, count: 30}
base: {strategy: mcts_rs, simulations: 10000}
reference: {strategy: mcts_rs}
space:
  - {name: exploration_constant, type: float, low: 0.02, high: 3.0, log: true}
  - {name: widening_k, type: float, low: 0.5, high: 3.0}
```
