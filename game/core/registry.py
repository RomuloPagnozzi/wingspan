from __future__ import annotations

from typing import TYPE_CHECKING, List, Dict
import random
import pickle

if TYPE_CHECKING:
    from .constants import BirdCard, Bonus

BIRD_REGISTRY: Dict[int, BirdCard] = {}
POWER_REGISTRY: Dict[int, Dict] = {}
BONUS_REGISTRY: Dict[int, Bonus] = {}
_REGISTRIES_INITIALIZED = False


def load_deck(type: str) -> List:
    """Load a deck from a pickle file and shuffle it."""
    deck = []
    with open(f"game/assets/{type}.pickle", "rb") as f:
        deck.extend(pickle.load(f))
    random.shuffle(deck)
    return deck


def load_powers() -> Dict:
    """Load powers data from powers.pickle"""
    with open("game/assets/powers.pickle", "rb") as f:
        return pickle.load(f)


def init_registries() -> None:
    """Initialize all card registries from pickle files."""
    global _REGISTRIES_INITIALIZED
    if _REGISTRIES_INITIALIZED:
        return

    for bird in load_deck("birds"):
        if bird.id not in BIRD_REGISTRY:
            BIRD_REGISTRY[bird.id] = bird

    for bird_id, power_data in load_powers().items():
        POWER_REGISTRY[bird_id] = power_data

    for bonus in load_deck("bonuses"):
        if bonus.id not in BONUS_REGISTRY:
            BONUS_REGISTRY[bonus.id] = bonus

    _REGISTRIES_INITIALIZED = True


def get_bird_card(bird_id: int) -> BirdCard | None:
    """Get frozen bird card from registry."""
    init_registries()
    return BIRD_REGISTRY.get(bird_id)


def get_bonus_card(bonus_id: int) -> Bonus | None:
    """Get frozen bonus card from registry."""
    init_registries()
    return BONUS_REGISTRY.get(bonus_id)


def get_bird_power(bird_id: int) -> Dict:
    """Get power data for a specific bird ID from registry."""
    init_registries()
    return POWER_REGISTRY.get(bird_id, {})
