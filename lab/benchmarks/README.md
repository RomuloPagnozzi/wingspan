# lab/benchmarks

Performance benchmarks and determinism checks. Standalone scripts, not part of pytest.

## Files

| File | Role |
|------|------|
| `benchmark_copy.py` | times full random games using `copy_state` vs `deepcopy` |
| `benchmark_mcts.py` | times MCTS move selection at varying simulation counts |
| `profile_game.py` | plays one MCTS game for use under pyinstrument |
| `test_determinism.py` | asserts fixed seeds reproduce identical MCTS moves and scores |
| `benchmark_ismcts.py` | times IS-MCTS/PIMC move selection against peek-MCTS |
| `test_ismcts.py` | correctness checks on redeterminization (hidden state reshuffling) |
| `test_parallel_equivalence.py` | asserts worker count does not change results |

## Dependencies

```
benchmark_copy.py   <- wingspan.engine.core, wingspan.engine.actions, wingspan.engine.engine, wingspan.engine.phase_handlers
benchmark_mcts.py   <- wingspan.engine.*, wingspan.ai
profile_game.py     <- wingspan.engine.*, wingspan.ai
test_determinism.py <- wingspan.engine.*, wingspan.ai
benchmark_ismcts.py <- wingspan.engine.*, wingspan.ai
test_ismcts.py      <- wingspan.engine.*, wingspan.ai
test_parallel_equivalence.py <- wingspan.engine.*, wingspan.ai
```

## Usage

```bash
uv run python lab/benchmarks/benchmark_copy.py
uv run python lab/benchmarks/benchmark_mcts.py
uv run python lab/benchmarks/test_determinism.py

# Profile one MCTS game
uv run python -m pyinstrument lab/benchmarks/profile_game.py
```
