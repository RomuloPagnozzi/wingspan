# Wingspan Project Roadmap

Long-term plan for the project, from the current state (engine complete, experiment harness scaffolded) through the AlphaZero-style NN end state. Big-picture vision only — sprint-level work lives in `BACKLOG.md`; capture-only ideas live in `INBOX.md`; experiment definitions and results live in `EXPERIMENTS.md`.

## Project goal

Build the strongest possible Wingspan player via the AlphaZero recipe — MCTS for game data generation, NN trained on that data, iterative self-play improvement. Secondary research aim: characterize the compute-efficiency frontier for this recipe at small compute budgets, which is the contribution of the eventual paper.

---

## How ablations fit

All MCTS optimizations (PIMC, score-aware rollouts, K-step rollouts, PUCT, action canonicalization, etc.) must be implemented as **feature flags on `MCTSConfig`** — not as separate strategy classes. Two reasons:

1. Any combination of flags can be run through the same code path, including the full factorial (2^N).
2. The flag values auto-serialize into each row of `games.parquet`, so analysis is just *"group by config columns, win rate vs reference."*

Every ablation experiment evaluates against the **same fixed reference opponent** (`REFERENCE_PARAMS` in `lab/generators.py`). This means win rates from different experiments live on a common scale and are directly comparable — necessary for stacking "A is worth +X%, B is worth +Y%" claims. The current reference is *provisional* (peek-MCTS at 500 sims); the final choice depends on EXP-006's peek-vs-PIMC outcome.

Subtlety to keep in mind: ablations measure marginal contributions, but subset-sums don't always equal the whole. Two optimizations can overlap (sum > whole) or synergize (whole > sum). The factorial design exposes this; per-optimization *"+N%"* numbers hide it. For the paper, report both the one-at-a-time marginal effects and the full subset matrix.

---

## Phases

```
Phase 1 — Foundation for ablations       [1–2 weeks]
Phase 2 — MCTS strength frontier         [the main experimental work]
Phase 3 — Mass game generation           [compute-bound, low-touch]
Phase 4 — NN bootstrap and self-play     [the AlphaZero phase]
```

**Phase 1 — Foundation for ablations.** Do *not* run real strength-sensitive experiments before this is done. Rewrite `analysis.py` for the new parquet schema. PIMC needs to land (see `BACKLOG.md`) and EXP-006 (peek vs PIMC) needs to run before the project-wide reference is finalized — only then are cross-experiment win rates trustworthy. The experiment harness supports `vs_reference`, `paired`, and `continuous` modes; strategy hyperparams auto-serialize via the flexible `strategy_config` map so new MCTS flags need no schema work; observable game state at any decision is reconstructed by replaying the action log through the engine — no per-decision state snapshot to store. The investment pays for itself the first time you re-run an experiment instead of re-collecting data.

**Phase 2 — MCTS strength frontier.** Run EXP-001 through EXP-007 as an ablation matrix over the Phase 1 flags. Output: a quantified "what matters how much" table + the best-config MCTS player.

**Phase 3 — Mass game generation.** Use best-config MCTS to generate the bootstrap dataset. Long compute, mostly waiting. Validates the determinism + reproducibility guarantees at scale.

**Phase 4 — NN bootstrap and self-play.** EXP-008 plus the NN architecture work, plus iterative self-play after the initial bootstrap. The eventual paper is written from results here.

The boundary that matters: **do not cross Phase 1 → Phase 2** until the data infrastructure is right. Every experiment run before the schema is final is data you'll likely have to throw away.
