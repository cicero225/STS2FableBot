"""Community card priors (distilled from the Spirebird cohort export).

Scores are shrunk Elo deltas, roughly -8..+8 with 0 = replacement-level pick.
Built by scripts/build_priors.py; data/priors_cards.json is committed so runs
are reproducible against a known priors snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PRIORS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "priors_cards.json"

CHARACTER_NAME_TO_ID = {
    "The Ironclad": "IRONCLAD",
    "The Silent": "SILENT",
    "The Defect": "DEFECT",
    "The Regent": "REGENT",
    "The Necrobinder": "NECROBINDER",
}


class CardPriors:
    def __init__(self, by_character: dict[str, dict[str, float]], meta: dict | None = None):
        self.by_character = by_character
        self.meta = meta or {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> CardPriors | None:
        priors_path = Path(path) if path else DEFAULT_PRIORS_PATH
        if not priors_path.exists():
            return None
        data = json.loads(priors_path.read_text(encoding="utf-8"))
        return cls(by_character=data.get("cards", {}), meta=data.get("meta", {}))

    def score(self, card_id: str | None, character: str | None) -> float | None:
        """Prior for a card; `character` accepts id ('IRONCLAD') or display name."""
        if not card_id or not character:
            return None
        char_id = CHARACTER_NAME_TO_ID.get(character, character).upper()
        return self.by_character.get(char_id, {}).get(card_id.upper())
