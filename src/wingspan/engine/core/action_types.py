from __future__ import annotations

from dataclasses import dataclass


def frozen_map(d: dict) -> tuple[tuple, ...]:
    """Convert dict to sorted tuple-of-pairs for hashable action data.

    ALL dict-to-action conversions MUST use this function to ensure
    consistent ordering for equality and hashing.
    """
    return tuple(sorted(d.items()))


@dataclass(frozen=True, slots=True)
class SimpleAction:
    """Actions with no parameters."""

    type: str


@dataclass(frozen=True, slots=True)
class IdAction:
    """Actions targeting a single entity by integer ID."""

    type: str
    id: int


@dataclass(frozen=True, slots=True)
class NameAction:
    """Actions selecting a type by string name."""

    type: str
    name: str


@dataclass(frozen=True, slots=True)
class PlayBirdAction:
    """Play a bird card at a specific board position."""

    bird_id: int
    row: int
    col: int


@dataclass(frozen=True, slots=True)
class SelectDieAction:
    """Select a die from the bird feeder."""

    die_index: int
    food_type: str


@dataclass(frozen=True, slots=True)
class TradeAction:
    """Trade one food type for another."""

    from_type: str
    to_type: str


@dataclass(frozen=True, slots=True)
class FoodMapAction:
    """Actions involving a food-type-to-amount mapping."""

    type: str
    items: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class EggMapAction:
    """Actions involving a bird-id-to-egg-count mapping."""

    type: str
    items: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class DrawCardsAction:
    """Draw cards from tray and/or deck."""

    tray_birds: tuple[int, ...]
    deck_count: int


@dataclass(frozen=True, slots=True)
class SelectInitialAction:
    """Select initial birds and bonus card during setup."""

    kept_birds: tuple[int, ...]
    kept_bonus: int


Action = (
    SimpleAction
    | IdAction
    | NameAction
    | PlayBirdAction
    | SelectDieAction
    | TradeAction
    | FoodMapAction
    | EggMapAction
    | DrawCardsAction
    | SelectInitialAction
)
