"""The roster of AI opponents the web app can field (bots.yaml)."""

from pathlib import Path

import yaml

_ROSTER = yaml.safe_load((Path(__file__).parent / "bots.yaml").read_text())
CHAMPION: str = _ROSTER["champion"]
BOTS: dict[str, dict] = {bot_id: {"id": bot_id, **bot} for bot_id, bot in _ROSTER["bots"].items()}
