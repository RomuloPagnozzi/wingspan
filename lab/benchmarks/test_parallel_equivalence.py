"""Verify that game-level parallelism produces byte-identical per-game results.

Runs the same paired config twice — once with num_workers=1 (sequential),
once with num_workers=2 (spawn pool) — and asserts that each (game_idx)
slot yields the same scores, winner, and decision count regardless of
which worker process executed it.

Slow (full games × 2 paths). Lives in lab/benchmarks/, not tests/.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.__main__ import _iter_results, _work_iter
from lab.generators import get_generator


def _run(config: dict, num_workers: int):
    """Run the experiment driver returning a {game_idx: result_summary} map."""
    generator = get_generator(config)
    # count_games is large enough to not be the limiting factor; the generator
    # exhausts naturally for paired/vs_reference.
    work = _work_iter(generator, total_games=None, record_decisions=False)

    out = {}
    for result, _decisions, game_idx in _iter_results(work, num_workers):
        out[game_idx] = (
            tuple(p.total_score for p in result.players),
            tuple(p.is_winner for p in result.players),
            result.total_decisions,
        )
    return out


def _config(determinize: bool) -> dict:
    """A tiny paired config: 1 pair × 2 seeds × 2 positions = 4 games at 20 sims."""
    return {
        "mode": "paired",
        "base": {
            "strategy": "mcts",
            "simulations": 20,
            "exploration_constant": 1.41,
            "value_function": "score_delta",
            "determinize": determinize,
        },
        "compare": {
            "parameter": "exploration_constant",
            "values": [1.0, 1.41],
        },
        "seeds": {"count": 2, "start": 1},
    }


def test_parallel_equivalence_peek():
    config = _config(determinize=False)
    sequential = _run(config, num_workers=1)
    parallel = _run(config, num_workers=2)
    assert sequential.keys() == parallel.keys()
    for game_idx, expected in sequential.items():
        assert parallel[game_idx] == expected, (
            f"Game {game_idx} diverged:\n"
            f"  sequential: {expected}\n  parallel:   {parallel[game_idx]}"
        )


def test_parallel_equivalence_ismcts():
    config = _config(determinize=True)
    sequential = _run(config, num_workers=1)
    parallel = _run(config, num_workers=2)
    assert sequential.keys() == parallel.keys()
    for game_idx, expected in sequential.items():
        assert parallel[game_idx] == expected, (
            f"Game {game_idx} diverged:\n"
            f"  sequential: {expected}\n  parallel:   {parallel[game_idx]}"
        )


if __name__ == "__main__":
    print("Running peek equivalence check...")
    test_parallel_equivalence_peek()
    print("  ✓ peek: sequential == parallel")
    print("Running IS-MCTS equivalence check...")
    test_parallel_equivalence_ismcts()
    print("  ✓ ismcts: sequential == parallel")
