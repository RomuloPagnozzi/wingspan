# Backlog

Prioritized work, top = next. Each item has a design vision and is one refinement away from implementation. Engineering specs are inline; experiment definitions live in `EXPERIMENTS.md` and are linked.

## Sprint order

1. [Rewrite analysis.py](#rewrite-analysispy) — Phase 1 finishing item; unblocks interpreting any experiment.
2. [EXP-004](EXPERIMENTS.md#exp-004-first-player-advantage-quantification) — first-player advantage sanity check; doesn't depend on reference finalization.
3. [PIMC implementation](#pimc-implementation) — engineering prerequisite for EXP-006 and EXP-008.
4. [EXP-006](EXPERIMENTS.md#exp-006-peek-mcts-vs-pimc-determinization) — measures the cheat tax.
5. **Finalize `REFERENCE_PARAMS`** based on EXP-006 outcome. Until done, strength-sensitive experiments may need to be re-run.
6. [Score-aware rollouts](#score-aware-rollout-policies) — engineering prerequisite for EXP-007.
7. Strength-sensitive experiments in any order: [EXP-001](EXPERIMENTS.md#exp-001-simulation-budget-scaling), [EXP-002](EXPERIMENTS.md#exp-002-exploration-constant-coarse-sweep), [EXP-003](EXPERIMENTS.md#exp-003-value-function-comparison), [EXP-005](EXPERIMENTS.md#exp-005-selection-policy-comparison), [EXP-007](EXPERIMENTS.md#exp-007-rollout-policy-comparison). All use `vs_reference` against the finalized reference.
8. [Action canonicalization](#action-canonicalization) — independent compute win; useful before mass game generation.
9. [State + action serialization](#state--action-serialization-for-nn-training) — NN encoder design; gates EXP-008.
10. [Generate training data for NN pipeline](#generate-training-data-for-nn) — gates EXP-008.
11. [EXP-008](EXPERIMENTS.md#exp-008-bootstrap-data-quality-for-nn-training) — bootstrap data quality.
12. [EXP-009](EXPERIMENTS.md#exp-009-bootstrap-vs-from-scratch-self-play) — bootstrap vs from-scratch.
13. [Complexity benchmark for the paper](#complexity-benchmark-for-the-paper) — paper-time, lowest urgency.

---

## Specs

### Rewrite analysis.py

Rewrite `analysis.py` as a library of reusable plotting functions that accept filtered DataFrames. The old script assumed wide-format CSV (`p1_total_score`, `p2_total_score`, `winner`). New data is long-format parquet (one row per player per game).

**Design:**
- Library of small reusable plotting functions that accept filtered DataFrames (no config, no CLI; user brings their own pandas query). Natural interface is a notebook.
- `generate_html_report(plots, title)` wraps matplotlib figures into HTML.

**Capabilities the toolkit should cover** (see "Analysis goals" in `EXPERIMENTS.md`):
- Compare arms across any hyperparameter (groupby on keys inside `strategy_config`).
- Score and score-breakdown distributions across strategies and configs.
- Game-closeness summaries from `games.parquet`.
- Joined queries against `decisions.parquet` for action-frequency / per-decision-point analyses.
- Paired-design variance reduction multiplier per experiment.

**Replaces:** `analysis.py` (CSV-based), `experiments/analyze_all.py` (batch CSV report generator).

**Second-pass EDA via xgboost / SHAP:** add a module that takes the combined `games.parquet` (+ optional `decisions.parquet` features like per-game branching factor, phase distribution, game length) and runs xgboost feature-importance / SHAP analysis to surface unexpected hyperparameter interactions. **This is hypothesis generation, not hypothesis testing** — any interaction surfaced here must be followed up with a new paired experiment to make a causal claim. See "Considered and Tabled" in `EXPERIMENTS.md` for why this is not the primary analysis.

---

### PIMC implementation

Engineering prereq for **EXP-006** and **EXP-008**.

Add a method to `GameState` (or a free function in `game/core/`) that re-randomizes all hidden information from a given player's perspective:

```python
def reshuffle_unknown(state: GameState, from_perspective_of: int, rng: random.Random) -> None:
    """Re-randomize everything `from_perspective_of` shouldn't know:
    - bird_deck and bonus_deck (preserve length and contents, only order changes)
    - other players' bird_hand and bonus_hand (resample from remaining unseen pool)
    - state.rng (re-seed from rng)
    Used per-simulation in PIMC mode to average MCTS values over plausible worlds.
    """
```

Plug into MCTS as a new flag (`MCTSConfig.determinize: bool = False`). When true, `_simulate` calls `reshuffle_unknown` on a copy of the root state before each rollout. Keep peek-mode as the default for now — switching the default is its own experiment (EXP-006).

---

### Score-aware rollout policies

Engineering prereq for **EXP-007** (highest expected strength ROI).

Make `_simulate`'s action selection pluggable. Add to `MCTSConfig`:

```python
rollout_policy: RolloutPolicy = RolloutPolicy.RANDOM
rollout_epsilon: float = 0.3  # for eps_greedy
rollout_max_steps: int | None = None  # None = play to terminal
rollout_leaf_value: LeafValue = LeafValue.TERMINAL_SCORE  # or HEURISTIC at K-step cutoff
```

Variants to implement and benchmark:
- `RANDOM` (current)
- `GREEDY_SCORE` — always pick the action with max immediate `update_player_scores` delta
- `EPS_GREEDY` — greedy with prob (1−ε), random with prob ε
- `K_STEP + HEURISTIC` — stop after K moves (or at end-of-round), return `player.score.total − max_opponent_score` as leaf value

The K-step variant is the big compute win: stops rollouts well before terminal so each sim is cheaper.

---

### Action canonicalization

Replaces the "variable simulation budget per branching" idea (see `EXPERIMENTS.md` / "Considered and Tabled").

`get_egg_payment_combinations`, `generate_food_payments`, and `get_egg_distribution_combinations` currently enumerate *every* legal payment/distribution. Many are mechanically equivalent (paying 1 egg from bird A vs bird B at the same spot-column when neither has a power that cares which one). Collapse these into canonical representatives before MCTS sees them, then re-expand at apply time if the engine needs the specific assignment.

Hypothesized impact: large reduction in branching at payment/lay phases → MCTS spends sims on choices that actually matter → strict win on equal sim budget. Worth measuring before/after on EXP-001 sim-scaling curves to see whether the diminishing-returns threshold shifts.

---

### State + action serialization for NN training

When building the RL training pipeline, design a coherent encoding scheme for both game state and actions together. Currently actions are stored as `str(action)` (dataclass repr) which is fine for analysis/replay but not for NN input.

**Needs:**
- Observable view of `GameState` → fixed-size tensor
- `Action` → integer index into action space (with legal action masking)
- `visit_counts` → policy target vector aligned with action indices

Storage decision is settled: action sequences are stored upfront; observable state is derived via engine replay at training time (see [Generate training data for NN](#generate-training-data-for-nn)).

**Observable-only constraint (load-bearing for EXP-008):** the encoder must include *only* what an honest agent observes. Specifically:

| Include | Exclude |
|---|---|
| Your own `bird_hand`, `bonus_hand`, `food`, `board`, `action_cubes`, `score` | `state.bird_deck` order (deck *count* is fine; deck *order* is the cheat) |
| Opponents' visible state: their `board`, their `score`, their `action_cubes`, public counts | `state.bonus_deck` order |
| `bird_tray`, `feeder` (current dice roll), `discarded_birds`, `discarded_bonuses` | Other players' `bird_hand` / `bonus_hand` |
| `round`, `current_player_index`, `round_goal_config` | `state.rng` state |

If any of the excluded fields leaks into the encoder, the NN will learn cheating patterns that peek-MCTS encodes — and lose them at inference. This is the structural firewall that bounds how much damage biased bootstrap data (EXP-008 path (a)) can do.

---

### Generate training data for NN

Two-stage pipeline: **collect** (expensive, upfront) and **derive** (cheap, at training time).

**Collect — already in place.** `decisions.parquet` records the action sequence (sparse at choice points, forced moves filled by engine replay), MCTS visit counts, root value, per-action Q-values, and final outcome per game. MCTS runs are the bottleneck — these are done once and stored.

**Derive — to build.** At training time, the observable state at each decision point is reconstructed by replaying the game's action log through the engine (~5 ms/game, benchmarked). Nothing extra to store; engine determinism gives us this for free.

**Pipeline to build (in order):**

1. **Game replay** — given `(game_seed, n_players, scoring_mode, recorded_actions)`, walk the engine and yield `(state, decision_record)` at each recorded choice point. Forced moves apply automatically (their action is unambiguous).
2. **Observable view extractor** — given a state and acting player, return the subset the agent honestly sees. Strict exclusions: `bird_deck` order, `bonus_deck` order, other players' `bird_hand` / `bonus_hand`, `state.rng`. Include their counts, public board, score breakdown, etc. See the include/exclude table in [State + action serialization](#state--action-serialization-for-nn-training).
3. **State + action encoders** — see the separate [State + action serialization](#state--action-serialization-for-nn-training) item.
4. **Training-example assembly** — for each decision: `(encode(observable_view), encode_policy(visit_counts), encode_value(outcome or mcts_root_value))`.

**Key distinction:**
- MCTS data collection is expensive (a 500-sim move takes ~250 ms; a game ~150 decisions) and happens once.
- Observable-state derivation is cheap (engine replay only) and happens lazily during training. Changing the encoder doesn't require re-collecting MCTS data.

This mirrors the source-of-truth + derived-tensor pattern used by successful AlphaZero replications.

**Prerequisite for:**
- **EXP-008** (NN bootstrap data quality)
- Any NN-based strategy in `lab/strategies/`

---

### Complexity benchmark for the paper

Script that simulates many random games at each `n_players ∈ {2, 3, 4, 5}` and computes:

- Average / max branching factor per phase
- Game tree depth (turn count distribution)
- State-space complexity estimates
- Phase distribution (% of decisions in each `GamePhase`)
- Output as a table in standard notation suitable for the paper.

Replaces the previous deleted version. Goal: be thorough enough to cite as the canonical Wingspan complexity characterization.
