"""YAML search-space → Optuna `trial.suggest_*` calls.

A space YAML lists the params to sweep. Each entry is one of:

  - name: exploration_constant
    type: float
    low: 0.3
    high: 3.0
    log: true            # optional, default false

  - name: simulations
    type: int
    low: 200
    high: 4000
    step: 100            # optional
    log: false           # optional

  - name: value_function
    type: categorical
    choices: [score_delta, win_loss, absolute_score]

Anything not listed in `space` falls back to the `base` block, which is a
literal MCTSConfig partial. Together they form the full per-trial config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import optuna


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str  # "float" | "int" | "categorical"
    low: float | int | None = None
    high: float | int | None = None
    step: float | int | None = None
    log: bool = False
    choices: list[Any] | None = None


def parse_space(space_yaml: list[dict]) -> list[ParamSpec]:
    """Parse the `space:` list from YAML into ParamSpec objects."""
    specs = []
    for i, entry in enumerate(space_yaml):
        if "name" not in entry or "type" not in entry:
            raise ValueError(f"space[{i}]: missing `name` or `type` (got {entry!r})")
        t = entry["type"]
        if t in ("float", "int"):
            if "low" not in entry or "high" not in entry:
                raise ValueError(
                    f"space[{i}] ({entry['name']}): `{t}` requires `low` and `high`"
                )
            specs.append(
                ParamSpec(
                    name=entry["name"],
                    type=t,
                    low=entry["low"],
                    high=entry["high"],
                    step=entry.get("step"),
                    log=entry.get("log", False),
                )
            )
        elif t == "categorical":
            if not entry.get("choices"):
                raise ValueError(
                    f"space[{i}] ({entry['name']}): `categorical` requires non-empty `choices`"
                )
            specs.append(
                ParamSpec(name=entry["name"], type=t, choices=list(entry["choices"]))
            )
        else:
            raise ValueError(
                f"space[{i}] ({entry['name']}): unknown type {t!r} "
                "(expected float|int|categorical)"
            )
    return specs


def sample_params(trial: optuna.Trial, specs: list[ParamSpec]) -> dict[str, Any]:
    """Call the right `trial.suggest_*` for each spec, return param dict."""
    out: dict[str, Any] = {}
    for s in specs:
        if s.type == "float":
            out[s.name] = trial.suggest_float(
                s.name, s.low, s.high, step=s.step, log=s.log
            )
        elif s.type == "int":
            out[s.name] = trial.suggest_int(
                s.name, int(s.low), int(s.high), step=int(s.step or 1), log=s.log
            )
        elif s.type == "categorical":
            out[s.name] = trial.suggest_categorical(s.name, s.choices)
    return out
