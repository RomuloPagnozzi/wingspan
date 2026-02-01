# game/power

Bird power execution system.

## Files

| File | Contents |
|------|----------|
| `handlers.py` | Power handlers for all 21 powers, `get_power_handler()`, `@power_handler` decorator |
| `choices.py` | Choice generators for power phases, `get_power_choice_generator()`, `@power_choices` decorator |
| `validators.py` | Power executability checks, `can_execute_power()`, `@power_validator` decorator |

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
