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

- **`vs_reference`** — every arm pitted against a reference opponent: by default the fixed project-wide `REFERENCE_PARAMS` (`lab/generators.py`), or any strategy via `compare.reference` (e.g. the self-play generator, EXP-013/014). Arms are interleaved seed by seed, and without `seeds.count` it runs until stopped. Win rates for any arm in any vs_reference experiment live on the same scale and stack into a coherent ablation table. Linear scaling in number of values swept. **Use for**: sweeping multiple values of a parameter to find the best (best `c`, best sim count, best rollout policy).
- **`paired`** — direct A vs B head-to-head with shared seeds. Highest statistical power per binary question. Pairwise combinatorial scaling — expensive at >2 values. **Use for**: specific A/B questions (peek-MCTS vs PIMC, score-aware vs random rollouts) or tiebreaking between two arms that came out close in a `vs_reference` sweep.
- **`continuous`** — open-ended matchup runs (no fixed seeds, runs until Ctrl+C). **Use for**: exploratory data generation, smoke runs, or accumulating games for later analysis when statistical paired design isn't needed.

**`REFERENCE_PARAMS` is a determinized PIMC opponent.** IS-MCTS/PIMC is implemented in `src/wingspan/engine/core/redeterminize.py` and exposed via `MCTSConfig.determinize`. Empirically, PIMC matches or beats the wall-clock throughput of peek-MCTS because per-simulation redeterminization is cheaper than peek-MCTS's cached-node state copying. The project has adopted PIMC as the fixed reference. Win rates from experiments run against this reference are on a common scale; any pre-PIMC data is no longer comparable.

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
- **H8:** Encoding sets of cards with a set encoder (each card through a shared learned net, then summed) beats summing or averaging raw card features, because the raw pool loses which properties belong to the same card (a grassland-bowl + wetland-cavity pair encodes identically to wetland-bowl + grassland-cavity). This applies on two sides: the observation (hand, tray), where the gain should show in decisions that depend on what the hand can do (main-turn choice, value); and multi-bird actions (`select_initial_cards`, multi-bird `draw_cards`), where it should show in choosing which birds to take. Single-bird actions (`play_bird`) are encoded one bird at a time already, so no gain is expected there.
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

### EXP-010: Pooled vs set-encoded cards (observation × actions)
**Hypothesis (H8):** A set encoder over card lists beats pooling raw card features, on the observation side and on the action side independently.
**Config:** a 2×2 design. Same data, split, targets, trunk and action-MLP sizes, optimizer and seeds; only how card lists enter the net differs:

| | Actions: averaged (`action_bird_*` columns) | Actions: + set encoder over `action_bird_ids` |
|---|---|---|
| **Obs: summed** (`hand_*`, `tray_*` columns) | (a) baseline | (c) actions only |
| **Obs: + set encoder over `Observation.hand`, `.tray`** | (b) observation only | (d) both |

- The set encoder is `Σ φ(card)`: φ is a small MLP shared by all cards, applied to each card's `bird_table()` row, padded and masked; the sum is concatenated to the existing input. The observation and the actions get separate φ networks.
- The pooled columns stay in every arm, so (b)–(d) only add information; differences measure what keeping cards apart is worth.
- The 2×2 shows each effect alone and whether they add up (if (d) − (a) ≈ ((b) − (a)) + ((c) − (a)), the two are independent).

**Data:** the step-3 replay dataset from `mcts_joint_v2` (2,550 games), split by game. No new games needed. The dataset must store `Observation.hand`/`.tray` and `action_bird_ids` per legal action.
**Eval:** validation policy cross-entropy and top-1 agreement with MCTS, broken down by phase; value-net validation MSE by round. Repeat over 3 seeds; report the per-seed spread.
- Observation effect, (b) vs (a): primary readout `main_turn` and value MSE.
- Action effect, (c) vs (a): primary readout `select_initial_cards` (5,100 decisions, 64 options each) and `draw_cards`.
- Control for both: `play_bird`, a single-bird action, where no difference is expected. A difference there would point to something other than binding (more parameters, a different optimum).
**Depends on:** step 3 dataset builder, step 4 training loop.
**Reasoning:** DeepSets (Zaheer et al. 2017): any function of a set can be written as ρ(Σ φ(x)). Pooling raw features is the special case where φ is the identity, which can't represent conjunctions like "wetland AND bowl on one card". A ReLU unit with weights +1, +1 and bias −1 can, and summing such units counts the cards that satisfy it. The cost is one small MLP per side; if neither helps at this data scale, pooled features are good enough and stay the default.

---

### EXP-011: Paired flat Monte Carlo vs the champion MCTS
**Hypothesis:** At the champion's budget, flat Monte Carlo with common random numbers (every legal move played in the same re-dealt worlds with the same playout seeds) plays at least as well as the champion's IS-MCTS, and picks more reliable moves.
**Background (2026-11-07, 48 real positions from `mcts_joint_v2`):** the champion's UCB bonus (c≈2.27) dwarfs the value gaps between moves, so visits spread evenly and the search acts like unpaired flat Monte Carlo. Its picks are close to noise in collect_food, lay_eggs and draw_cards (seed agreement 31–45% vs 18–26% by chance), because a playout's luck (sd ~4.5 points) swamps move differences (~0.1–0.2 points). Pairing cuts that noise ×2–18 in those phases, and raises agreement with a precise reference from 60% to 71% at the same budget (Stage 1). Main actions and bird choice were already reliable.
**Config:** `experiments/flat_mc_vs_champion.yaml`, `vs_reference` mode, 50 fresh seeds (2001+) × 2 seats per arm, against REFERENCE_PARAMS at 1500 sims. Arms: `paired` (1500 playouts), `paired_lean_eggs` (same, 300 playouts for lay_eggs).
**Result:** see Completed Experiments.

---

### EXP-012: Per-phase playout budgets
**Hypothesis:** Giving each phase only the paired playouts it needs keeps paired flat Monte Carlo as strong while making games cheaper to generate.
**Background (2026-11-07, 204 positions, 12 per phase):** with paired playouts, the gap between a phase's best and second-best move and the playouts per move needed to separate them differ widely. collect_food, lay_eggs, pay_egg_cost, the discard choices and end_turn have gaps under 0.1 point (a wrong pick is cheap, separating would take 5,000–12,000 playouts per move); play_bird and activate_powers needed far less than they got; select_initial_cards had 23 playouts per option for the highest-stakes choice (10 points between best and worst hand).
**Config:** `experiments/flat_mc_phase_budget.yaml` (the budget table, with reasons), `vs_reference` against the champion @1500, 50 fresh seeds (3001+) × 2 seats, decisions recorded.
**Result:** see Completed Experiments.

---

### EXP-013: With fast search, does a tree or more simulations beat the data generator?
**Hypothesis:** EXP-011/012 compared at Python-affordable budgets (1500). With the Rust engine (~30× faster), a real tree (IS-MCTS) or many more simulations may beat the current generator.
**Config:** `experiments/tree_vs_flat.yaml` (`vs_reference`, each deal from both seats; the 2026-11-08 run used deals 20001+, 19 min on 7 cores, via the since-removed `rust/py/exp_tree.py`, results in `experiments/data/exp_tree/results.jsonl`). Every arm plays the reference = `flat_mc_rs` with the EXP-012 phase table. Arms: champion tree (`mcts-v1` params) at 1500 and 10k sims, 10k with c=0.7, flat 1500 without the table, flat with the table ×10.
**Result:** see Completed Experiments.

---

### EXP-014: Tree scaling curve, and the phase table for the tree
**Hypothesis:** The tree keeps gaining with simulations; the EXP-012 phase table, scaled to the tree, keeps strength at lower cost as it did for flat MC.
**Config:** `experiments/tree_scaling.yaml` (`vs_reference`, each deal from both seats, run until stopped; the 2026-11-09 run used deals 30001+ via the since-removed `rust/py/exp_tree.py`, scores only, in `experiments/data/exp_scaling/results.jsonl`). Same reference as EXP-013. `tree_table_10k`: 10k sims by default, the flat table's ratios for the other phases (40k setup, 5k powers, 4k play bird, 2k food/eggs/discards).
**Result:** see Completed Experiments.

---

## Completed Experiments

- **2026-05-11:** Cross-process determinism verified across `PYTHONHASHSEED` / worker count / game seed for both peek and IS-MCTS (`lab/benchmarks/test_determinism.py`).
- **2026-06:** IS-MCTS/PIMC determinization implemented and adopted as the project reference.
- **2026-06:** Optuna joint hyperparameter search (`mcts_joint_v1`) completed 75 trials × 20 seeds. Best config beat the PIMC reference at 77.5% win rate (`simulations=1500`, `exploration_constant≈2.27`, `value_function=absolute_score`, `widening_alpha≈0.83`, `widening_k≈1.70`).

- **2026-11-07:** EXP-011, paired flat Monte Carlo vs the champion MCTS, 100 games per arm. `paired` 52-45-3 (53.5%, 95% CI 44–63%); `paired_lean_eggs` 61-39 (61.0%, 95% CI 51–71%, p=0.03 vs 50%, not corrected for two arms). The arms do not differ significantly (+7.5 ± 13.7 points). Reading: dropping the tree for a paired root comparison costs nothing measurable, and cutting lay_eggs to 300 playouts does not hurt; a real gain over the champion is plausible but not established at this sample size. Paired flat MC (with lean eggs) becomes the default for new training games, where its more reliable picks also make better policy labels.

- **2026-11-08:** EXP-012, per-phase budgets vs the champion MCTS, 100 games: 49-50-1 (49.5%, 95% CI 40–59%), at ~50.6 s per game vs ~57–61 s with the full budget (the champion's half unchanged, so the bot's own share fell by roughly 30%). Same strength, cheaper: these budgets are used for self-play data (`experiments/selfplay_flat_mc.yaml`). EXP-011's 61% for lean eggs alone is within noise of this (difference 11.5 ± 13.7 points).

- **2026-11-08:** EXP-013, 277 games (~55 per arm), score difference per deal vs the reference (95% CI): tree 1500 −2.1 ± 2.1; **tree 10k +2.6 ± 1.8** (win 66%); **tree 10k c=0.7 +2.6 ± 2.1** (69%); flat 1500 without the table −0.5 ± 2.2; flat with the table ×10 −0.2 ± 2.2. Reading: at 1500 the tree is no better than paired flat MC (EXP-011 holds at its budget), but it scales with simulations while flat MC does not (10× playouts: nothing; its limit is the random-rollout bias, not noise). The table is free for flat MC.

- **2026-11-09:** EXP-014, 2,688 games (~335 deals per arm). Vs the reference, per deal: tree 3k +0.2 ± 0.7 (8 s/game), **10k +2.4 ± 0.7** (24 s), **30k +3.5 ± 0.7** (75 s), table 10k +1.6 ± 0.7 (19 s). Same-deal comparisons: 3k→10k +2.1 ± 0.9, 10k→30k +1.15 ± 0.9, table 10k − plain 10k −0.7 ± 0.85. Reading: gains roughly halve per tripling of simulations while cost is linear (100k would add ~+0.5 for 3.3× cost; not run). The reference plays like a 3k tree. The table does not help the tree: it saves 20% of the time but lands where plain simulations at that cost would (~+1.9), slightly below. Drop the table for the tree; tree 10k+ is the way past flat MC's strength, flat MC stays the cheapest at its level.

## Notes & Observations

- **2026-11-09, root visits are near-uniform at any budget (`rust/py/visits.py`, 480 real positions).** Champion tree at 1.5k/3k/10k/30k: effective moves / legal moves 1.00/1.00/1.00/0.99; top visit share 0.37→0.40 (main_turn 0.34→0.41, uniform 0.31); median Q gap best−second 0.40→0.31 points; most-visited = best-Q 94%→100%. The exploration constant (c≈2.27) dwarfs the Q gaps (0.3–0.7 points = 0.003–0.007 in absolute_score units; the bonus is ~0.07 even at 30k), so extra simulations buy precision of Q, not focus. Consequences: (1) visit counts are near-useless as policy targets with this c (use Q instead); (2) c on the scale of the gaps (~0.05–0.2) is the untested lever (EXP-013's c=0.7 is still far too large).

- 2024-02-04: Infrastructure ready - parquet storage, YAML configs, configurable exploration_constant
- 2024-02-04: **Determinism verified** - identical seeds produce identical MCTS trees and moves
- 2024-02-04: Infrastructure ready - parquet storage, YAML configs, configurable exploration_constant.
- 2024-02-04: **Determinism verified** - identical seeds produce identical MCTS trees and moves.
- 2026-05-11: **Cross-process determinism verified** — identical seeds produce identical moves across `PYTHONHASHSEED ∈ {0, 1, random}` × `num_workers ∈ {1, 2}` × `game_seed ∈ {1, 42, 999}`. The engine is `PYTHONHASHSEED`-invariant; no env wrapper needed for paired comparisons even at `num_workers > 1`. See `lab/benchmarks/test_determinism.py`.
- 2026-06: PIMC/IS-MCTS determinization implemented in `src/wingspan/engine/core/redeterminize.py` and adopted as the project-wide reference.
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
