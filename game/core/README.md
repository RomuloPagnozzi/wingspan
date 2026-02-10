# game/core

Game state data structures and initialization.

## Files

| File | Role |
|------|------|
| `models.py` | the domain vocabulary: types, cards, players, board |
| `game.py` | the state container and how to start a match |
| `action_types.py` | the moves a player can choose from |
| `custom_copy.py` | faster than standard deepcopy |

## Dependencies

```
models.py       <- stdlib only
action_types.py <- stdlib only
game.py         <- models.py, action_types.py (type-only)
custom_copy.py  <- models.py, game.py
```

## Usage

```python
from game.core import initiate_state, GameState, copy_state

state = initiate_state(n_players=2)
new_state = copy_state(state)
```