# game/core

Game state data structures and initialization.

## Files

| File | Contents |
|------|----------|
| `constants.py` | Immutable types: `PinkTrigger`, `GamePhase`, `ScoringMode`, `BirdCard`, `Bonus` |
| `player.py` | Player/board state: `BirdState`, `PlacedBird`, `Spot`, `ScoreState`, `Player` |
| `turn_data.py` | Turn execution: `PowerExecution`, `QueuedPower`, `CostPayment`, `EndTurnEffect`, `ActionData` |
| `registry.py` | Card registries and loaders |
| `game.py` | `GameState`, `initiate_state()`, `roll_feeder()` |
| `custom_copy.py` | Custom state copying (~20x faster than deepcopy) |

## Dependencies

```
constants.py   ← stdlib only
registry.py    ← constants.py
player.py      ← registry.py
turn_data.py   ← (type-only imports)
game.py        ← player.py, turn_data.py, registry.py
custom_copy.py ← all above
```

## Usage

```python
from game.core import initiate_state, GameState, copy_state

state = initiate_state(n_players=2)
new_state = copy_state(state)
```
