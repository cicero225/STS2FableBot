"""The bot's own HP loss per fight type (from scripts/build_combat_stats.py).

Feeds the rest-vs-smith decision: rest only when a fight type might not be survivable
to the next heal, else smith. data/combat_stats.json is committed and regenerated as
runs accumulate, so the estimate tracks how the current policy actually performs.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "combat_stats.json"


class CombatStats:
    def __init__(self, by_type: dict[str, dict]):
        self.by_type = by_type

    @classmethod
    def load(cls, path: Path | str | None = None) -> CombatStats | None:
        p = Path(path) if path else DEFAULT_PATH
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(by_type=data.get("fight_hp_loss", {}))

    def expected_loss(
        self, fight_type: str, stat: str = "p75", min_samples: int = 3
    ) -> float | None:
        """HP typically lost to a fight type (default the conservative p75). None when
        too few samples to trust — callers fall back to a configured default."""
        s = self.by_type.get(fight_type)
        if not s or s.get("n", 0) < min_samples:
            return None
        return s.get(stat)
