"""Step-by-step parity of the Rust engine against the Python one (no powers, M1).

At every state of many random Python games: the legal action lists must be identical (same strings, same
order), and for EVERY legal action the next state must be identical, with Rust replaying the die rolls and
shuffles that Python drew. Stops at the first mismatch and prints it.

    uv run python rust/py/parity.py [n_games]
"""

import json
import random
import sys

import nopowers  # noqa: F401  (switches powers off before the engine is used)
from pystate import RecordingRandom, to_json
import wingspan_rs

from wingspan.engine.actions import get_actions
from wingspan.engine.core import ScoringMode, copy_state, initiate_state
from wingspan.engine.engine import transition_state_inplace


def diff(a, b, path=""):
    if type(a) is not type(b) or not isinstance(a, (dict, list)) or (isinstance(a, list) and len(a) != len(b)):
        if a != b:
            print(f"  {path or '.'}: python={a!r} rust={b!r}")
        return
    for k in a if isinstance(a, dict) else range(len(a)):
        diff(a[k], b[k], f"{path}.{k}" if isinstance(a, dict) else f"{path}[{k}]")


def check_game(seed: int) -> tuple[int, int]:
    mode = ScoringMode.BLUE if seed % 5 == 0 else ScoringMode.GREEN
    s = initiate_state(2, mode, seed=seed)
    pick = random.Random(seed)
    states = transitions = 0
    while True:
        js = json.dumps(to_json(s))
        py = [str(a) for a in get_actions(s)]
        rs = wingspan_rs.legal_actions(js)
        if py != rs:
            print(f"seed {seed} step {states}: legal actions differ in {s.game_phase}")
            print("  python:", py[:10], "\n  rust:  ", rs[:10])
            sys.exit(1)
        if not py:
            return states, transitions
        for i, action in enumerate(get_actions(s)):
            nxt = copy_state(s)
            nxt.rng = RecordingRandom(s.rng.getstate())
            transition_state_inplace(nxt, action)
            got, unused = wingspan_rs.apply(js, i, nxt.rng.log)
            want = to_json(nxt)
            if json.loads(got) != want or unused:
                print(f"seed {seed} step {states}: {action} in {s.game_phase} gives a different state")
                print(f"  ({unused} unused chance events)")
                diff(want, json.loads(got))
                sys.exit(1)
            transitions += 1
        transition_state_inplace(s, pick.choice(get_actions(s)))
        states += 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    states = transitions = 0
    for seed in range(n):
        a, b = check_game(seed)
        states, transitions = states + a, transitions + b
    print(f"OK: {n} games, {states} states, {transitions} transitions identical")
