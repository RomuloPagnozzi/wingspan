"""Optuna study runner: orchestrates trials, persists study + trials.csv."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import optuna
import yaml
from tqdm import tqdm

from lab.data import generate_run_id
from lab.tune.merge import merge_study
from lab.tune.objective import _build_arm_config, run_trial
from lab.tune.space import ParamSpec, parse_space, sample_params

TRIALS_CSV_NAME = "trials.csv"
STUDY_DB_NAME = "study.db"
BEST_PARAMS_NAME = "best_params.yaml"
CONFIG_COPY_NAME = "config.yaml"


def _make_sampler(cfg: dict) -> optuna.samplers.BaseSampler:
    name = cfg.get("name", "tpe")
    seed = cfg.get("seed")
    if name == "tpe":
        return optuna.samplers.TPESampler(seed=seed, multivariate=True)
    if name == "random":
        return optuna.samplers.RandomSampler(seed=seed)
    raise ValueError(f"unknown sampler {name!r} (expected tpe|random)")


def _make_pruner(cfg: dict | None) -> optuna.pruners.BasePruner:
    if cfg is None or cfg.get("name") == "none":
        return optuna.pruners.NopPruner()
    name = cfg["name"]
    if name == "median":
        return optuna.pruners.MedianPruner(
            n_startup_trials=cfg.get("n_startup_trials", 5),
            n_warmup_steps=cfg.get("n_warmup_steps", 5),
        )
    if name == "asha":
        return optuna.pruners.SuccessiveHalvingPruner(
            min_resource=cfg.get("min_resource", 5),
            reduction_factor=cfg.get("reduction_factor", 3),
        )
    if name == "hyperband":
        return optuna.pruners.HyperbandPruner(
            min_resource=cfg.get("min_resource", 5),
            max_resource=cfg.get("max_resource", "auto"),
            reduction_factor=cfg.get("reduction_factor", 3),
        )
    raise ValueError(f"unknown pruner {name!r}")


def validate_tune_config(config: dict) -> None:
    """Light validation; surface obvious mistakes early."""
    for key in ("study_name", "n_trials", "seeds", "space"):
        if key not in config:
            raise ValueError(f"tuning config: missing required key `{key}`")
    if not isinstance(config["space"], list) or not config["space"]:
        raise ValueError("tuning config: `space` must be a non-empty list")
    seeds = config["seeds"]
    if "count" not in seeds:
        raise ValueError("tuning config: `seeds.count` is required")
    if config.get("base") and not isinstance(config["base"], dict):
        raise ValueError("tuning config: `base` must be a mapping")


class TrialsIndex:
    """Append-only CSV mapping trial_number → run_id → params → win_rate.

    This is the cross-reference between Optuna's trial space and the parquet
    `run_id` column. Read with pandas if needed.
    """

    HEADER = ["trial_number", "run_id", "state", "win_rate", "params_json"]

    def __init__(self, path: Path):
        self.path = path
        self._init_if_missing()

    def _init_if_missing(self):
        if not self.path.exists():
            with self.path.open("w", newline="") as f:
                csv.writer(f).writerow(self.HEADER)

    def append(
        self,
        trial_number: int,
        run_id: str,
        state: str,
        win_rate: float | None,
        params: dict[str, Any],
    ):
        with self.path.open("a", newline="") as f:
            csv.writer(f).writerow(
                [
                    trial_number,
                    run_id,
                    state,
                    "" if win_rate is None else f"{win_rate:.6f}",
                    json.dumps(params, default=str, sort_keys=True),
                ]
            )


def run_study(config: dict, study_dir: Path, source_yaml_path: Path | None = None):
    """Top-level entry: build study, run n_trials, persist results."""
    validate_tune_config(config)
    study_dir.mkdir(parents=True, exist_ok=True)

    if source_yaml_path is not None:
        (study_dir / CONFIG_COPY_NAME).write_bytes(source_yaml_path.read_bytes())

    specs: list[ParamSpec] = parse_space(config["space"])
    base = config.get("base", {}) or {}
    seeds_cfg = config["seeds"]
    seed_count = int(seeds_cfg["count"])
    seed_start = int(seeds_cfg.get("start", 1))
    num_workers = int(config.get("num_workers", 1))
    n_trials = int(config["n_trials"])

    sampler = _make_sampler(config.get("sampler", {}))
    pruner = _make_pruner(config.get("pruner"))

    storage = f"sqlite:///{study_dir / STUDY_DB_NAME}"
    study = optuna.create_study(
        study_name=config["study_name"],
        direction="maximize",
        sampler=sampler,
        pruner=pruner,
        storage=storage,
        load_if_exists=True,
    )

    index = TrialsIndex(study_dir / TRIALS_CSV_NAME)
    progress = tqdm(total=n_trials, desc="trials", unit="trial", dynamic_ncols=True)

    def objective(trial: optuna.Trial) -> float:
        sampled = sample_params(trial, specs)
        arm_cfg = _build_arm_config(base, sampled)
        run_id = generate_run_id()
        trial.set_user_attr("run_id", run_id)
        try:
            wr = run_trial(
                trial=trial,
                arm_cfg=arm_cfg,
                seed_count=seed_count,
                seed_start=seed_start,
                num_workers=num_workers,
                run_dir=study_dir,
                run_id=run_id,
            )
        except optuna.TrialPruned:
            # Record what we have; pruned trials still leave parquet on disk
            # and are referenced from trials.csv for later inspection.
            index.append(trial.number, run_id, "pruned", None, sampled)
            raise
        index.append(trial.number, run_id, "complete", wr, sampled)
        return wr

    def _on_trial_complete(study: optuna.Study, trial: optuna.trial.FrozenTrial):
        progress.update(1)
        best = study.best_trial
        progress.set_postfix_str(
            f"best={best.value:.3f} (trial #{best.number})"
            if best.value is not None
            else "best=?"
        )

    study.optimize(objective, n_trials=n_trials, callbacks=[_on_trial_complete])
    progress.close()

    _write_best_params(study, study_dir, base)
    counts = merge_study(study_dir)
    if any(counts.values()):
        parts = ", ".join(f"{k}: {n}" for k, n in counts.items() if n)
        print(f"Merged per-trial parquets → {study_dir} ({parts})")
    _print_summary(study)


def _write_best_params(study: optuna.Study, study_dir: Path, base: dict) -> None:
    try:
        best = study.best_trial
    except ValueError:
        return  # no completed trials
    payload = {
        "study_name": study.study_name,
        "best_trial_number": best.number,
        "best_win_rate": best.value,
        "best_run_id": best.user_attrs.get("run_id"),
        "params": {**base, **best.params},
    }
    with (study_dir / BEST_PARAMS_NAME).open("w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def _print_summary(study: optuna.Study) -> None:
    print(f"\n{'=' * 60}")
    print(f"STUDY {study.study_name!r} — {len(study.trials)} trials")
    print("=" * 60)
    try:
        best = study.best_trial
        print(f"Best trial: #{best.number}  win_rate={best.value:.3f}")
        for k, v in best.params.items():
            print(f"  {k} = {v}")
    except ValueError:
        print("No completed trials.")
