"""Step-by-step parity of the Rust engine against the Python one.

At every state of many random Python games: the legal action lists must be identical (same strings, same
order), and for EVERY legal action the next state must be identical, with Rust replaying the die rolls and
shuffles that Python drew. Stops at the first mismatch and prints it.

    uv run python rust/py/parity.py [n_games] [--players N]
"""

import collections
import json
import random
import sys

import wingspan_rs

from wingspan.ai.rust import to_json
from wingspan.engine.actions import get_actions
from wingspan.engine.core import ScoringMode, copy_state, initiate_state
from wingspan.engine.engine import transition_state_inplace


class RecordingRandom(random.Random):
    """A Random that logs the outcomes the rules drew, for the Rust engine to replay: ("die", [face index])
    for each die rolled, ("shuffle", deck after) for each shuffle."""

    FACES = [["fish"], ["fruit"], ["rodent"], ["invertebrate"], ["seed"], ["invertebrate", "seed"]]

    def __init__(self, state):
        super().__init__()
        self.setstate(state)
        self.log = []

    def choice(self, seq):
        x = super().choice(seq)
        if seq == self.FACES:
            self.log.append(("die", [self.FACES.index(x)]))
        return x

    def shuffle(self, x):
        super().shuffle(x)
        self.log.append(("shuffle", list(x)))


def diff(a, b, path=""):
    if type(a) is not type(b) or not isinstance(a, (dict, list)) or (isinstance(a, list) and len(a) != len(b)):
        if a != b:
            print(f"  {path or '.'}: python={a!r} rust={b!r}")
        return
    for k in a if isinstance(a, dict) else range(len(a)):
        diff(a[k], b[k], f"{path}.{k}" if isinstance(a, dict) else f"{path}[{k}]")


COVERAGE: collections.Counter = collections.Counter()  # (power id, power phase) of the states checked


def check_game(seed: int, n_players: int = 2) -> tuple[int, int]:
    mode = ScoringMode.BLUE if seed % 5 == 0 else ScoringMode.GREEN
    s = initiate_state(n_players, mode, seed=seed)
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
        ad = s.action_data
        if ad.execution_stack:
            COVERAGE[(ad.execution_stack[-1].power_id, ad.execution_stack[-1].phase)] += 1
        elif s.game_phase.value == "activate_powers":
            COVERAGE[(ad.powers_queue[ad.current_power_index].power_id, "queued")] += 1
        for i, action in enumerate(get_actions(s)):
            nxt = copy_state(s)
            nxt.rng = RecordingRandom(s.rng.getstate())
            try:
                transition_state_inplace(nxt, action)
            except Exception as e:  # Rust must reject it too
                try:
                    wingspan_rs.apply(js, i, nxt.rng.log)
                except BaseException:
                    transitions += 1
                    continue
                print(f"seed {seed} step {states}: {action} raises in Python ({e!r}) but not in Rust")
                sys.exit(1)
            try:
                got, unused = wingspan_rs.apply(js, i, nxt.rng.log)
            except BaseException as e:
                print(f"seed {seed} step {states}: {action} in {s.game_phase} fails in Rust: {e!r}")
                print("  state:", js[:3000])
                sys.exit(1)
            want = to_json(nxt)
            if json.loads(got) != want or unused:
                print(f"seed {seed} step {states}: {action} in {s.game_phase} gives a different state")
                print(f"  ({unused} unused chance events)")
                diff(want, json.loads(got))
                sys.exit(1)
            transitions += 1
        while True:  # play on with a move that works (a few legal moves raise in both engines)
            nxt = copy_state(s)
            try:
                transition_state_inplace(nxt, pick.choice(get_actions(s)))
                break
            except Exception:
                pass
        s = nxt
        states += 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 200
    players = int(sys.argv[sys.argv.index("--players") + 1]) if "--players" in sys.argv else 2
    states = transitions = 0
    for seed in range(n):
        a, b = check_game(seed, players)
        states, transitions = states + a, transitions + b
    print(f"OK: {n} games, {states} states, {transitions} transitions identical")
    print("power coverage (states checked):")
    for (pid, phase), k in sorted(COVERAGE.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        print(f"  power {pid:2} {phase:<24} {k}")
    missing = set(range(1, 22)) - {pid for pid, _ in COVERAGE}
    print("templates never reached:", sorted(missing) or "none")
