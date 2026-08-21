"""Build data/card_catalog.json for the card pass (CARD_PASS.md step 0).

Ground truth = the mod's own endpoints on the running game:
  - GET /api/v1/compendium -> card_library.discovered_ids (+ per-card pick/win stats)
  - GET /api/v1/wiki?q=<id> -> full entry: base AND upgraded rules text, type, rarity, keywords

Character tag from the Spirebird priors' per-character tables (a card in exactly one
character's table = that character; in none = colorless/status/curse/other). Exposure =
compendium stats + Spirebird pick-weight where present. Re-run after unlocks (the wiki
serves only discovered cards — which is also exactly what can be offered to this profile).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "card_catalog.json"
BASE = "http://127.0.0.1:15526/api/v1"


def main() -> int:
    with httpx.Client(timeout=15) as client:
        comp = client.get(f"{BASE}/compendium").json()
        lib = comp["sections"]["card_library"]
        ids: list[str] = lib["discovered_ids"]
        stats = {s["id"]: s for s in lib.get("stats", [])}

        priors = json.loads((ROOT / "data" / "priors_cards.json").read_text(encoding="utf-8"))
        char_of: dict[str, str] = {}
        for character, table in priors.get("cards", {}).items():
            for cid in table:
                # a card in several tables (colorless) ends up tagged by the last one;
                # fix up below by counting
                char_of.setdefault(cid, character)
        multi = {
            cid for cid in char_of
            if sum(cid in t for t in priors.get("cards", {}).values()) > 1
        }

        catalog: dict[str, dict] = {}
        misses: list[str] = []
        # OWNER-AUTHORITATIVE character overrides (2026-08-18): the multi-table
        # heuristic mislabels cross-character cards as COLORLESS (Prismatic Gem
        # runs put off-class cards in many characters' Spirebird tables). The
        # API exposes no color field (wiki + compendium probed), so the owner's
        # mapping is ground truth. Extend as more mislabels surface.
        # Star costs (owner catch 2026-08-20, Cloak of Stars): the wiki
        # endpoint exposes NO star_cost field, so the catalog was blind to
        # star economy -- the audit mis-read Cloak of Stars as a free block
        # card. Ground truth = live payloads (deck/reward cards carry
        # star_cost); verified values are pinned here. TODO: probe the wiki
        # base dict for a star field next time the game is up.
        star_costs = {"CLOAK_OF_STARS": "1"}
        overrides = {
            "INFERNO": "IRONCLAD", "TEAR_ASUNDER": "IRONCLAD",
            "THE_SMITH": "REGENT", "CRUSH_UNDER": "REGENT", "ALIGNMENT": "REGENT",
            "REAVE": "NECROBINDER", "PAGESTORM": "NECROBINDER",
            "UPROAR": "DEFECT", "HOTFIX": "DEFECT", "BALL_LIGHTNING": "DEFECT",
            "COLD_SNAP": "DEFECT", "CHAOS": "DEFECT", "CAPACITOR": "DEFECT",
            "DODGE_AND_ROLL": "SILENT",
            "PREP_TIME": "COLORLESS",  # legitimately colorless (owner)
        }
        for cid in ids:
            r = client.get(f"{BASE}/wiki", params={"q": cid, "item_type": "card"}).json()
            entry = next(
                (x for x in r.get("results", [])
                 if x.get("item_type") == "card" and x.get("id") == cid),
                None,
            )
            if entry is None:
                misses.append(cid)
                continue
            base = entry.get("base") or {}
            upg = entry.get("upgraded") or {}
            character = overrides.get(
                cid, "COLORLESS" if cid in multi else char_of.get(cid, "NONE"))
            st = stats.get(cid, {})
            catalog[cid] = {
                "name": entry.get("name"),
                "type": entry.get("type"),
                "rarity": entry.get("rarity"),
                "character": character,
                "star_cost": star_costs.get(cid),
                "cost": base.get("cost"),
                "text": base.get("description"),
                "cost_upgraded": upg.get("cost"),
                "text_upgraded": upg.get("description"),
                "keywords": [k.get("name") for k in base.get("keywords") or []],
                "exposure": {
                    "times_picked": st.get("times_picked", 0),
                    "times_won": st.get("times_won", 0),
                    "times_lost": st.get("times_lost", 0),
                },
            }

    OUT.write_text(
        json.dumps({"source": "compendium+wiki (mod, live)", "cards": catalog},
                   indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    by_char: dict[str, int] = {}
    for c in catalog.values():
        by_char[c["character"]] = by_char.get(c["character"], 0) + 1
    print(f"wrote {len(catalog)} cards to {OUT.name}; wiki misses: {len(misses)}")
    print("by character:", dict(sorted(by_char.items())))
    if misses:
        print("missed ids:", misses[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
