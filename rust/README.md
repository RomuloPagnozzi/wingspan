# wingspan_rs

The game engine and its searches in Rust, used by the Python package as `wingspan_rs` (`uv sync` builds
it; it rebuilds when the sources or the card data change). The Python engine stays the reference: every
rule here is checked against it, state by state.

`wingspan.ai.rust` registers the strategy that uses it: `mcts_rs`, IS-MCTS with the tuned params as defaults
and per-phase budgets (`phase_simulations`).

The game itself is played by the Python engine; Rust only searches, so recorded games replay in Python.
Card data: `src/wingspan/engine/assets/*.json`, shared with the Python engine.

```bash
uv run python rust/py/parity.py 300              # every legal action from every state of 300 games must match
uv run python rust/py/parity.py 300 --players 4  # pink powers depend on seating
uv run python rust/py/visits.py                  # root visit / Q distributions of the tree vs simulations
cargo test --release                             # Rust tests
cargo run --release --bin bench [random|ismcts|phases]   # speed (ismcts prints a checksum: unchanged by a pure optimization)
```

Parity without a shared RNG: the rules draw randomness only through `chance::Chance` (die rolls, shuffles).
`parity.py` records what Python drew and Rust replays those outcomes; real runs use Rust's own RNG. The
state the engines exchange: `wingspan.ai.rust.to_json` (Python) / `src/state.rs` (Rust).

Layout: `state.rs` (state, its JSON), `actions.rs` (action strings), `rules.rs` (setup, actions, transitions,
scoring, power queue), `powers.rs` (power triggers, validators, choices, handlers), `search.rs`
(redeterminize, IS-MCTS), `chance.rs`, `data.rs` (cards), `lib.rs` (Python bindings).
