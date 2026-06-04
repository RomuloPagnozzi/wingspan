# Inbox

Unprioritized ideas to revisit when relevant. Add freely; nothing leaves until promoted to `BACKLOG.md`. Entries describe the *idea* and *why* it matters — implementation details belong in the backlog spec after promotion.

---

### vs_reference: factorial sweeps

Today the vs_reference framework varies one hyperparameter at a time. Real strength gains often come from interactions (e.g. a higher exploration constant only helps at large sim budgets), and single-parameter sweeps can't see those. The idea is to let a single experiment sweep multiple parameters jointly and analyze the resulting grid, so synergies and conflicts become visible. Until we have a concrete reason to need this, sequential single-parameter runs cover the same ground.

---

### vs_reference: 3+ player games

The paired-comparison methodology currently assumes 2-player matchups. Extending it to 3+ players raises real design questions: how many slots get the reference opponent, how wins are attributed when there are multiple losers, and how to rotate positions cleanly. Worth thinking through only once a concrete multi-player question shows up — Wingspan plays the same rules across player counts so most insights transfer from 2-player work.

---

### Explicit chance nodes

IS-MCTS handles future chance (dice rolls, feeder re-rolls, deck draws under a fresh determinization) by reseeding `state.rng` per simulation — each sim draws one fresh sample of the entire trajectory's chance vector, and Monte Carlo over N sims integrates over the distribution. Mathematically converges to the right answer. The alternative is **explicit chance nodes**: insert a chance node between an action and its stochastic resolution, with children = possible outcomes selected by *probability-weighted sampling* (not UCB — UCB at chance nodes biases value backprop). Advantage: each visit through a chance point samples an outcome independently, so chance-heavy paths converge to true EV faster at low sim counts; IS-MCTS couples all chance events within one sim to a single seed. Cost: identify stochastic transitions in the engine, expose pre-/post-roll boundaries, add progressive widening for large outcome spaces (the feeder roll alone has 7776 outcomes), and a separate selection + weighted-average backprop rule for chance nodes. Substantially more engineering than IS-MCTS for a variance-reduction benefit that may or may not be material. Only worth pursuing if a future experiment shows IS-MCTS reaches stable strength but converges slowly on chance-heavy decisions.

---

### Single-determinization MCTS vs IS-MCTS

Once IS-MCTS lands, a useful follow-up baseline is **single-determinization MCTS**: determinize the hidden state *once* at the root of each MCTS call, then run normal peek-MCTS in that one locked world. This isn't PIMC (no voting across multiple trees) and it isn't IS-MCTS (no per-sim re-determinization). The gap between this and IS-MCTS isolates the value of cross-world statistic merging — i.e. quantifies the cost of strategy fusion *within* a single search. Different and more interesting question than the peek-vs-honest one EXP-006 answers. Only worth running if EXP-006 motivates digging into *why* IS-MCTS wins.

---

### Score-aware rollout policies

MCTS today plays random moves during the rollout phase. Random play is unbiased but very high-variance, so most of the simulation budget goes to estimating noise rather than signal. Two related ideas to fix this. First: bias rollout action choice toward moves that score well immediately (greedy or ε-greedy), which sharpens the value estimate at the same sim count. Second: truncate the rollout after a fixed number of moves and replace the unplayed tail with a cheap heuristic evaluation (e.g. score margin). Truncation is the bigger compute win because each simulation finishes much faster, letting MCTS spend the saved budget on more sims at the root. Among the rollout-side optimizations, this is the highest-expected-ROI lever for raw playing strength.

---

### Action canonicalization

Several game phases — paying egg/food costs, distributing eggs across the board — let the engine enumerate every legal assignment, even when many of those assignments are mechanically indistinguishable (e.g. paying one egg from bird A vs bird B at the same column when no power cares which bird paid). This inflates the branching factor with choices that carry no decision-theoretic content, and MCTS wastes simulations distinguishing them. The idea is to recognize mechanical equivalence per phase, collapse equivalent actions into a single canonical representative before MCTS sees them, and re-expand to a concrete assignment only at apply time if the engine needs it. Expected effect: meaningfully smaller search space → more sims per real choice → strict strength improvement at equal compute. Likely shifts the diminishing-returns threshold on sim-count scaling, so it's worth doing before strength experiments are run on the un-canonicalized engine.

---

### State + action serialization for NN training

The AlphaZero pipeline needs the game state and the action space encoded numerically: state as a fixed-size tensor, actions as indices into a global action space with legal-action masking, and MCTS visit counts as a policy target aligned to those indices. The hard part isn't the encoding mechanics but the *what to encode*: the state tensor must contain only what an honest agent observes. If deck order, opponents' hidden hands, or the RNG state leak in, the NN will learn the cheating patterns that peek-MCTS used to generate the training data, and lose them at inference. Designing this honestly is the structural firewall that determines how much of the offline training signal actually transfers to a real player.

---

### Generate training data for NN

To train a NN from MCTS games we need a stream of (observable state, policy target, value target) tuples. The expensive part is running MCTS to produce visit counts and final outcomes; the cheap part is deriving the observable state at each decision point, which can be reconstructed by replaying the recorded action sequence through the deterministic engine. The idea is to lean on this asymmetry: store the expensive stuff once (action logs, MCTS statistics, outcomes), and reconstruct observable state lazily at training time. The big win is that changing the encoder doesn't require regenerating any games — only re-replay. Prerequisite for the bootstrap experiments and for any NN-based player.

---

### Complexity benchmark for the paper

A standalone characterization of Wingspan's game-tree complexity — average and max branching factor per phase, turn-count distribution, state-space estimates, phase distribution across decisions — measured across player counts. The goal isn't internal use, it's a citation-grade table that positions Wingspan among the other games in the game-AI literature when the paper is written.

---

### EXP-004: first-player advantage quantification

Sanity-check on the magnitude of first-player advantage in 2-player games. The paired-comparison harness already neutralizes FPA via position swapping for every other experiment, so this is a standalone measurement, not a dependency. See `EXPERIMENTS.md`.

---

### EXP-006: peek-MCTS vs PIMC determinization

Measures the "cheat tax" — how much weaker MCTS becomes once it can no longer see hidden information. The outcome decides whether the project's reference opponent stays as peek-MCTS or switches to honest PIMC, which in turn affects whether any prior strength numbers are still comparable. See `EXPERIMENTS.md`.

---

### EXP-001, EXP-002, EXP-003, EXP-005, EXP-007

Strength-sensitive sweeps over simulation budget, exploration constant, value function, selection policy, and rollout policy — all evaluated against the same fixed reference so the results can be stacked into a single ablation table. Should only run after the reference is finalized. See `EXPERIMENTS.md`.

---

### EXP-008: bootstrap data quality for NN training

Tests whether a NN trained on MCTS-generated games inherits the biases of the data-generating MCTS, and how much that matters for downstream self-play. Depends on PIMC, the NN encoder, and the training-data pipeline being in place. See `EXPERIMENTS.md`.

---

### EXP-009: bootstrap vs from-scratch self-play

Compares starting NN self-play from MCTS-bootstrapped weights versus from scratch — the question of whether the bootstrap is a real shortcut or a local-minimum trap. Follow-up to EXP-008. See `EXPERIMENTS.md`.
