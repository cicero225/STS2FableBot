"""Spirebird shop ratings: relic / card value-per-gold (WAR/100g) and card-removal
value, keyed by the live ShopItem relic_id / card_id. Built by scripts/build_shop_stats.py;
data/shop_stats.json is committed so shop decisions are reproducible. The cohort export
(priors_cards.json) lacks price, so this is the only source of "is it worth the gold."
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SHOP_STATS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "shop_stats.json"
)


class ShopStats:
    def __init__(
        self,
        removal: list[dict] | None = None,
        relics: dict[str, dict] | None = None,
        cards: dict[str, dict] | None = None,
        meta: dict | None = None,
    ):
        self.removal = removal or []
        self.relics = relics or {}
        self.cards = cards or {}
        self.meta = meta or {}

    @classmethod
    def load(cls, path: Path | str | None = None) -> ShopStats | None:
        p = Path(path) if path else DEFAULT_SHOP_STATS_PATH
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(d.get("removal"), d.get("relics"), d.get("cards"), d.get("meta"))

    def relic_value(self, relic_id: str | None) -> float | None:
        """Value-per-gold (WAR/100g) of buying this relic at a shop; None if unknown.
        Negative = a bad buy at its price (e.g. Book Repair Knife)."""
        r = self.relics.get((relic_id or "").upper())
        return r.get("war_per_100g") if r else None

    def card_value(self, card_id: str | None) -> float | None:
        c = self.cards.get((card_id or "").upper())
        return c.get("war_per_100g") if c else None

    def removal_value(self) -> float | None:
        """Representative value-per-gold for card removal (the cheap early removals,
        which is what the bot is usually deciding on)."""
        early = [r["war_per_100g"] for r in self.removal[:3] if r.get("war_per_100g") is not None]
        return sum(early) / len(early) if early else None
