# Backlog

Prioritized work, top = next. Each item has a design vision and is one refinement away from implementation. Engineering specs are inline; experiment definitions live in `EXPERIMENTS.md` and are linked.

## Sprint order

1. IS-MCTS (opt-in determinization) — implementation done; remaining: `REFERENCE_PARAMS` decision after EXP-006
2. ~~In-place `transition_state` for IS-MCTS rewalk~~ — done (3.3× per-sim speedup)
3. ~~Game-level parallelism in the experiment harness~~ — done

---

## Specs

### Game-level parallelism in the experiment harness ✅ DONE

**What**: Switch experiment parallelism from sim-level (one game, N workers split the sims inside it) to game-level (N workers, each running an entire game single-threaded). Inside each game `MCTSConfig.num_workers = 1`; the harness owns the pool that distributes games across cores.

**Why**: At the current `num_workers=6, simulations=500` setting we observe ~75s/game, which matches the theoretical floor — each `pool.map` per move pickles the full `GameState` (170-card deck + 2 boards) to 6 workers and collects results back, paid 200 times per game. Game-level parallelism pays the pickle tax **once per game** instead of once per move. Estimated throughput win: ~5–6× on a 6-core box (200-game experiment: ~4 h → ~40 min). The MCTS internals stay untouched; this is purely a harness change.

#### Engineering spec

- New `lab/parallel.py` (or extend `lab/__main__.py`): a `multiprocessing.Pool` of game-workers using `spawn` context (consistent with the existing MCTS worker pattern).
- Worker entry point: `_run_one_game(args) -> (GameResult, GameDecisions | None)` where `args = (strategy_specs, game_seed, record_decisions)`. The worker reconstructs strategies from specs inside the subprocess (avoiding pickling un-initialized RNG state etc.) and calls `simulate_game`.
- Main thread iterates `generator`, submits to the pool via `imap_unordered` for backpressure, collects results, updates the tqdm progress bar, writes to `GamesWriter` / `DecisionsWriter`.
- New config knob: `defaults.game_parallelism: int = 1` (or top-level `game_workers`). When > 1, harness uses the game-pool; when = 1, current path. Coexists with per-strategy `num_workers` but **mutually exclusive at runtime** — using both would nest pools (subprocesses spawning subprocesses) and thrash.
- Validation: if any strategy spec sets `num_workers > 1` while `game_parallelism > 1`, fail loudly with a clear error pointing the user at the choice.

#### Determinism

- Game outcomes are determined by `(game_seed, mcts_seed)` per the existing contract. Game-level parallelism doesn't introduce new randomness — each subprocess constructs the same strategy with the same seeds and runs deterministically. `test_determinism.py` should still pass as-is.
- The *order* in which games complete is no longer deterministic (workers finish at different times), so `games.parquet` row order changes. This is fine: every analysis groups by `(strategy_config, game_seed)` and ignores append order. Add a note to the README.

#### Tests / verification

- Smoke: run `experiments/configs/test.yaml` (4 games) with `game_parallelism: 2` and verify identical scores per game vs sequential.
- Benchmark: re-run the EXP-006 config with `game_parallelism: 6` and confirm wall time drops to ~1/6 of the sequential run.

#### Sequencing

- [x] Removed sim-level parallelism from `MCTSStrategy` (no more pool, `__enter__`/`__exit__`, `MCTSConfig.num_workers`)
- [x] Harness refactor: `_iter_results` branches on `num_workers`; `run_one_game` worker in `lab/simulation.py`; per-game metadata `(game_idx)` round-trips through the pool so attribution survives `imap_unordered` reordering
- [x] Migrated `num_workers` from `base`/`defaults` → top-level config key in YAMLs
- [x] Parallel-equivalence test (`lab/benchmarks/test_parallel_equivalence.py`) — byte-identical per-game results for both peek and IS-MCTS across `num_workers=1` vs `num_workers=2`
- [x] Smoke test confirmed end-to-end with tqdm streaming live A/B tallies

---

### In-place `transition_state` for IS-MCTS rewalk ✅ DONE

**What**: Add `transition_state_inplace(state, action) -> state` that applies the same phase/power/effect logic as `transition_state` but **mutates** the input state instead of copying it first. Use the in-place variant inside the IS-MCTS tree walk and rollout. Peek-MCTS continues to use the copying `transition_state` (its node states are cached and aliased).

**Why**: Profiling shows `_copy_player` dominating IS-MCTS runtime. Each IS-MCTS iteration does `redeterminize` (1 copy) + `D` walk steps (1 copy each) + rollout to terminal (~200 copies). The walk-step copies are pure waste — the redeterminized state is owned by exactly one simulation, no one else holds a reference, and it dies at backprop. Replacing those D copies with in-place mutations gives an estimated 5–10× per-sim speedup for IS-MCTS at typical tree depths.

#### Safety argument

A function can mutate its input iff the caller is the sole owner and the object's lifetime ends with the call chain. In IS-MCTS:
- `world_state = redeterminize(root_state, ...)` returns a fresh object via `copy_state` internally → single owner from the start.
- The tree (`ISMCTSNode`) caches no state.
- `world_state` flows down the walk → expand → simulate → backprop, then goes out of scope.
- Next iteration calls `redeterminize` again, producing a different fresh object.

So the only "leak" risk is `root_state` itself, which `redeterminize` already protects by copying before returning. ✓

In peek-MCTS by contrast, every `MCTSNode.state` is read by multiple future simulations descending through that node. Mutating would corrupt all of them. The copy is mandatory there.

#### Engineering spec

- Refactor `game/engine.py:transition_state` so its body operates on a state it receives, with the `copy_state(state)` call lifted to a thin outer wrapper:

```python
def transition_state(state, action):
    return transition_state_inplace(copy_state(state), action)

def transition_state_inplace(state, action):
    # current body of transition_state, minus the copy
```

- In `lab/strategies/mcts.py:_ismcts_iteration`, replace the walk's `transition_state(state, action)` with `transition_state_inplace(state, action)`. Also use the in-place variant in `_simulate_from_state` (the rollout phase is owned by this single sim).
- Peek-MCTS path unchanged — keeps calling `transition_state`.

#### Tests / verification

- Byte-equivalence: an existing IS-MCTS game played at fixed `(game_seed, mcts_seed)` must produce the same moves before and after this change (the underlying engine logic is unchanged; only the redundant copy is removed). `lab/benchmarks/test_ismcts.py::test_ismcts_is_deterministic_same_seeds` covers this implicitly; add an explicit "before vs after" check during development.
- Per-sim cost benchmark: re-run `benchmark_ismcts.py`. Expected: IS-MCTS per-sim cost drops to within ~5% of peek (or below — IS-MCTS may *win* at very deep trees because peek copies cached states during expansion too).
- Full test suite green.

#### Out of scope

- Removing `transition_state`'s outer copy entirely (would force every caller, including peek-MCTS and `play.py`, into in-place semantics). Not worth the global API change for the IS-MCTS optimization.

#### Sequencing

- [x] Refactored `transition_state` into thin wrapper + `transition_state_inplace`; peek path untouched
- [x] Added `_rollout_inplace` for IS-MCTS rollouts; swapped IS-MCTS walk + rollout to in-place
- [x] Byte-equivalence check: `(game_seed=1, mcts_seed=11, 30 sims)` produced identical SHA256 of move sequence before/after
- [x] 201/201 unit tests pass; `test_parallel_equivalence.py` still passes for both modes
- [x] `benchmark_ismcts.py`: ~4.8 µs → ~1.45 µs per sim — **3.3× per-sim speedup**. IS-MCTS now faster than peek (peek pays per-step copy in rollout; IS-MCTS pays one copy at redeterminize entry then mutates).

---

### IS-MCTS (opt-in determinization)

**What**: Add SO-ISMCTS (Single-Observer Information Set MCTS) as an opt-in mode of `MCTSStrategy` via `MCTSConfig.determinize: bool = False`. When `True`, MCTS re-determinizes the hidden game state (deck orders, opponents' hands, `state.rng` seed) at the start of each simulation, walks the tree under that fresh world, and merges statistics across worlds in a single tree. Peek mode (default) is unchanged.

**Why**: Current MCTS reads the engine's hidden state during simulation (`bird_deck` order, opponent hands, future `state.rng` outcomes). Its win rate therefore overstates real strength: at deployment an honest agent lacks that information. IS-MCTS gives the honest baseline. EXP-006 measures the cheat tax; the result determines whether `REFERENCE_PARAMS` switches to IS-MCTS, which gates Phase 2 experiments per `ROADMAP.md`. Links: EXP-006 in `EXPERIMENTS.md`.

**Naming note**: `EXPERIMENTS.md` (EXP-006, H4) and `INBOX.md` use "PIMC" colloquially for the same idea. The literature-correct name for what we're building — single tree, per-simulation determinization, statistics merged via action-keyed nodes — is IS-MCTS (Cowling et al. 2012). Strict PIMC (Long et al. 2010: K separate trees + voting) is dominated by IS-MCTS in the literature and not built. A related single-determinization baseline sits in `INBOX.md` as a possible follow-up.

#### Engineering spec

**1. `game/core/redeterminize.py`** — new module exposing:

```python
def redeterminize(state: GameState, perspective_player: int, rng: random.Random) -> GameState:
    """Return a new state consistent with perspective_player's information set,
    with the unseen card pool freshly shuffled and a fresh state.rng seed."""
```

Logic:
- `unseen_birds = BIRD_REGISTRY.keys() − bird_tray − discarded_birds − all_placed_birds − perspective.bird_hand − perspective-owned cards in execution.context`
- Same for bonuses (`unseen_bonuses`); no board placement, no tray.
- Shuffle `unseen_birds` with `rng`. Slice `len(opponent.bird_hand)` for each opponent in player-index order; remainder becomes the new `bird_deck`. Likewise for bonuses.
- Reseed `new_state.rng` from `rng` (e.g. `random.Random(rng.getrandbits(64))`).
- Pure: returns a new state, mutates nothing.

**2. Tree restructure** in `lab/strategies/mcts.py`:
- `MCTSNode` drops `.state`. States are reconstructed per-simulation from the action path + the redeterminized root.
- Each iteration: redeterminize root → walk the tree from root, re-applying `transition_state` along the action path → at the leaf, expand/simulate as today.
- Selection filter: at each node, eligible children are those whose `action_taken` is legal in the current sim's world. Children illegal in this world stay in the tree (they were legal in some past world) but are skipped this iteration.
- Untried actions at a node = `get_actions(current_world_state) − children.keys()`.
- UCB1, backprop, and final visit-count action selection unchanged.
- When `determinize=False`, retain the existing fast path (states cached in nodes, no per-sim walk).

**3. `MCTSConfig.determinize: bool = False`** — additive field; auto-serializes into `games.parquet` via the existing `strategy_config` map.

#### Gotchas (from audit)

- **Cards in `execution.context`**: several power handlers stash drawn-but-unresolved card IDs in context dicts (`bonus_options`, `available_cards`, etc.). If the MCTS root is mid-power-execution, cards in the **perspective player's** executions are part of their info set (keep fixed); cards in **opponent's** executions are unseen (return to pool). `redeterminize` walks `state.action_data.execution_stack`, partitions context-cards by `execution.player_index`, and treats them accordingly.
- **Pool subtraction**: the unseen pool subtracts public locations + perspective's own hand, *not* opponent hands. Opponent hands are exactly what we're sampling out of the pool.

#### Determinism contract

- Redeterminization rng is `MCTSStrategy._rng` (driven by `mcts_seed`), not `state.rng`. Same `(game_seed, mcts_seed, determinize)` must produce identical moves.
- Extend `lab/benchmarks/test_determinism.py` with a `determinize ∈ {False, True}` axis.
- `test_reproducibility.py` must still pass byte-identically on the `determinize=False` path.

#### Tests

- `tests/test_redeterminize.py`:
  - Perspective player's `bird_hand`, `bonus_hand`, `board`, `food`, `score`, `action_cubes` preserved exactly.
  - Public state preserved exactly: `bird_tray`, `discarded_birds`, `discarded_bonuses`, `feeder`, `round_goal_config`, `round`, `current_player_index`, `game_phase`.
  - Card-count conservation: `len(BIRD_REGISTRY)` equals the sum of all bird locations after redeterminization. Same for bonuses.
  - Opponent hand *sizes* preserved; *identities* vary across distinct `rng` seeds.
  - Mid-power-execution case: perspective-owned context cards preserved; opponent-owned context cards returned to pool.
- `tests/test_ismcts.py`: smoke — 2p and 3p games run without error; per-sim action choice differs across rng seeds at the same root.
- Extend `lab/benchmarks/test_determinism.py` per above.

#### Out of scope (deferred)

- MO-ISMCTS (per-opponent trees with own info-set perspectives).
- Power-specific peeked-card tracking (a player who saw a card via a power effect is still treated as if they hadn't).
- Per-decision determinization mode (per-sim subsumes it for our purposes).
- Explicit chance nodes for `state.rng` events. Rng reseed handles this implicitly; explicit chance nodes are a future variance-reduction refinement (see INBOX).

#### Sequencing

- [x] GameState leak audit
- [x] `redeterminize` + tests (`game/core/redeterminize.py`, `tests/test_redeterminize.py`)
- [x] MCTS tree refactor behind `determinize` flag + smoke tests (`tests/test_ismcts.py`)
- [x] Extend `test_determinism.py` with `determinize=True` axis (cross-process determinism verified)
- [x] Benchmark IS-MCTS vs peek-MCTS per-sim cost (`lab/benchmarks/benchmark_ismcts.py`) — ~1.02–1.05× slowdown at 50–500 sims
- [ ] `REFERENCE_PARAMS` decision deferred to EXP-006 outcome

