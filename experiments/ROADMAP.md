# Wingspan Project Roadmap

Long-term plan for the project, from the current state (engine complete, experiment harness scaffolded) through the AlphaZero-style NN end state. Companion to `EXPERIMENTS.md` (research hypotheses & queue) and `TODO.md` (engineering items).

## Project goal

Build the strongest possible Wingspan player via the AlphaZero recipe — MCTS for game data generation, NN trained on that data, iterative self-play improvement. Secondary research aim: characterize the compute-efficiency frontier for this recipe at small compute budgets, which is the contribution of the eventual paper.

---

## How ablations fit

All MCTS optimizations (PIMC, score-aware rollouts, K-step rollouts, PUCT, action canonicalization, etc.) must be implemented as **feature flags on `MCTSConfig`** — not as separate strategy classes. Two reasons:

1. Any combination of flags can be run through the same code path, including the full factorial (2^N).
2. The flag values auto-serialize into each row of `games.parquet`, so analysis is just *"group by config columns, win rate vs reference."*

Every ablation experiment evaluates against the **same fixed reference opponent** (e.g., MCTS at default config / 500 sims / seed 0). This means win rates from different experiments live on a common scale and are directly comparable — necessary for stacking "A is worth +X%, B is worth +Y%" claims.

Subtlety to keep in mind: ablations measure marginal contributions, but subset-sums don't always equal the whole. Two optimizations can overlap (sum > whole) or synergize (whole > sum). The factorial design exposes this; per-optimization *"+N%"* numbers hide it. For the paper, report both the one-at-a-time marginal effects and the full subset matrix.

---

## Phases

```
Phase 0 — Commit and stabilize           [this week]
Phase 1 — Foundation for ablations       [1–2 weeks]
Phase 2 — MCTS strength frontier         [the main experimental work]
Phase 3 — Mass game generation           [compute-bound, low-touch]
Phase 4 — NN bootstrap and self-play     [the AlphaZero phase]
```

**Phase 0 — Commit and stabilize.** Land everything uncommitted (`lab/`, `experiments/`, `CLAUDE.md`, READMEs, expanded `test_determinism.py`, dependency bumps). Establish the safety net.

**Phase 1 — Foundation for ablations.** Do *not* run real experiments before this is done. Expand `decisions.parquet` to capture observable state + turn context + MCTS metadata (the "Generate training data for NN" TODO). Rewrite `analysis.py` for the parquet schema. Scaffold `MCTSConfig` with feature flags for every planned optimization (empty stubs are fine). Pick the reference opponent. The investment pays for itself the first time you re-run an experiment instead of re-collecting data.

**Phase 2 — MCTS strength frontier.** Run EXP-001 through EXP-007 as an ablation matrix over the Phase 1 flags. Output: a quantified "what matters how much" table + the best-config MCTS player.

**Phase 3 — Mass game generation.** Use best-config MCTS to generate the bootstrap dataset. Long compute, mostly waiting. Validates the determinism + reproducibility guarantees at scale.

**Phase 4 — NN bootstrap and self-play.** EXP-008 plus the NN architecture work, plus iterative self-play after the initial bootstrap. The eventual paper is written from results here.

The boundary that matters: **do not cross Phase 1 → Phase 2** until the data infrastructure is right. Every experiment run before the schema is final is data you'll likely have to throw away.

---

## Short-term — the next four things, in order

1. **Commit what's uncommitted.** `lab/`, `experiments/`, `CLAUDE.md`, the new READMEs, expanded `test_determinism.py`, `pyproject.toml` + `uv.lock`. Gitignore `experiments/data/*.parquet` — those are throwaway smoke-test outputs.

2. **Expand `DECISIONS_SCHEMA`** in `lab/data.py` per the "Generate training data for NN" TODO. Surgical change; unblocks everything downstream. Bump `schema_version` from day one.

3. **Rewrite `analysis.py`** for the new parquet schema. Replaces the dead CSV-era code; targets the data you're about to start producing. Unblocks running *and interpreting* experiments.

4. **Add a reference-opponent helper** in `lab/generators.py` — small `vs_reference` mode that pairs each strategy against a fixed baseline. This is what makes ablations comparable across runs.

After those four: EXP-004 (first-player advantage) is a quick sanity check; EXP-001 (sim scaling) is the first real experiment.

---

## Status conventions

When checking back into this file, the convention is:

- A phase is **in progress** when its first task is started.
- A phase is **complete** when every task it gates is checkable (e.g., Phase 1 is complete when `decisions.parquet` has the new schema, `analysis.py` works against it, `MCTSConfig` has the flags, and the reference opponent is picked).
- Add dated notes under each phase as it progresses; promote completed items to `EXPERIMENTS.md` under "Completed Experiments" where applicable.
