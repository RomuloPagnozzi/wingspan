"""Parity of the Rust encodings (`wingspan_rs.encode_obs`, `encode_actions`) against wingspan.ai.encoding.

At every state of many random Python games, every viewer's observation and every legal move's encoding and
bird ids must match (up to float32 rounding). Stops at the first mismatch and prints the differing columns
by name.

    uv run python rust/py/encoding_parity.py [n_games]
"""

import random
import sys

import numpy as np
import wingspan_rs

from wingspan.ai.encoding import (
    action_bird_ids,
    action_feature_names,
    encode_action,
    encode_obs,
    player_feature_names,
    shared_feature_names,
)
from wingspan.ai.rust import state_json
from wingspan.engine.actions import get_actions
from wingspan.engine.core import ScoringMode, initiate_state
from wingspan.engine.engine import transition_state


def names(n_players: int) -> list[str]:
    p = player_feature_names()
    return [f"me.{x}" for x in p] + [f"opp{i}.{x}" for i in range(1, n_players) for x in p] + list(shared_feature_names())


def check_game(seed: int, n_players: int) -> tuple[int, int]:
    mode = ScoringMode.BLUE if seed % 5 == 0 else ScoringMode.GREEN
    s, pick, checked, moves = initiate_state(n_players, mode, seed=seed), random.Random(seed), 0, 0
    while actions := get_actions(s):
        js = state_json(s)
        for viewer in range(n_players):
            py = np.array(encode_obs(s, viewer).flat(), np.float32)
            rs = np.array(wingspan_rs.encode_obs(js, viewer), np.float32)
            bad = np.flatnonzero(~np.isclose(py, rs, atol=1e-6)) if len(py) == len(rs) else None
            if bad is None or len(bad):
                print(f"seed {seed}, phase {s.game_phase.value}, round {s.round}, viewer {viewer}: MISMATCH")
                if bad is None:
                    print(f"  length python={len(py)} rust={len(rs)}")
                for i in bad[:20] if bad is not None else ():
                    print(f"  {names(n_players)[i]}: python={py[i]:.6f} rust={rs[i]:.6f}")
                sys.exit(1)
            checked += 1
        for action, (rs, birds) in zip(actions, wingspan_rs.encode_actions(js), strict=True):
            py = np.array(encode_action(s, action), np.float32)
            bad = np.flatnonzero(~np.isclose(py, np.array(rs, np.float32), atol=1e-6))
            if len(bad) or list(birds) != action_bird_ids(action):
                print(f"seed {seed}, phase {s.game_phase.value}, {action}: MISMATCH")
                print(f"  birds python={action_bird_ids(action)} rust={birds}")
                for i in bad[:20]:
                    print(f"  {action_feature_names()[i]}: python={py[i]:.6f} rust={rs[i]:.6f}")
                sys.exit(1)
            moves += 1
        s = transition_state(s, pick.choice(actions))
    return checked, moves


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    total, moves = map(sum, zip(*(check_game(seed, 2 + seed % 3) for seed in range(n))))
    print(f"OK: {total:,} observations and {moves:,} moves identical over {n} games (2-4 players)")
