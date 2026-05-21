"""Test that identical seeds produce identical MCTS behavior.

Has two regimes:

1. Same-process determinism — runs two games back-to-back in this process.
   Fails if `random.Random(seed)` plumbing is broken, but cannot detect
   hash-seed-sensitive iteration because PYTHONHASHSEED is constant within
   a single process.

2. Cross-process determinism — re-launches this file as a subprocess with
   several distinct `PYTHONHASHSEED` values and compares the move streams,
   across multiple `(game_seed, num_workers)` configurations. Catches:
     - hidden `set()` / `dict[str, …]` iteration leaks (varies hashseed),
     - per-worker hash-seed drift in parallel MCTS (varies num_workers),
     - power code paths exercised only on certain seeds (varies game_seed).
   Required for paired-comparison validity when `num_workers > 1` (each
   MCTS worker is a separate spawned interpreter).
"""

import itertools
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from game.core import initiate_state
from game.actions import get_actions
from game.engine import transition_state
from lab.strategies import create_strategy, MCTSStrategy


def play_game(
    game_seed: int,
    mcts_seed: int,
    simulations: int,
    exploration_constant: float,
    num_workers: int = 1,
    determinize: bool = False,
):
    """Play a full game and return (moves_made, final_scores)."""
    strategy = create_strategy(
        "mcts",
        simulations=simulations,
        exploration_constant=exploration_constant,
        num_workers=num_workers,
        seed=mcts_seed,
        determinize=determinize,
    )

    state = initiate_state(2, seed=game_seed)
    moves: list = []

    assert isinstance(strategy, MCTSStrategy)
    with strategy:
        while actions := get_actions(state):
            action = strategy.select_action(state, actions)
            moves.append(action)
            state = transition_state(state, action)

    scores = [p.score.total for p in state.players]
    return moves, scores


# =============================================================================
# Same-process test
# =============================================================================


def test_same_process() -> bool:
    print("Testing MCTS determinism with identical seeds (same process)...\n")

    game_seed = 42
    mcts_seed = 123
    simulations = 100
    exploration_constant = 1.41

    ok = True
    for determinize in (False, True):
        label = "ismcts" if determinize else "peek"
        print(
            f"\n[{label}] Parameters: game_seed={game_seed}, mcts_seed={mcts_seed}, "
            f"sims={simulations}, c={exploration_constant}, num_workers=1"
        )

        print(f"  Run 1...")
        moves1, scores1 = play_game(
            game_seed,
            mcts_seed,
            simulations,
            exploration_constant,
            determinize=determinize,
        )
        print(f"  Run 2...")
        moves2, scores2 = play_game(
            game_seed,
            mcts_seed,
            simulations,
            exploration_constant,
            determinize=determinize,
        )

        print(f"  Run 1: {len(moves1)} moves, scores={scores1}")
        print(f"  Run 2: {len(moves2)} moves, scores={scores2}")

        if moves1 == moves2:
            print(f"  ✓ IDENTICAL [{label}]: Same moves in same order")
        else:
            print(f"  ✗ DIFFERENT [{label}]: Moves diverged!")
            for i, (m1, m2) in enumerate(zip(moves1, moves2)):
                if m1 != m2:
                    print(f"    First difference at move {i}: '{m1}' vs '{m2}'")
                    break
            ok = False

    print("\n" + "-" * 60)
    print("Testing that different MCTS seed produces different behavior...")

    moves_a, _ = play_game(
        game_seed, mcts_seed, simulations, exploration_constant, determinize=False
    )
    moves_b, _ = play_game(
        game_seed, mcts_seed + 1, simulations, exploration_constant, determinize=False
    )
    if moves_a != moves_b:
        print("✓ EXPECTED: Different MCTS seed → different moves")
    else:
        print(
            "? UNEXPECTED: Same moves despite different MCTS seed (could happen by chance)"
        )

    return ok


# =============================================================================
# Cross-process test (PYTHONHASHSEED × game_seed × num_workers)
# =============================================================================

_CHILD_BEGIN = "===CHILD_BEGIN==="
_CHILD_END = "===CHILD_END==="


def _child_run(
    game_seed: int,
    mcts_seed: int,
    simulations: int,
    c: float,
    num_workers: int,
    determinize: bool,
) -> None:
    """Subprocess entry point. Prints moves and scores between markers."""
    moves, scores = play_game(
        game_seed, mcts_seed, simulations, c, num_workers, determinize
    )
    print(_CHILD_BEGIN)
    for m in moves:
        print(repr(m))
    print(f"SCORES={scores}")
    print(_CHILD_END)


def _run_subprocess(
    hashseed: str,
    game_seed: int,
    mcts_seed: int,
    simulations: int,
    c: float,
    num_workers: int,
    determinize: bool,
) -> tuple[list[str], str]:
    """Re-launch this file with PYTHONHASHSEED=hashseed and capture moves+scores."""
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        str(game_seed),
        str(mcts_seed),
        str(simulations),
        str(c),
        str(num_workers),
        str(int(determinize)),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=REPO_ROOT, check=True
    )
    lines = result.stdout.splitlines()
    try:
        start = lines.index(_CHILD_BEGIN) + 1
        end = lines.index(_CHILD_END)
    except ValueError:
        raise RuntimeError(
            f"Child output malformed for PYTHONHASHSEED={hashseed}, "
            f"game_seed={game_seed}, num_workers={num_workers}:\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    payload = lines[start:end]
    scores_line = payload[-1]
    moves = payload[:-1]
    return moves, scores_line


def _compare_results(
    results: list[tuple[str, list[str], str]],
) -> bool:
    """Compare a list of (hashseed, moves, scores) tuples to the first one."""
    baseline_hs, baseline_moves, baseline_scores = results[0]
    all_match = True
    for hs, moves, scores in results[1:]:
        moves_match = moves == baseline_moves
        scores_match = scores == baseline_scores
        if moves_match and scores_match:
            print(f"    ✓ PYTHONHASHSEED={hs}  matches baseline (={baseline_hs})")
        else:
            all_match = False
            print(f"    ✗ PYTHONHASHSEED={hs}  DIVERGED from baseline (={baseline_hs})")
            if not scores_match:
                print(f"        baseline scores: {baseline_scores}")
                print(f"        this run scores: {scores}")
            if not moves_match:
                for i, (a, b) in enumerate(zip(baseline_moves, moves)):
                    if a != b:
                        print(f"        first divergence at move idx {i}:")
                        print(f"          baseline: {a}")
                        print(f"          this run: {b}")
                        break
                if len(baseline_moves) != len(moves):
                    print(
                        f"        move counts differ: baseline={len(baseline_moves)}, "
                        f"this run={len(moves)}"
                    )
    return all_match


def test_cross_process(
    hashseeds: list[str] | None = None,
    game_seeds: list[int] | None = None,
    worker_counts: list[int] | None = None,
    determinize_values: list[bool] | None = None,
    simulations: int = 100,
    exploration_constant: float = 1.41,
    mcts_seed: int = 123,
) -> bool:
    """Sweep (game_seed × num_workers × determinize × PYTHONHASHSEED). Identical
    (game_seed, num_workers, determinize) must produce identical moves across all
    PYTHONHASHSEED values."""
    if hashseeds is None:
        hashseeds = ["0", "1", "random"]
    if game_seeds is None:
        game_seeds = [1, 42, 999]
    if worker_counts is None:
        worker_counts = [1, 2]
    if determinize_values is None:
        determinize_values = [False, True]

    n_configs = len(game_seeds) * len(worker_counts) * len(determinize_values)
    n_runs = n_configs * len(hashseeds)

    print("\n" + "=" * 60)
    print("Testing cross-process determinism (PYTHONHASHSEED sweep)...")
    print("=" * 60)
    print(f"  game_seeds:   {game_seeds}")
    print(f"  num_workers:  {worker_counts}")
    print(f"  determinize:  {determinize_values}")
    print(f"  hashseeds:    {hashseeds}")
    print(
        f"  simulations:  {simulations}    (MCTS seed: {mcts_seed}, c: {exploration_constant})"
    )
    print(
        f"  total subprocess runs: {n_runs}  ({n_configs} configs × {len(hashseeds)} hashseeds)\n"
    )

    overall_ok = True
    config_idx = 0
    for game_seed, num_workers, determinize in itertools.product(
        game_seeds, worker_counts, determinize_values
    ):
        config_idx += 1
        print(
            f"[config {config_idx}/{n_configs}] "
            f"game_seed={game_seed}, num_workers={num_workers}, "
            f"determinize={determinize}"
        )

        results: list[tuple[str, list[str], str]] = []
        for hs in hashseeds:
            moves, scores = _run_subprocess(
                hs,
                game_seed,
                mcts_seed,
                simulations,
                exploration_constant,
                num_workers,
                determinize,
            )
            print(f"    PYTHONHASHSEED={hs:>6}  →  {len(moves)} moves, {scores}")
            results.append((hs, moves, scores))

        config_ok = _compare_results(results)
        if not config_ok:
            overall_ok = False
        print()

    print("=" * 60)
    if overall_ok:
        print(
            "✓ Cross-process determinism HOLDS across every (game_seed, num_workers, hashseed)."
        )
    else:
        print(
            "✗ Cross-process determinism BROKEN in at least one configuration.\n"
            "  Iteration order of a string-hashing set/dict is leaking into game logic\n"
            "  or per-worker behavior. See divergence details above."
        )
    return overall_ok


# =============================================================================
# Entry point
# =============================================================================


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _, _, game_seed, mcts_seed, simulations, c, num_workers, determinize = sys.argv
        _child_run(
            int(game_seed),
            int(mcts_seed),
            int(simulations),
            float(c),
            int(num_workers),
            bool(int(determinize)),
        )
        return

    same_ok = test_same_process()
    cross_ok = test_cross_process()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Same-process:  {'PASS' if same_ok else 'FAIL'}")
    print(f"Cross-process: {'PASS' if cross_ok else 'FAIL'}")

    sys.exit(0 if (same_ok and cross_ok) else 1)


if __name__ == "__main__":
    main()
