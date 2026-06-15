"""Community card priors (distilled from the Spirebird cohort export).

Each entry is {"s": score, "a": [tilt1, tilt2, tilt3]}:
- s: shrunk Elo delta, roughly -8..+8, 0 = replacement-level pick.
- a: per-act tilt (8.1b) — how much better/worse the card performs in each act vs.
     its own average, de-biased and zero-centered, bounded ~+-1.
Built by scripts/build_priors.py; data/priors_cards.json is committed so runs are
reproducible against a known priors snapshot. (A plain float entry is also accepted
as a bare score, for hand-built test priors.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PRIORS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "priors_cards.json"

CHARACTER_NAME_TO_ID = {
    "The Ironclad": "IRONCLAD",
    "The Silent": "SILENT",
    "The Defect": "DEFECT",
    "The Regent": "REGENT",
    "The Necrobinder": "NECROBINDER",
}


class CardPriors:
    def __init__(self, by_character: dict[str, dict[str, Any]], meta: dict | None = None):
        self.by_character = by_character
        self.meta = meta or {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> CardPriors | None:
        priors_path = Path(path) if path else DEFAULT_PRIORS_PATH
        if not priors_path.exists():
            return None
        data = json.loads(priors_path.read_text(encoding="utf-8"))
        return cls(by_character=data.get("cards", {}), meta=data.get("meta", {}))

    def _entry(self, card_id: str | None, character: str | None) -> Any:
        if not card_id or not character:
            return None
        char_id = CHARACTER_NAME_TO_ID.get(character, character).upper()
        return self.by_character.get(char_id, {}).get(card_id.upper())

    def score(self, card_id: str | None, character: str | None) -> float | None:
        """Prior score; `character` accepts id ('IRONCLAD') or display name."""
        entry = self._entry(card_id, character)
        if entry is None:
            return None
        return float(entry) if isinstance(entry, int | float) else entry.get("s")

    def act_tilt(self, card_id: str | None, character: str | None, act: int) -> float:
        """Per-act tilt for the current act (1-3); 0.0 if no reliable act data."""
        entry = self._entry(card_id, character)
        if not isinstance(entry, dict):
            return 0.0
        tilts = entry.get("a")
        if not tilts:
            return 0.0
        return float(tilts[max(1, min(3, act)) - 1])
