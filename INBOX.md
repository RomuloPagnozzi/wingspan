# Inbox

Unprioritized ideas to revisit when relevant. Add freely. Entries describe the *idea* and *why* it matters; an idea graduates by becoming an experiment in `EXPERIMENTS.md`, where the implementation detail belongs.

---

### Rollout truncation + heuristic eval

**Status: not implemented.**

By far the highest-ROI lever on IS-MCTS wall clock. Random rollouts to terminal are mostly wasted compute — the late-game tail adds noise, not signal. Two compounding wins: truncate at fixed depth and substitute a cheap eval (current score delta is a strong baseline; NN value head later); separately, bias action choice toward immediately-scoring moves to sharpen the estimate at equal sims. Truncation is the bigger compute win and the cleaner experiment.

---

### Engine refactor toward SoA-hybrid tensor state

**Status: not implemented.**

Bigger structural rewrite of `game/` away from `dataclass`/`Spot`-per-cell Python objects toward a struct-of-arrays tensor backbone (`board_bird_id[P,3,5]`, `hand_mask[P,N_CARDS]`, food/scores as small int arrays, decks as int16 arrays) plus a thin Python sidecar for irregular state (power execution stack, end-turn effects, action_data). Mutate tensor parts in-place with an `(field, index, old_value)` undo log; sidecar copy-on-write since it's small.

The real wins are three orthogonal ones:

- **Bitset redeterminize.** Currently a measurable share of IS-MCTS budget; with a `hand_mask` bitset over all cards, "what's still unknown" becomes one XOR.
- **NN-ready state.** Stacked arrays *are* the observation tensor. No separate featurizer to build, debug, or keep in sync with the engine.
- **Vectorized action masks.** Legal-play-bird mask = `(hand_mask & habitat_match[habitat] & cost_payable_mask)`. Required for any NN policy head; replaces nested Python loops in `game/utils.py`.

Order: do **rollout truncation first** — it changes the cost mix and may make this less urgent. Do the **NN encoder/value head before this** if possible (the rewrite is much more painful without a clear NN spec to target).

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

### vs_reference: factorial sweeps

Today the vs_reference framework varies one hyperparameter at a time. Real strength gains often come from interactions (e.g. a higher exploration constant only helps at large sim budgets), and single-parameter sweeps can't see those. The idea is to let a single experiment sweep multiple parameters jointly and analyze the resulting grid, so synergies and conflicts become visible. Until we have a concrete reason to need this, sequential single-parameter runs cover the same ground.

---

### vs_reference: 3+ player games

The paired-comparison methodology currently assumes 2-player matchups. Extending it to 3+ players raises real design questions: how many slots get the reference opponent, how wins are attributed when there are multiple losers, and how to rotate positions cleanly. Worth thinking through only once a concrete multi-player question shows up — Wingspan plays the same rules across player counts so most insights transfer from 2-player work.

---

### Explicit chance nodes

IS-MCTS handles future chance (dice rolls, feeder re-rolls, deck draws under a fresh determinization) by reseeding `state.rng` per simulation — each sim draws one fresh sample of the entire trajectory's chance vector, and Monte Carlo over N sims integrates over the distribution. Mathematically converges to the right answer. The alternative is **explicit chance nodes**: insert a chance node between an action and its stochastic resolution, with children = possible outcomes selected by *probability-weighted sampling* (not UCB — UCB at chance nodes biases value backprop). Substantially more engineering than IS-MCTS for a variance-reduction benefit that may or may not be material. Only worth pursuing if a future experiment shows IS-MCTS reaches stable strength but converges slowly on chance-heavy decisions.

---

### Single-determinization MCTS vs IS-MCTS

A useful follow-up baseline: determinize the hidden state *once* at the root of each MCTS call, then run normal peek-MCTS in that one locked world. This isn't PIMC (no voting across multiple trees) and it isn't IS-MCTS (no per-sim re-determinization). The gap between this and IS-MCTS isolates the value of cross-world statistic merging — i.e. quantifies the cost of strategy fusion *within* a single search. Only worth running if we want to dig into *why* IS-MCTS performs as it does.

---

### Action canonicalization

Several game phases — paying egg/food costs, distributing eggs across the board — let the engine enumerate every legal assignment, even when many of those assignments are mechanically indistinguishable (e.g. paying one egg from bird A vs bird B at the same column when no power cares which bird paid). This inflates the branching factor with choices that carry no decision-theoretic content, and MCTS wastes simulations distinguishing them. The idea is to recognize mechanical equivalence per phase, collapse equivalent actions into a single canonical representative before MCTS sees them, and re-expand to a concrete assignment only at apply time if the engine needs it. Likely shifts the diminishing-returns threshold on sim-count scaling, so it's worth doing before strength experiments are run on the un-canonicalized engine.
