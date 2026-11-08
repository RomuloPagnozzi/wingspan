# wingspan_rs

A Rust port of the game engine, developed next to the Python one without touching it. The Python engine stays
the reference: every rule ported here is checked against it, state by state.

Status: all rules including the 21 bird power templates (M2), plus redeterminize and flat Monte Carlo (M3).

```bash
# build + install into the project venv (redo after Rust changes, or after `uv sync`, which removes it)
VIRTUAL_ENV=../.venv uvx maturin develop --release --uv

uv run python rust/py/parity.py 300              # every legal action from every state of 300 games must match
uv run python rust/py/parity.py 300 --players 4  # pink powers depend on seating
uv run python rust/py/bench.py                   # Python vs Rust random-play speed
uv run python rust/py/selfplay_bench.py          # seconds per self-play game, flat_mc vs flat_mc_rs
cargo test --release                             # Rust-only tests (redeterminize, flat MC)
cargo run --release --bin bench                  # pure Rust speed
uv run python rust/py/export_data.py             # regenerate data/*.json if the card pickles change
```

Parity without a shared RNG: the rules draw randomness only through `chance::Chance` (die rolls, shuffles).
The test records what Python drew (`pystate.RecordingRandom`) and Rust replays those outcomes; real runs use
Rust's own fast RNG.

`py/flat_mc_rs.py` is the `flat_mc` strategy with its playouts in Rust (one call per decision). The game
itself is still played by the Python engine, so recorded games replay in Python as before.

Layout: `state.rs` (state, its JSON), `actions.rs` (action strings), `rules.rs` (setup, actions, transitions,
scoring, power queue), `powers.rs` (power triggers, validators, choices, handlers), `search.rs`
(redeterminize, flat MC), `chance.rs`, `data.rs` (cards), `lib.rs` (Python bindings).
