# wingspan_rs

A Rust port of the game engine, developed next to the Python one without touching it. The Python engine stays
the reference: every rule ported here is checked against it, state by state.

Status (M1): all rules except bird powers. Python with powers patched out (`py/nopowers.py`, in-process
only) plays exactly the same rules, which is what the parity test and the benchmark compare against.

```bash
# build + install into the project venv (redo after Rust changes, or after `uv sync`, which removes it)
VIRTUAL_ENV=../.venv uvx maturin develop --release --uv

uv run python rust/py/parity.py 200   # every legal action from every state of 200 games must match
uv run python rust/py/bench.py        # Python vs Rust random-play speed, same rules
cargo run --release --bin bench       # pure Rust speed
uv run python rust/py/export_data.py  # regenerate data/*.json if the card pickles change
```

Parity without a shared RNG: the rules draw randomness only through `chance::Chance` (die rolls, shuffles).
The test records what Python drew (`pystate.RecordingRandom`) and Rust replays those outcomes; real runs use
Rust's own fast RNG.
