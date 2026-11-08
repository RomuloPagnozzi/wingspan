# wingspan_rs

A Rust port of the game engine and its searches, next to the Python one. The Python engine stays the
reference: every rule ported here is checked against it, state by state.

Status: all rules including the 21 bird power templates, redeterminize, flat Monte Carlo and IS-MCTS.

```bash
# build + install into the project venv (redo after Rust changes, or after `uv sync`, which removes it)
VIRTUAL_ENV=../.venv uvx maturin develop --release --uv
```

## Using it

The Python package picks the extension up when it is installed: `wingspan.ai.rust` registers two
strategies, used in YAML configs and tuning like any other.

| Strategy | What it is |
|---|---|
| `flat_mc_rs` | `flat_mc` with its playouts in Rust (same `FlatMCConfig`, same decision rule) |
| `mcts_rs` | `mcts` IS-MCTS (`determinize: true`) with its search in Rust (same `MCTSConfig`), plus `phase_simulations` (per-phase budgets) |

The game itself is still played by the Python engine; Rust only searches. So recorded games replay in
Python as before. Experiments: `experiments/tree_scaling.yaml`, `experiments/tree_vs_flat.yaml`,
`experiments/flat_mc_rs_vs_flat_mc.yaml` (Rust vs Python strength), `experiments/selfplay_flat_mc_rs.yaml`
(self-play data); see `experiments/README.md`.

## Dev tools (`py/`)

```bash
uv run python rust/py/parity.py 300              # every legal action from every state of 300 games must match
uv run python rust/py/parity.py 300 --players 4  # pink powers depend on seating
uv run python rust/py/bench.py                   # Python vs Rust random-play speed, same rules
uv run python rust/py/strength.py                # flat_mc_rs estimates like flat_mc? (same positions)
uv run python rust/py/mcts_check.py              # mcts_rs searches like mcts? (same positions)
uv run python rust/py/visits.py                  # root visit / Q distributions vs simulations
uv run python rust/py/export_data.py             # regenerate data/*.json if the card pickles change
cargo test --release                             # Rust-only tests (redeterminize, flat MC)
cargo run --release --bin bench [random|flatmc|ismcts|phases]   # pure Rust speed
```

Parity without a shared RNG: the rules draw randomness only through `chance::Chance` (die rolls, shuffles).
`parity.py` records what Python drew and Rust replays those outcomes; real runs use Rust's own fast RNG.
The state the engines exchange is `wingspan.ai.rust.to_json` (Python) / `src/state.rs` (Rust).

Layout: `state.rs` (state, its JSON), `actions.rs` (action strings), `rules.rs` (setup, actions, transitions,
scoring, power queue), `powers.rs` (power triggers, validators, choices, handlers), `search.rs`
(redeterminize, flat MC, IS-MCTS), `chance.rs`, `data.rs` (cards), `lib.rs` (Python bindings).
