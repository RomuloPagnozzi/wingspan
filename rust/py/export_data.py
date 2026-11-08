"""Export the card registries (pickles) to JSON for the Rust engine. Run once; rerun if the assets change.

    uv run python rust/py/export_data.py
"""

import json
from pathlib import Path

from wingspan.engine.core.models import BIRD_REGISTRY, BONUS_REGISTRY, POWER_REGISTRY, init_registries

OUT = Path(__file__).parent.parent / "data"

init_registries()
birds = [
    {
        "id": b.id,
        "habitats": list(b.habitats),
        "cost": [[list(item) for item in option] for option in b.cost],
        "points": b.points,
        "nest": b.nest if isinstance(b.nest, str) else "none",  # two cowbirds have no nest (nan)
        "egg_limit": b.egg_limit,
        "color": color if isinstance(color := POWER_REGISTRY.get(b.id, {}).get("color"), str) else None,
    }
    for b in BIRD_REGISTRY.values()  # registry order = initial deck order
]
bonuses = [
    {"id": b.id, "valid_birds": sorted(b.valid_birds_ids or ()), "score_params": b.score_params}
    for b in BONUS_REGISTRY.values()
]
(OUT / "birds.json").write_text(json.dumps(birds, indent=1))
(OUT / "bonuses.json").write_text(json.dumps(bonuses, indent=1))
(OUT / "powers.json").write_text(  # NaN (birds without a power) -> null
    json.dumps({str(k): v for k, v in POWER_REGISTRY.items()}, indent=1).replace("NaN", "null")
)
print(f"{len(birds)} birds, {len(bonuses)} bonuses -> {OUT}")
