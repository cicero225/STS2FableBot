"""Deck/run-state feature extraction for the PLAN §9 value heads.

Cards enter as FEATURES, not IDs (patch/class transfer): generic aggregates
from the card catalog (type mix, cost curve, upgrade fraction) plus the tag
table's provides-counts — the same lens drafting uses (drafttags pseudo-tags
via deck_tag_weights + real-tag provides mirroring _providers' upgrade and
innate rules), so learned heads and the hand-tuned scorer read the deck the
same way.

Dataset rows (scripts/build_run_dataset.py) store decks as compact "ID+"
keys; _CardShim adapts those to the getattr protocol drafttags expects,
enriched with type/cost/description from the card catalog (the pseudo-tags
__skills/__attacks/__curses read those fields).
"""

from __future__ import annotations

from sts2bot.policy.drafttags import INNATE_PROVIDER_MULT, deck_tag_weights


class _CardShim:
    __slots__ = ("cost", "description", "id", "is_upgraded", "name", "type")

    def __init__(self, key: str, catalog: dict[str, dict] | None = None):
        self.is_upgraded = key.endswith("+")
        self.id = key.rstrip("+")
        # deck listings carry display names; keys don't — the id is close
        # enough for the name-based pseudo-tags (strike-named checks the id too)
        self.name = self.id.replace("_", " ").title()
        entry = (catalog or {}).get(self.id) or {}
        self.type = entry.get("type") or ""
        self.cost = (entry.get("cost_upgraded") if self.is_upgraded
                     else entry.get("cost")) or entry.get("cost") or ""
        self.description = (
            (entry.get("text_upgraded") if self.is_upgraded
             else entry.get("text")) or entry.get("text") or "")


def cards_from_keys(
    keys: list[str], catalog: dict[str, dict] | None = None,
) -> list[_CardShim]:
    return [_CardShim(k, catalog) for k in keys]


def _tag_provides(cards: list[_CardShim], tags: dict) -> dict[str, float]:
    """Real-tag weighted provides over a deck, mirroring drafttags._providers
    (exhaust_drops_on_upgrade gate, innate multiplier) without the per-tag
    call shape — one pass, all tags."""
    out: dict[str, float] = {}
    for c in cards:
        entry = tags.get(c.id.upper())
        if not entry:
            continue
        for tag, w in (entry.get("provides") or {}).items():
            w = float(w)
            if (w and tag == "exhaust_enabler"
                    and entry.get("exhaust_drops_on_upgrade")
                    and c.is_upgraded):
                continue
            if w and entry.get("innate"):
                w *= INNATE_PROVIDER_MULT
            out[tag] = out.get(tag, 0.0) + w
    return out


def deck_features(
    deck_keys: list[str],
    *,
    relics: list[str] | None = None,
    hp: float | None = None,
    max_hp: float | None = None,
    act: int | None = None,
    boss: str | None = None,
    catalog: dict[str, dict] | None = None,
    tags: dict | None = None,
) -> dict[str, float]:
    """One flat feature dict for a run state. Missing inputs simply omit their
    features — the model layer treats absent keys as 0 after standardization."""
    cards = cards_from_keys(deck_keys, catalog)
    n = len(cards)
    f: dict[str, float] = {"n_cards": float(n)}
    if n:
        f["frac_upgraded"] = sum(c.is_upgraded for c in cards) / n
    if relics is not None:
        f["n_relics"] = float(len(relics))
    if hp is not None and max_hp:
        f["hp_frac"] = hp / max_hp
        f["max_hp"] = float(max_hp)
    if act is not None:
        f["act"] = float(act)
    if boss:
        f[f"boss:{boss}"] = 1.0

    if catalog and n:
        types: dict[str, int] = {}
        costs: dict[str, int] = {}
        for c in cards:
            t = (c.type or "other").lower()
            types[t] = types.get(t, 0) + 1
            cost = str(c.cost)
            key = cost if cost in ("0", "1", "2") else (
                "x" if cost == "X" else "3plus" if cost else "none")
            costs[key] = costs.get(key, 0) + 1
        for t, k in types.items():
            f[f"type:{t}"] = k / n
        for cst, k in costs.items():
            f[f"cost:{cst}"] = k / n

    # tag lens, per-card normalized so deck SIZE doesn't smuggle itself into
    # every tag feature: pseudo-tags (need type/cost/description on the shim,
    # hence the catalog enrichment) + real-tag provides
    if n:
        for tag, w in deck_tag_weights(cards).items():
            f[f"tag:{tag}"] = w / n
        if tags:
            for tag, w in _tag_provides(cards, tags).items():
                f[f"tag:{tag}"] = w / n
    return f
