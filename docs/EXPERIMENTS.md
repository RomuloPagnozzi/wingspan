# What we know

What experiments have established, and what is open. When a finding changes, edit it here; this file is
the current state, not a log.

## How results are measured

Paired comparisons: every arm plays the same deals, each deal twice with the seats swapped, arms
interleaved deal by deal (`lab`, modes `vs_reference` / `paired`). The precise readout is the score
difference averaged per deal over both seats (`lab.summary`, "per-seed diff"): ~300 deals give ±0.7 points
at 95%. Win rate is the coarser second readout. Every run records its decisions, so any result can be
explained afterwards from visits and Q per move.

## Engines

- The Rust engine plays the same game as the Python one: identical legal moves, in the same order, and
  an identical next state for every legal action from every state, over thousands of random games with
  2-4 players, every bird power reached (`rust/py/parity.py`).
- Rust search runs ~30× faster per decision than the Python one did; self-play on 7 workers makes ~7,400
  games/hour with `flat_mc` (Apple M1).
- The Rust flat Monte Carlo estimates moves like the Python one did (same value gaps and move agreement
  on the same positions) and played even with it head to head.

## Search

- **Tuned tree** (`TUNED_TREE` in `src/wingspan/ai/rust.py`, the `mcts_rs` defaults): IS-MCTS, value
  `score_delta`, c ≈ 1.14, widening α ≈ 0.63, k ≈ 1.41, tuned with Optuna at 1500 simulations.
  `score_delta` clearly beat `win_loss` and `absolute_score` (chosen by 55 of 60 trials).
- With those params the tree's root visits concentrate as simulations grow: main turns' top-move share
  0.43 at 1.5k → 0.63 at 30k (0.31 = uniform). Q gap between the best and second move: ~0.85 points in
  main turns, ~0.55 in power activations, under 0.25 in food, egg and payment choices (`rust/py/visits.py`).
- **Flat Monte Carlo** (paired: all moves played in the same re-dealt worlds with the same seeds) does not
  get stronger with 10× the playouts: its limit is the bias of random playouts, not their noise.
- Flat MC's per-phase budgets (`experiments/selfplay.yaml`) play as well as 1500 playouts everywhere, for
  less time.

## Self-play data (`experiments/data/selfplay`: 9.3k games of `flat_mc` vs itself)

- Consistent: unique seeds, seats balanced (first player wins 49.8%), scores sum up, outcomes match
  winners; mean score 73.5, 3.9% ties.
- The random-playout bias shows in the choices: 53% of setups keep a single bird, the "most cards in hand"
  bonus is kept 99% of the time it is dealt, bonus cards with high thresholds are rejected, players end
  with ~7-8 birds. Fine as value targets (game outcomes); weak as policy targets.
- Flat MC splits playouts evenly by design, so its visit counts carry no policy signal: policy targets
  come from Q.

## Open questions

1. Flat MC's value function: the generator uses `absolute_score`, never compared with `score_delta`.
2. How the tuned tree's strength grows with simulations (3k / 10k / 30k) against the generator, and what
   it costs; whether per-phase budgets help the tree.
3. The tree's params at 10k+ simulations (tuned at 1500).
4. Which generator to bootstrap the networks from: flat MC (cheap, biased) or the tree (stronger, ~10×+
   the cost per game).
