# Wingspan MCTS Experiments

## Research Philosophy

**Core insight:** Most MCTS research relies on massive compute (millions of games). Our contribution is finding the most efficient experimental design to reach statistically significant conclusions with comparatively low game counts.

**Approach: Maximally controlled paired comparisons**

We exploit two sources of randomness that can be controlled:
1. **Game seed** - controls initial hands, bird tray, dice rolls, etc.
2. **MCTS seed** - controls tree exploration order, rollout action choices

By fixing both seeds, we eliminate variance from everything except the hyperparameter we're testing. This dramatically reduces the number of games needed for statistical significance.

**Verified:** With identical (game_seed, mcts_seed, simulations, exploration_constant, value_function), MCTS produces identical moves and trees (see `test_determinism.py`).

**Paired experiment design:**
```
For each game_seed G:
  For each mcts_seed M:
    Run: P1(param=A, seed=M) vs P2(param=B, seed=M) on game G
    Run: P1(param=B, seed=M) vs P2(param=A, seed=M) on game G  # position swap
```
Position swapping controls for first-player advantage. Same MCTS seed ensures the only variable is the parameter being tested.

**Statistical methods:**
- Paired comparisons → McNemar's test (not binomial CI)
- Estimate: 50-100 paired games can detect differences that would need 400+ unpaired games

## Hypotheses & Goals

- **H1:** Higher simulation counts yield diminishing returns beyond a threshold
- **H2:** Default exploration constant (√2 ≈ 1.41) is suboptimal for Wingspan
- **H3:** Value function choice (score_delta vs win_loss vs absolute_score) affects play style and win rate
- **H4:** Current MCTS implicitly exploits hidden information (deck order, dice via seeded `rng`, opponent hands) through `transition_state` determinism. A determinized variant (PIMC) that reshuffles unknowns per simulation will play measurably differently, and the gap quantifies how much current MCTS strength comes from peek vs honest planning.
- **H5:** Replacing uniform-random rollouts with score-aware rollouts (ε-greedy on score delta, or K-step + heuristic with early termination) beats random rollouts at fixed simulation budget by a margin larger than 2× sim count — i.e., it's a strictly better use of compute than throwing more sims at random rollouts.
- **H6:** At fixed total compute, an NN bootstrapped from biased-but-strong (peek-MCTS) self-play games matches or beats an NN bootstrapped from clean-but-weaker (PIMC) games, before iterative self-play washes out the bias. If true, dirty bootstrap data is a compute-efficient shortcut in low-compute regimes — the central question for the paper.
- **H7:** At our compute scale, an NN warm-started from MCTS-generated bootstrap data reaches a target strength level (e.g., beating reference MCTS at ≥55% win rate) using strictly less total compute than an NN trained from random init via pure self-play. AlphaZero showed bootstrap is *unnecessary* at massive compute; we expect it is *load-bearing* at our scale. Quantifying the speedup — and the crossover point where pure self-play catches up — is part of the compute-efficiency frontier the paper characterizes.
- **Goal:** Find optimal MCTS configuration for competitive 2-player and 3-player games, and characterize the compute-efficiency frontier for NN bootstrap strategies.

## Experiment Queue

### EXP-001: Simulation budget scaling
**Status:** pending
**Hypothesis:** Win rate advantage of higher sims plateaus around 1000-1500
**Config:**
```yaml
matchups:
  - [mcts:500, mcts:1000]
  - [mcts:1000, mcts:1500]
  - [mcts:1500, mcts:2000]
```
**Games:** 500 per matchup
**Reasoning:** Establish baseline scaling curve before tuning other params. Need to know where diminishing returns kick in.

---

### EXP-002: Exploration constant coarse sweep
**Status:** pending
**Hypothesis:** Optimal c is game-specific; Wingspan's moderate branching may favor c < √2
**Config:**
```yaml
defaults:
  simulations: 500
matchups:
  - [c=0.5, c=1.0]
  - [c=1.0, c=1.41]
  - [c=1.41, c=2.0]
```
**Games:** 200 per matchup (fixed seeds for paired comparison)
**Reasoning:** Literature shows c is the most impactful hyperparameter. Coarse sweep first, then refine.
**Depends on:** EXP-001 (to pick appropriate simulation count)

---

### EXP-003: Value function comparison
**Status:** pending
**Hypothesis:** score_delta outperforms win_loss due to richer signal
**Config:**
```yaml
defaults:
  simulations: 500
matchups:
  - [vf=score_delta, vf=win_loss]
  - [vf=score_delta, vf=absolute_score]
```
**Games:** 300 per matchup
**Reasoning:** Different value functions encode different objectives. Score delta encourages winning by large margins; win_loss only cares about winning.

---

### EXP-004: First player advantage quantification
**Status:** pending
**Hypothesis:** First player has measurable advantage (estimated 3-5%)
**Config:** mcts:500 vs mcts:500 (symmetric)
**Games:** 1000
**Analysis:** Compare win rates by first_player flag
**Reasoning:** Need to control for this in all other experiments

---

### EXP-005: Selection policy comparison
**Status:** pending
**Hypothesis:** Alternative selection policies (UCB1-Tuned, PUCT) may outperform standard UCB1 for Wingspan's branching structure
**Design idea:** Abstract the selection policy behind a protocol (e.g., `SelectionPolicy` with a `score(node, parent_visits) -> float` method) so `_select` becomes policy-agnostic. This enables clean A/B testing of:
- **UCB1** (current) - classic exploration bonus
- **UCB1-Tuned** - adds variance estimate for tighter bounds
- **PUCT** - prior-weighted exploration (used by AlphaZero); could incorporate hand-crafted or learned priors
- **Thompson Sampling** - Bayesian approach, samples from posterior
**Depends on:** EXP-001, EXP-002 (establish baseline with UCB1 first)
**Reasoning:** In MCTS literature, the selection policy (also called tree policy) governs how the already-built tree is traversed. Different policies trade off exploration vs exploitation differently, and the optimal choice is game-dependent.

---

### EXP-006: Peek-MCTS vs PIMC (determinization)
**Status:** pending
**Hypothesis (H4):** Current MCTS implicitly exploits hidden info via `transition_state` determinism. PIMC (re-shuffle `bird_deck` / `bonus_deck` / opponent hidden hands and re-seed `state.rng` per simulation) plays measurably differently. The strength gap *in honest evaluation* is the cheat tax.
**Config:** mcts:500 (peek) vs mcts:500 (PIMC), with eval performed under PIMC for both (honest play conditions).
**Games:** 200 per matchup (paired). Run at both `num_workers=1` and `num_workers=2`.
**Depends on:** PIMC implementation in `game/` (see TODO).
**Reasoning:** Quantifies how much of current MCTS's strength comes from exploiting engine-level observability that a real agent wouldn't have. Critical input to H6 — if peek's advantage is small, the bootstrap-data question becomes moot.

---

### EXP-007: Rollout policy comparison
**Status:** pending
**Hypothesis (H5):** Score-aware rollouts beat random rollouts at fixed sim budget by more than 2× sim count.
**Config:**
```yaml
defaults:
  simulations: 500
matchups:
  - [rollout:random, rollout:greedy_score]      # 1.0 mix
  - [rollout:random, rollout:eps_greedy_0.3]    # ε=0.3
  - [rollout:eps_greedy_0.3, rollout:eps_greedy_0.5]
  - [rollout:random, rollout:k_step_heuristic]  # truncated rollout + leaf heuristic
  - [rollout:random@1000, rollout:eps_greedy_0.3@500]  # 2× sim budget control
```
**Games:** 200 per matchup (paired).
**Depends on:** pluggable rollout policy in `_simulate` (see TODO).
**Reasoning:** Random rollouts in Wingspan are particularly noisy because games are long (~200 moves) and end-of-round/round-goal alignment requires coherent play. This is the highest expected ROI experiment for raw playing strength; also a clean ablation for the "compute efficiency" paper angle.

---

### EXP-008: Bootstrap data quality for NN training
**Status:** pending
**Hypothesis (H6):** At fixed total compute, peek-MCTS bootstrap data trains an NN that matches or beats PIMC-bootstrap, before self-play iteration takes over.
**Config:** generate `N` games each from three data sources, train an identical NN architecture on each, evaluate all three against honest-PIMC opponent:
- (a) Peek-MCTS (biased, strong)
- (b) PIMC-MCTS (clean, weaker per game, so fewer games at fixed compute)
- (c) 50/50 mix
- (d) Curriculum: bootstrap on (a), fine-tune on (b)
**Games:** TBD — needs cost-of-PIMC numbers from EXP-006 first.
**Eval:** Head-to-head paired games against honest-PIMC reference player.
**Depends on:** EXP-006 (PIMC working), NN training pipeline, observable-only state encoder (see TODO).
**Reasoning:** AlphaZero went from expert data to pure self-play because they had the compute. We don't. The empirical question — "is biased-but-cheap bootstrap data a compute-efficient shortcut at our scale?" — is the central result the paper hinges on. Negative result is also publishable.

---

### EXP-009: Bootstrap vs from-scratch self-play
**Status:** pending
**Hypothesis (H7):** At fixed compute budget, NN warm-started from MCTS bootstrap data reaches target strength faster than NN trained from random init via pure self-play. Quantifying the speedup (and the crossover point where pure self-play catches up, if any) is a direct measurement of bootstrap's value at our compute scale.
**Config:** train two NNs of identical architecture under matched total-compute budgets:
- (a) **Bootstrap arm:** initial supervised training on N games of best-config MCTS, then iterative self-play.
- (b) **From-scratch arm:** random init, pure self-play from step 0 (AlphaZero recipe).
At checkpoints along the compute axis, evaluate each NN against the same reference opponent (honest-PIMC at fixed sims).
**Games:** TBD — needs an estimate of bootstrap-set size from EXP-008.
**Eval:** Win rate vs reference opponent at matched-compute checkpoints; the resulting strength-vs-compute curves are the deliverable.
**Depends on:** EXP-008 (bootstrap recipe settled), NN training pipeline, self-play loop.
**Reasoning:** AlphaZero demonstrated bootstrap is *unnecessary* at massive compute — random init + pure self-play reaches SOTA. Open-source replications (KataGo, Leela Zero) consistently find bootstrap is *load-bearing* at smaller compute, but the magnitude is game- and architecture-specific. The paper's compute-efficiency framing requires us to measure this directly rather than assume it. Negative result ("from-scratch matches bootstrap even at our scale") would itself be a publishable finding.

---

## Completed Experiments

_(none yet)_

## Notes & Observations

- 2024-02-04: Infrastructure ready - parquet storage, YAML configs, configurable exploration_constant
- 2024-02-04: **Determinism verified** - identical seeds produce identical MCTS trees and moves
- 2026-05-11: **Cross-process determinism verified** — identical seeds produce identical moves across `PYTHONHASHSEED ∈ {0, 1, random}` × `num_workers ∈ {1, 2}` × `game_seed ∈ {1, 42, 999}`. The engine is `PYTHONHASHSEED`-invariant; no env wrapper needed for paired comparisons even at `num_workers > 1`. See `lab/benchmarks/test_determinism.py`.
- **Paired-design variance reduction is reported as a byproduct of every paired EXP.** For each, compute `effective_n_multiplier = (Var(A) + Var(B)) / Var(A − B)` over the paired outcomes; record alongside the primary result. The methodology itself is textbook (paired t-test / McNemar / blocked designs) and needs no dedicated experiment to justify, but the realized multiplier is empirical and is expected to **vary across experiments**: large for small-effect comparisons (e.g. EXP-002 near-optimal `c` tuning), smaller for large-effect ones (e.g. EXP-001 sim-budget extremes). Paper methods section should report the range across all paired EXPs plus one representative anchor — not a single global number.
- Random vs MCTS sanity check needed before serious experiments
- Paired experiment framework: use `mode: paired` in config with `python -m lab -c <path>`

---

## Considered and Tabled

Ideas evaluated and explicitly *not* in the queue. Recorded with rationale so future-me doesn't re-litigate them.

### Variable simulation budget per legal-action count
**Intuition:** scale MCTS simulations by branching factor (more sims when more legal actions).
**Why tabled:** wrong abstraction layer. Wingspan's high-branching states are mostly *artificial* — `get_egg_payment_combinations` / `generate_food_payments` enumerate mechanically-equivalent payment splits. Scaling sims by branching factor would spend more compute on choices that don't matter. The real fix is **action canonicalization** (see TODO), which shrinks branching honestly and speeds up everything else. Revisit only if measurements show MCTS quality loss specifically on genuine high-branching states.

### xgboost / feature importance as the *primary* analysis methodology
**Intuition:** dump all games into a DataFrame, throw xgboost at it, read off feature importances (fastai-style).
**Why tabled:** observational data over a heterogeneous experiment pool is full of confounders — exactly what the paired-comparison design exists to remove. xgboost would tell you correlations entangled with sampling choices, not causal effects. **Kept as a second-pass EDA tool** to flag interactions worth designing a new paired experiment around (see TODO); not a replacement for the paired framework.

---

## Analysis Queries

Common pandas queries for analyzing results:

```python
import pandas as pd
df = pd.read_parquet('experiments/data/games.parquet')

# Win rate by strategy
df.groupby(['simulations', 'exploration_constant'])['is_winner'].mean()

# First player advantage
df.groupby('is_first_player')['is_winner'].mean()

# Score distribution
df.groupby('strategy_name')['total_score'].describe()
```
