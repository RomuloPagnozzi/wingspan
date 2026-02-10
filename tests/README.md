# tests

Pytest suite covering the full game engine.

## Running

```bash
uv run pytest tests/
```

## Files

| File | Covers |
|------|--------|
| `conftest.py` | shared fixtures and helpers |
| `test_engine.py` | game loop and state transitions |
| `test_effects.py` | atomic state mutations |
| `test_reproducibility.py` | deterministic seeded games |
| `test_round_goals.py` | round goal scoring |
| `powers/` | one test file per bird power (1-21) |
