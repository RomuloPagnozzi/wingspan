# game/power

Bird power execution system.

## Files

| File | Role |
|------|------|
| `handlers.py` | what each bird power actually does when activated |
| `choices.py` | what options a power presents to the player |
| `validators.py` | whether a power can activate given the current state |

## Dependencies

```
validators.py  ← ..core, ..utils
choices.py     ← ..core, ..utils
handlers.py    ← ..core, ..effects, ..utils, validators.py
```

## Usage

```python
from game.power import get_power_handler, get_power_choice_generator, can_execute_power

# Check if power can execute
if can_execute_power(state, power_entry):
    handler = get_power_handler(power_id, phase)
    state = handler(state, stack, action)

# Get valid choices for a power phase
generator = get_power_choice_generator(power_id, phase)
choices = generator(state, execution)
```
