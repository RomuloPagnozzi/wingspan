"""Optuna-driven joint hyperparameter search over MCTSConfig knobs.

Reuses the existing paired-seed harness (one trial == N vs_reference paired
games against REFERENCE_PARAMS). Optuna replaces the YAML enumeration of
which configs to evaluate; paired comparisons remain the noise-reduction
primitive. See INBOX.md "Optuna-driven joint hyperparameter search".
"""
