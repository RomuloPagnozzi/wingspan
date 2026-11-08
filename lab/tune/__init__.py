"""Optuna-driven joint hyperparameter search over any registered strategy's params.

One trial == N seeds against a reference, each seed played from both seats (the `vs_reference`
games). The candidate is `base` (a strategy spec; `strategy` defaults to `mcts`) plus the sampled
params; the reference is the config's `reference` spec, or REFERENCE_PARAMS. Strategies backed by
the Rust engine (`mcts_rs`, `flat_mc_rs`) work like any other. Optuna replaces the YAML enumeration
of which configs to evaluate; paired seeds remain the noise-reduction primitive.
"""
