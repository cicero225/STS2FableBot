"""Distil the Spirebird 'Shops' sheet into data/shop_stats.json.

The Spirebird export (cohort_stats.json) has cards/relics/events but NOT the shop
sheet, which uniquely carries *price* and *value-per-gold* (WAR/100g) plus the
card-removal ratings. That sheet is pasted (headerless TSV, columns known from the
site) into data/spirebird/shops_sheet_copy_paste.txt; this script normalizes it to
relic_id/card_id keys the live ShopItem model uses, so the shop policy can rank buys.

Run: .venv\\Scripts\\python.exe scripts/build_shop_stats.py
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

SRC = Path("data/spirebird/shops_sheet_copy_paste.txt")
OUT = Path("data/shop_stats.json")

# Headerless paste; column order from the site (see the Shops sheet):
# 0:#  1:Item  2:Kind  3:Seen  4:Bought  5:dPSkill  6:Win%  7:dWSkill
# 8:WAR  9:WAR/ea  10:cWAR  11:cWAR/ea  12:Gold  13:SumGold  14:WAR/100g
ITEM, KIND, SEEN, BOUGHT, WIN, WAR, GOLD, WAR100 = 1, 2, 3, 4, 6, 8, 12, 14


def _num(s: str) -> float | None:
    s = s.replace("%", "").replace("g", "").replace("+", "").replace(",", "").strip()
    try:
        return float(s)  # the missing-value dash falls through to None
    except ValueError:
        return None


def _to_id(name: str) -> str:
    """Match the live ShopItem relic_id/card_id form: UPPER_SNAKE, apostrophes dropped."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper().replace("'", "")).strip("_")


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    rows = [ln.rstrip("\n").split("\t") for ln in lines if ln.strip()]
    removal: list[dict] = []
    relics: dict[str, dict] = {}
    cards: dict[str, dict] = {}
    for r in rows:
        if len(r) <= WAR100:
            continue
        kind = r[KIND]
        rec = {
            "win": (_num(r[WIN]) or 0) / 100 if _num(r[WIN]) is not None else None,
            "war": _num(r[WAR]),
            "gold": _num(r[GOLD]),
            "war_per_100g": _num(r[WAR100]),
        }
        if kind == "Removal":
            m = re.search(r"#(\d+)", r[ITEM])
            rec["n"] = int(m.group(1)) if m else len(removal) + 1
            removal.append(rec)
        elif kind == "Relic":
            relics[_to_id(r[ITEM])] = rec
        elif kind in ("Card", "Colorless"):
            cards[_to_id(r[ITEM])] = rec
    removal.sort(key=lambda x: x.get("n", 0))
    OUT.write_text(
        json.dumps(
            {
                "meta": {
                    "source": "spirebird shops sheet",
                    "generated": datetime.now(UTC).isoformat(),
                    "rows": len(rows),
                    "counts": {
                        "removal": len(removal),
                        "relics": len(relics),
                        "cards": len(cards),
                    },
                },
                "removal": removal,
                "relics": relics,
                "cards": cards,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT}: {len(removal)} removal, {len(relics)} relics, {len(cards)} cards")


if __name__ == "__main__":
    main()
