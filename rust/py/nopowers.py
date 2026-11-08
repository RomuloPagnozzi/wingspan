"""Import this to switch off bird powers in the Python engine (in this process only), so it plays the same
rules as the M1 Rust engine. Patches the three places powers are looked up; engine source is untouched."""

import wingspan.engine.actions as _actions
import wingspan.engine.engine as _engine


def _none(*_args, **_kwargs):
    return []


_engine.get_triggered_powers = _none
_engine.get_triggered_pink_powers = _none
_actions.get_triggered_powers = _none
