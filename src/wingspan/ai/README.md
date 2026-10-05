# wingspan.ai

Game-playing strategies. All strategies implement `Strategy.select_action(state, legal_actions) -> Action`.

## Files

| File | Role |
|------|------|
| `base.py` | `Strategy` ABC, `ValueFunction` enum, name registry, `create_strategy` factory |
| `random.py` | uniform random action selection (deterministic with a seed) |
| `mcts.py` | MCTS with UCB1 selection, progressive widening, and optional PIMC/IS-MCTS determinization |
| `default_params.yaml` | tuned MCTS params the web app plays with (copied from `experiments/tuning/mcts_joint_v1/best_params.yaml`) |

Only AIs that ship with the app live here. Experimental strategies can live in `lab/` and self-register with `@register_strategy`; promote them here once they prove out.

## Dependencies

```
base.py    <- wingspan.engine.core
random.py  <- wingspan.engine.core, base.py
mcts.py    <- wingspan.engine.core, wingspan.engine.actions, wingspan.engine.engine, base.py
```

## Registry

Strategies self-register via `@register_strategy` on the class. `create_strategy(name, **params)` looks the class up by its `name` class attribute (`"random"`, `"mcts"`). The driver in `lab/__main__.py` and the YAML configs reference strategies by this string.

## Usage

```python
from wingspan.ai import create_strategy

# By name + kwargs (how configs build strategies)
strategy = create_strategy("mcts", simulations=500, exploration_constant=1.41, seed=42)

# Direct construction
from wingspan.ai import MCTSStrategy, MCTSConfig, ValueFunction
strategy = MCTSStrategy(
    params=MCTSConfig(simulations=500, value_function=ValueFunction.SCORE_DELTA),
    seed=42,
)

action = strategy.select_action(state, legal_actions)
```

## Determinism contract

For paired comparison experiments, `(game_seed, mcts_seed, simulations, exploration_constant, value_function)` must uniquely determine the move sequence. `lab/benchmarks/test_determinism.py` is the regression test — do not introduce non-deterministic shortcuts (sets without sort, dict-order rollout, etc.) in this package.
