# experiments/configs

YAML configs for the experiment runner. Each file describes one experiment; pass it with `python -m lab -c <path>`.

## Files

| File | Contents |
|------|----------|
| `config.yaml` | continuous matchups: pairwise and 3-way MCTS simulation-count comparisons |
| `paired_exploration_constant.yaml` | paired sweep of `exploration_constant ∈ {0.5, 1.0, 1.41, 2.0}` |
| `test.yaml` | minimal paired config (4 games) for end-to-end smoke testing |

## Schema

Two top-level modes, selected via `mode:` (default `continuous`).

### Continuous mode

Runs matchups indefinitely; stop with Ctrl+C.

```yaml
defaults:                    # merged into every strategy spec
  value_function: score_delta
  num_workers: 8
  games_per_round: 5         # how many games per matchup per cycle

matchups:                    # list of matchup specs (each is a list of player specs)
  - - strategy: mcts
      simulations: 500
    - strategy: mcts
      simulations: 1000
```

### Paired mode

Fixed game/MCTS seeds, position-swapped. Total games = `C(len(values), 2) × seeds.count × 2`.

```yaml
mode: paired

base:                        # shared strategy params
  strategy: mcts
  simulations: 500
  value_function: score_delta

compare:
  parameter: exploration_constant
  values: [0.5, 1.0, 1.41, 2.0]

seeds:
  count: 50                  # number of seed pairs
  start: 1                   # starting seed (reproducibility)
```
