"""Observed HP cost of event fights per (event, option) -- built by
scripts/build_event_fight_stats.py from the bot's own run logs.

The event policy's HP-cost gate prices a fight option with the p75 loss of the
fight that option leads to (owner note on the Lantern Key: 'hp-gated'), instead
of the generic hallway mean it used before (Mysterious Knight: 30 mean / 41 p75
vs a ~10 hallway; Dense Vegetation's 'Rest' is a Wriggler ambush that never says
'fight'). Options with too few samples fall back to the old pricing.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "event_fight_stats.json"


class EventFightStats:
    def __init__(self, options: dict[str, dict] | None = None, min_samples: int = 10):
        self.options = options or {}
        self.min_samples = min_samples

    @classmethod
    def load(cls, path: Path | str | None = None) -> EventFightStats | None:
        p = Path(path) if path else DEFAULT_PATH
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(d.get("options"))

    def cost(self, event_id: str | None, option_title: str | None) -> dict | None:
        """The observed fight-loss record for this option, or None when unknown or
        thin (< min_samples)."""
        info = self.options.get(f"{(event_id or '').upper()}|{option_title or ''}")
        if not info or info.get("n", 0) < self.min_samples:
            return None
        return info
