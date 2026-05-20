# Engineering TODOs

## Analysis toolkit for parquet data

Rewrite `analysis.py` as a library of reusable plotting functions that accept filtered DataFrames.
The old script assumed wide-format CSV (`p1_total_score`, `p2_total_score`, `winner`).
New data is long-format parquet (one row per player per game).

**Design:**
- Functions like `compare_groups(df, by)`, `score_breakdown(df)`, `game_closeness(df)`
- `generate_html_report(plots, title)` wraps matplotlib figures into HTML
- No config or CLI filters - the user brings their own pandas query
- Natural interface is a notebook

**Example usage:**
```python
from experiments.analysis import compare_groups, score_breakdown

df = pd.read_parquet("experiments/data/games.parquet")

# Compare simulation budgets
compare_groups(df[df.simulations.isin([500, 1000])], by="simulations")

# Compare value functions for 2-player games
compare_groups(df[df.player_count == 2], by="value_function")

# Join with decisions for arbitrary queries
decisions = pd.read_parquet("experiments/data/decisions.parquet")
games_with_bird = decisions[decisions.action_taken.str.contains("bird_id=42")].game_id.unique()
score_breakdown(df[df.game_id.isin(games_with_bird)])
```

**Replaces:** `analysis.py` (CSV-based), `experiments/analyze_all.py` (batch CSV report generator)

**Second-pass EDA via xgboost / SHAP:** in addition to the paired-comparison plots, add a module that takes the combined `games.parquet` (+ optional `decisions.parquet` features like per-game branching factor, phase distribution, game length) and runs xgboost feature-importance / SHAP analysis to surface unexpected hyperparameter interactions. **This is hypothesis generation, not hypothesis testing** — any interaction surfaced here must be followed up with a new paired experiment to make a causal claim. See "Considered and Tabled" in EXPERIMENTS.md for why this is not the primary analysis.

---

## Generate training data for NN

Expand `decisions.parquet` so each row captures the full agent observation at the decision point, not just the chosen action. Today's schema records *what was chosen* (`action_taken`, `legal_actions`, `visit_counts`) and a sliver of *when* (`round`, `game_phase`, `player_position`) — but almost none of *what the agent could see when choosing*. The central strategic drivers (bonus card, active round goal, hand, board) are absent. As-is, the data is not trainable for any NN that needs to map (observation → policy / value).

Two classes of fields to add: observable state and turn-cascade context.

### 1. Observable state snapshot at decision time

Scoped to what an honest agent sees. Mirrors the include/exclude table in the "State + action serialization" TODO.

- **Self:** `bird_hand`, `bonus_hand`, `food`, `board` (with per-bird `eggs` / `stashed_food` / `tucked_cards`), `action_cubes`, `used_pink_powers`, full `score` breakdown (not just total)
- **Opponents** (public Wingspan info only): each opponent's `board`, `food` totals, `action_cubes`, `score` breakdown, `bird_hand` *size*, `bonus_hand` *size*, `first_player` flag
- **Shared:** `bird_tray` (3 face-up cards), `feeder` (current dice), `bird_deck` *count*, `bonus_deck` *count*, `discarded_birds` (contents or at minimum count), `discarded_bonuses` count
- **Round meta:** the active round goal (`round_goal_config.selected_goals[round-1]`), `scoring_mode`

Strict exclusions (the cheats that EXP-008 hinges on suppressing): `bird_deck` *order*, `bonus_deck` *order*, opponents' hidden hand contents, `state.rng` state.

### 2. Turn-cascade context

The "where in the turn am I" signal that's currently invisible — without it the NN cannot distinguish a fresh main-action choice from a forced sub-decision deep in a power cascade.

- `turn_in_round` — derived from `action_cubes` (round-start cubes minus current). Load-bearing for tempo decisions: round 1 turn 8 vs turn 1 play completely differently.
- `turn_decision_idx` — counter that resets when this player re-enters `MAIN_TURN`. Tells the NN whether the current decision starts a strategic action or continues a cascade.
- `cascade_origin` — what triggered the current sub-cascade: the main action that started the turn (`play_bird` / `lay_eggs` / `draw_cards` / `gain_food`), and if applicable the `power_id` + `bird_id` of the power being resolved. Mostly reconstructable from `state.action_data.execution_stack` / `powers_queue` at the decision point; easier to capture once than re-derive.

### Implementation notes

- Schema change in `lab/data.py:DECISIONS_SCHEMA` — add new fields, keep existing ones.
- Capture point is `lab/simulation.py:simulate_game`, inside the `if game_decisions is not None and len(actions) > 1:` block — that's where the state object is in hand right before the action is applied.
- Serialize state to compact columnar form (nested structs / lists in Arrow), not pickled blobs. Pickled blobs in parquet are an anti-pattern (opaque, unqueryable, version-coupled).
- Order of operations: do this **before** the NN encoder work — encoder design is downstream of what raw fields are available.

### Prerequisite for

- **EXP-008** (NN bootstrap data quality) — without this, neither peek-MCTS nor PIMC training data is actually trainable.
- Any NN-based strategy in `lab/strategies/`.

---

## State + action serialization for NN training

When building the RL training pipeline, design a coherent encoding scheme for both
game state and actions together. Currently actions are stored as `str(action)` (dataclass repr)
which is fine for analysis/replay but not for NN input.

**Needs:**
- `GameState` → fixed-size tensor
- `Action` → integer index into action space (with legal action masking)
- `visit_counts` → policy target vector aligned with action indices
- Decide between replay-from-seeds vs pre-computed tensor storage

**Observable-only constraint (load-bearing for EXP-008):** the encoder must include *only* what an honest agent observes. Specifically:

| Include | Exclude |
|---|---|
| Your own `bird_hand`, `bonus_hand`, `food`, `board`, `action_cubes`, `score` | `state.bird_deck` order (deck *count* is fine; deck *order* is the cheat) |
| Opponents' visible state: their `board`, their `score`, their `action_cubes`, public counts | `state.bonus_deck` order |
| `bird_tray`, `feeder` (current dice roll), `discarded_birds`, `discarded_bonuses` | Other players' `bird_hand` / `bonus_hand` |
| `round`, `current_player_index`, `round_goal_config` | `state.rng` state |

If any of the excluded fields leaks into the encoder, the NN will learn cheating patterns that peek-MCTS encodes — and lose them at inference. This is the structural firewall that bounds how much damage biased bootstrap data (EXP-008 path (a)) can do.

---

## Determinization (PIMC) for MCTS

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

## Score-aware rollout policies

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
- `EPS_GREEDY` — greedy with prob (1-ε), random with prob ε
- `K_STEP + HEURISTIC` — stop after K moves (or at end-of-round), return `player.score.total - max_opponent_score` as leaf value

The K-step variant is the big compute win: stops rollouts well before terminal so each sim is cheaper.

---

## Action canonicalization

Replaces the "variable simulation budget per branching" idea (see EXPERIMENTS.md / Considered and Tabled).

`get_egg_payment_combinations`, `generate_food_payments`, and `get_egg_distribution_combinations` currently enumerate *every* legal payment/distribution. Many are mechanically equivalent (paying 1 egg from bird A vs bird B at the same spot-column when neither has a power that cares which one). Collapse these into canonical representatives before MCTS sees them, then re-expand at apply time if the engine needs the specific assignment.

Hypothesized impact: large reduction in branching at payment/lay phases → MCTS spends sims on choices that actually matter → strict win on equal sim budget. Worth measuring before/after on EXP-001 sim-scaling curves to see whether the diminishing-returns threshold shifts.

---

## Complexity benchmark for the paper

Script that simulates many random games at each `n_players ∈ {2, 3, 4, 5}` and computes:

- Average / max branching factor per phase
- Game tree depth (turn count distribution)
- State-space complexity estimates
- Phase distribution (% of decisions in each `GamePhase`)
- Output as a table in standard notation suitable for the paper.

Replaces the previous deleted version. Goal: be thorough enough to cite as the canonical Wingspan complexity characterization.

---

## Inbox

Unprioritized notes — things to revisit when relevant, not scheduled.

- **vs_reference: factorial sweeps.** v1 sweeps one parameter at a time. If we ever want to vary two parameters together (e.g., simulations × exploration_constant) under the same vs_reference framework, generalize `compare` from a single `parameter`/`values` pair to a list. Currently solvable by multiple sequential single-parameter runs.
- **vs_reference: 3+ player games.** v1 assumes 2-player matchups. Multi-player vs_reference is non-trivial: which slots get reference opponents, how to attribute wins, how to handle position rotation. Defer until we have a concrete 3-player experiment in mind.