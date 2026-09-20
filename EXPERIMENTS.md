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

## Experiment modes: when to use which

Two run modes implement the paired-comparison machinery, each suited to a different shape of question.

- **`vs_reference`** — every arm pitted against the fixed project-wide reference opponent (`REFERENCE_PARAMS` in `lab/generators.py`). Win rates for any arm in any vs_reference experiment live on the same scale and stack into a coherent ablation table. Linear scaling in number of values swept. **Use for**: sweeping multiple values of a parameter to find the best (best `c`, best sim count, best rollout policy).
- **`paired`** — direct A vs B head-to-head with shared seeds. Highest statistical power per binary question. Pairwise combinatorial scaling — expensive at >2 values. **Use for**: specific A/B questions (peek-MCTS vs PIMC, score-aware vs random rollouts) or tiebreaking between two arms that came out close in a `vs_reference` sweep.
- **`continuous`** — open-ended matchup runs (no fixed seeds, runs until Ctrl+C). **Use for**: exploratory data generation, smoke runs, or accumulating games for later analysis when statistical paired design isn't needed.

**`REFERENCE_PARAMS` is a determinized PIMC opponent.** IS-MCTS/PIMC is implemented in `game/core/redeterminize.py` and exposed via `MCTSConfig.determinize`. Empirically, PIMC matches or beats the wall-clock throughput of peek-MCTS because per-simulation redeterminization is cheaper than peek-MCTS's cached-node state copying. The project has adopted PIMC as the fixed reference. Win rates from experiments run against this reference are on a common scale; any pre-PIMC data is no longer comparable.

**Recommended sequence for sweeps:** `vs_reference` coarse sweep → if top arms are within noise, `paired` tiebreak between the contenders.

**Setting `base` in `vs_reference`:** by default, set `base` to match the reference's non-swept params. Arms then differ from the reference only in the swept dimension, giving the cleanest "pure effect of this one knob" reading. Diverging `base` from the reference (e.g., different sim count) is valid for explicit interaction studies — but be aware that win rates compress near 0% or 100% when arms are much weaker or stronger than the reference, and multi-parameter divergence muddies attribution. Call out divergence explicitly in the experiment hypothesis.

## Hypotheses & Goals

- **H1:** Higher simulation counts yield diminishing returns beyond a threshold
- **H2:** Default exploration constant (√2 ≈ 1.41) is suboptimal for Wingspan
- **H3:** Value function choice (score_delta vs win_loss vs absolute_score) affects play style and win rate
- **H4:** Current MCTS implicitly exploits hidden information (deck order, dice via seeded `rng`, opponent hands) through `transition_state` determinism. A determinized variant (PIMC) that reshuffles unknowns per simulation will play measurably differently, and the gap quantifies how much current MCTS strength comes from peek vs honest planning.
- **H5:** Replacing uniform-random rollouts with score-aware rollouts (ε-greedy on score delta, or K-step + heuristic with early termination) beats random rollouts at fixed simulation budget by a margin larger than 2× sim count — i.e., it's a strictly better use of compute than throwing more sims at random rollouts.
- **H6:** At fixed total compute, an NN bootstrapped from biased-but-strong (peek-MCTS) self-play games matches or beats an NN bootstrapped from clean-but-weaker (PIMC) games, before iterative self-play washes out the bias. If true, dirty bootstrap data is a compute-efficient shortcut in low-compute regimes — the central question for the paper.
- **H7:** At our compute scale, an NN warm-started from MCTS-generated bootstrap data reaches a target strength level (e.g., beating reference MCTS at ≥55% win rate) using strictly less total compute than an NN trained from random init via pure self-play. AlphaZero showed bootstrap is *unnecessary* at massive compute; we expect it is *load-bearing* at our scale. Quantifying the speedup — and the crossover point where pure self-play catches up — is part of the compute-efficiency frontier the paper characterizes.
- **Goal:** Find optimal MCTS configuration for competitive 2-player and 3-player games, and characterize the compute-efficiency frontier for NN bootstrap strategies.

## Experiment Catalog

### EXP-001: Simulation budget scaling
**Hypothesis:** Win rate advantage of higher sims plateaus around 1000–1500.
**What it measures:** Strength as a function of simulation budget at otherwise fixed config.
**Why:** Establish the baseline scaling curve before tuning other params. The knee of the curve sets the default sim count for every later experiment.

---

### EXP-002: Exploration constant coarse sweep
**Hypothesis (H2):** Optimal `c` is game-specific; Wingspan's moderate branching may favor `c < √2`.
**What it measures:** Win rate as a function of `c` across a range that brackets the textbook default.
**Why:** Literature shows `c` is the most impactful hyperparameter. Coarse sweep first; if two values come out close, paired tiebreak.
**Depends on:** EXP-001 (to pick appropriate simulation count).

---

### EXP-003: Value function comparison
**Hypothesis (H3):** `score_delta` outperforms `win_loss` due to richer signal.
**What it measures:** Win rate of each value function against the same reference.
**Why:** Different value functions encode different objectives — `score_delta` rewards winning by margin, `win_loss` only the outcome, `absolute_score` ignores opponents. Effect on play style and strength is unknown.

---

### EXP-004: First player advantage quantification
**Hypothesis:** First player has measurable advantage (estimated 3–5%).
**What it measures:** Win-rate split by `is_first_player` across symmetric self-play.
**Why:** Needed to control for first-player effect when interpreting all other experiments. Quick sanity check; also validates the position-swap machinery works as intended.

---

### EXP-005: Selection policy comparison
**Hypothesis:** Alternative selection policies (UCB1-Tuned, PUCT) may outperform standard UCB1 for Wingspan's branching structure.
**What it measures:** Win rate of each selection policy at fixed sim budget.
**Design idea:** Abstract the selection policy behind a protocol (e.g., `SelectionPolicy` with a `score(node, parent_visits) -> float` method) so `_select` becomes policy-agnostic. Candidates: UCB1 (current), UCB1-Tuned (variance-aware), PUCT (prior-weighted; AlphaZero's choice), Thompson Sampling (posterior).
**Why:** The selection policy governs how the tree is traversed; different policies trade exploration vs exploitation differently and the optimal choice is game-dependent.
**Depends on:** EXP-001, EXP-002 (establish baseline with UCB1 first).

---

### EXP-006: Peek-MCTS vs PIMC (determinization)
**Status: implementation complete; reference decision settled outside this experiment.**
**Hypothesis (H4):** Current MCTS implicitly exploits hidden info via `transition_state` determinism. PIMC (re-shuffle `bird_deck` / `bonus_deck` / opponent hidden hands and re-seed `state.rng` per simulation) plays measurably differently. The strength gap *in honest evaluation* is the cheat tax.
**What it measures:** Win rate of peek-MCTS vs honest PIMC, both evaluated under honest play conditions.
**Why:** Quantifies how much of current MCTS's strength comes from exploiting engine-level observability that a real agent wouldn't have.
**Note:** PIMC/IS-MCTS was implemented and the project reference was switched to determinized MCTS after wall-clock and early-strength data showed it was the better standard. The experiment can still be run as a historical A/B, but it is no longer a gating decision for the reference.

---

### EXP-007: Rollout policy comparison
**Hypothesis (H5):** Score-aware rollouts beat random rollouts at fixed sim budget by more than 2× sim count.
**What it measures:** Win rate of each rollout policy (random, greedy_score, eps_greedy at various ε, K-step + heuristic) at fixed sim budget; also a "2× sim budget control" run to confirm the win isn't just from extra compute.
**Why:** Random rollouts in Wingspan are particularly noisy because games are long (~200 moves) and end-of-round/round-goal alignment requires coherent play. Highest expected ROI experiment for raw playing strength; also a clean ablation for the compute-efficiency paper angle.
**Depends on:** pluggable rollout policy in `_simulate` (see TODO).

---

### EXP-008: Bootstrap data quality for NN training
**Hypothesis (H6):** At fixed total compute, peek-MCTS bootstrap data trains an NN that matches or beats PIMC-bootstrap, before self-play iteration takes over.
**Config:** generate `N` games each from three data sources, train an identical NN architecture on each, evaluate all three against honest-PIMC opponent:
- (a) Peek-MCTS (biased, strong)
- (b) PIMC-MCTS (clean, weaker per game, so fewer games at fixed compute)
- (c) 50/50 mix
- (d) Curriculum: bootstrap on (a), fine-tune on (b)
**Games:** TBD — needs cost-of-PIMC numbers from EXP-006 first.
**Eval:** Head-to-head paired games against honest-PIMC reference player.
**Depends on:** NN training pipeline, observable-only state encoder (see TODO).
**Reasoning:** AlphaZero went from expert data to pure self-play because they had the compute. We don't. The empirical question — "is biased-but-cheap bootstrap data a compute-efficient shortcut at our scale?" — is the central result the paper hinges on. Negative result is also publishable.

---

### EXP-009: Bootstrap vs from-scratch self-play
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

- **2026-05-11:** Cross-process determinism verified across `PYTHONHASHSEED` / worker count / game seed for both peek and IS-MCTS (`lab/benchmarks/test_determinism.py`).
- **2026-06:** IS-MCTS/PIMC determinization implemented and adopted as the project reference.
- **2026-06:** Optuna joint hyperparameter search (`mcts_joint_v1`) completed 75 trials × 20 seeds. Best config beat the PIMC reference at 77.5% win rate (`simulations=1500`, `exploration_constant≈2.27`, `value_function=absolute_score`, `widening_alpha≈0.83`, `widening_k≈1.70`).

## Notes & Observations

- 2024-02-04: Infrastructure ready - parquet storage, YAML configs, configurable exploration_constant
- 2024-02-04: **Determinism verified** - identical seeds produce identical MCTS trees and moves
- 2024-02-04: Infrastructure ready - parquet storage, YAML configs, configurable exploration_constant.
- 2024-02-04: **Determinism verified** - identical seeds produce identical MCTS trees and moves.
- 2026-05-11: **Cross-process determinism verified** — identical seeds produce identical moves across `PYTHONHASHSEED ∈ {0, 1, random}` × `num_workers ∈ {1, 2}` × `game_seed ∈ {1, 42, 999}`. The engine is `PYTHONHASHSEED`-invariant; no env wrapper needed for paired comparisons even at `num_workers > 1`. See `lab/benchmarks/test_determinism.py`.
- 2026-06: PIMC/IS-MCTS determinization implemented in `game/core/redeterminize.py` and adopted as the project-wide reference.
- 2026-06: Optuna joint search (`mcts_joint_v1`, 75 trials) completed; best configuration recorded under Completed Experiments.
- **Paired-design variance reduction is reported as a byproduct of every paired EXP.** For each, compute `effective_n_multiplier = (Var(A) + Var(B)) / Var(A − B)` over the paired outcomes; record alongside the primary result. The methodology itself is textbook (paired t-test / McNemar / blocked designs) and needs no dedicated experiment to justify, but the realized multiplier is empirical and is expected to **vary across experiments**: large for small-effect comparisons (e.g. EXP-002 near-optimal `c` tuning), smaller for large-effect ones (e.g. EXP-001 sim-budget extremes). Paper methods section should report the range across all paired EXPs plus one representative anchor — not a single global number.

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

## Analysis goals

What the analysis layer should be able to answer (implementation in `analysis.py`):

- Win rate by hyperparameter value (groupby on any key inside `strategy_config`).
- First-player advantage size and direction (split by `is_first_player`).
- Score distribution and breakdown across strategies and configs.
- Per-experiment paired-design variance reduction multiplier (the empirical complement to the textbook claim — see Notes & Observations).
- Game closeness / round goal contribution / decision-point statistics from the joined `games` + `decisions` parquets.
