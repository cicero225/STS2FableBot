"""Deck-context draft scoring — the card-pass step-2 tag machinery.

One mechanism, not 93 micro-rules (CARD_PASS_STEP2_PROPOSAL.md, owner-reviewed
2026-07-12): each card `provides` weighted archetype tags and may `need` tags at a
threshold. Two generic rules produce the score adjustment:

- bonus: a need met (weighted providers vs threshold) earns a strength-scaled bonus,
  ramping linearly from zero providers to the threshold (smooth, not a cliff).
- penalty: ONLY cards marked as pure payoffs (near-blank without support) are docked
  when a need has zero providers — enablers with baseline value are bonus-only, so
  they stay pickable as archetype seeds (owner's chicken-and-egg principle). The dock
  is discounted in Act 1 (speculative window: Rupture/Unmovable-class cards are worth
  taking while the deck is still malleable).

Structural rules from the review: a card counts ITSELF as a provider (Dominate provides
the Vulnerable it needs -> never docked); provider weights carry magnitude (Tremble's
3 stacks beat Bash's 2); per-proc autoblock (Plating) is pre-weighted in the table.

Pure functions only — the tag table is loaded by the kb layer and injected.
"""

from __future__ import annotations

import json
from pathlib import Path

_STRENGTH_MULT = {"mild": 0.5, "moderate": 1.0, "strong": 1.6}

_TAGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "card_draft_tags.json"
_BOONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ancient_boons.json"


def load_draft_tags(path: Path | str | None = None) -> dict[str, dict]:
    """id -> {provides, needs, copy_cap, ...} from data/card_draft_tags.json
    (scripts/build_draft_tags.py). Empty if absent — drafting then runs context-free."""
    p = Path(path) if path else _TAGS_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("tags", {})


def load_ancient_boons(path: Path | str | None = None) -> dict[str, dict]:
    """title -> {value, deck_bonus, provides, draft_bonus, note, uncertain} from
    data/ancient_boons.json (scripts/build_ancient_boons.py). Empty if absent —
    ancient events then fall back to the generic event heuristic."""
    p = Path(path) if path else _BOONS_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("boons", {})


_EVENTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "event_choices.json"


def load_event_choices(path: Path | str | None = None) -> dict[str, dict]:
    """OPTION TITLE -> {value, note, uncertain} from data/event_choices.json
    (scripts/build_event_choices.py, EVENTS_PASS.md). Title-keyed because the mod's
    event_id lags screen transitions. Empty if absent — events then fall back to
    Spirebird + the generic heuristic."""
    p = Path(path) if path else _EVENTS_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("choices", {})


def boon_relic_context(relics, boons: dict) -> tuple[dict[str, float], dict[str, float]]:
    """(provides, draft_bonus) merged over owned relics that match catalog boons.

    Boons picked at Ancient events land in player.relics under their boon title
    (verified: Pael's Legion in the A/B #3 record), so drafting can see them: an
    owned energy boon lifts the draw penalty, and an engine boon (Legion) both
    meets card needs (`provides`) and steers offers toward its archetype
    (`draft_bonus`)."""
    provides: dict[str, float] = {}
    bonus: dict[str, float] = {}
    for r in relics or []:
        entry = boons.get(getattr(r, "name", None) or getattr(r, "id", "") or "")
        if not entry:
            continue
        for tag, wgt in (entry.get("provides") or {}).items():
            provides[tag] = provides.get(tag, 0.0) + float(wgt)
        for tag, b in (entry.get("draft_bonus") or {}).items():
            bonus[tag] = max(bonus.get(tag, 0.0), float(b))
    return provides, bonus


def deck_tag_weights(deck) -> dict[str, float]:
    """Weighted provides-counts for a deck, plus pseudo-tags computed from deck state
    (__unupgraded / __strike_named / __defends / __basics) so density rules like
    Apotheosis (unupgraded count) and Perfected Strike (name-contains-Strike) ride the
    same machinery. Tag table lookups happen in score_adjustment; this only needs card
    ids/names/upgrade flags."""
    counts: dict[str, float] = {}
    n_unupgraded = 0
    n_strike_named = 0
    n_defends = 0
    n_basics = 0
    for c in deck:
        cid = (getattr(c, "id", "") or "").upper()
        name = (getattr(c, "name", "") or "").lower()
        if not getattr(c, "is_upgraded", False):
            n_unupgraded += 1
        if "strike" in name or "STRIKE" in cid:
            n_strike_named += 1
        if cid.startswith("DEFEND_"):
            n_defends += 1
        if cid.startswith(("STRIKE_", "DEFEND_")):
            n_basics += 1
    counts["__unupgraded"] = float(n_unupgraded)
    counts["__strike_named"] = float(n_strike_named)
    counts["__defends"] = float(n_defends)
    counts["__basics"] = float(n_basics)
    return counts


def _providers(
    tag: str, deck_counts: dict[str, float], deck, tags: dict,
    extra: dict[str, float] | None = None,
) -> float:
    """Weighted provider count for a tag: pseudo-tags come from deck_tag_weights;
    real tags are summed from the tag table over the actual deck, plus `extra`
    (relic/boon-provided tags — Ancients pass)."""
    if tag.startswith("__"):
        return deck_counts.get(tag, 0.0)
    total = float((extra or {}).get(tag, 0.0))
    for c in deck:
        entry = tags.get((getattr(c, "id", "") or "").upper())
        if entry:
            total += float((entry.get("provides") or {}).get(tag, 0.0))
    return total


def score_adjustment(
    card_id: str,
    deck,
    tags: dict,
    w,
    act: int = 1,
    is_upgraded: bool = False,
    relic_provides: dict[str, float] | None = None,
    relic_draft_bonus: dict[str, float] | None = None,
) -> float:
    """The deck-context adjustment for offering `card_id` to `deck`. Additive on top of
    the base _card_score (rarity/prior/planner-blind/etc.) — never a replacement.
    `relic_provides`/`relic_draft_bonus` carry owned boon/relic tags (Ancients pass):
    provides count toward needs/anti like deck cards; draft_bonus adds a flat bonus
    when the offered card provides a tag the boon wants fed (Legion → block_engine)."""
    entry = tags.get((card_id or "").upper())
    if not entry:
        return 0.0
    deck_counts = deck_tag_weights(deck)
    own_provides = entry.get("provides") or {}
    adj = 0.0

    for tag, b in (relic_draft_bonus or {}).items():
        if float(own_provides.get(tag, 0.0)) > 0:
            adj += float(b)

    for need in entry.get("needs") or []:
        tag = need.get("tag", "")
        threshold = max(1.0, float(need.get("threshold", 1)))
        mult = _STRENGTH_MULT.get(need.get("strength", "moderate"), 1.0)
        have = _providers(tag, deck_counts, deck, tags, relic_provides)
        # self-provision: the candidate joins the deck it is scored for
        have += float(own_provides.get(tag, 0.0))
        met_frac = min(1.0, have / threshold)
        adj += w.w_tag_bonus * mult * met_frac
        if need.get("penalty") and have <= 0:
            act_factor = w.tag_act1_penalty_mult if act <= 1 else 1.0
            adj += w.w_tag_penalty * mult * act_factor

    # anti-synergy: dock when a tag is ALREADY well-represented (Battle Trance's
    # draw-lock collides with stacked draw; Panic Button locks out block plans)
    for anti in entry.get("anti") or []:
        tag = anti.get("tag", "")
        threshold = max(1.0, float(anti.get("threshold", 1)))
        mult = _STRENGTH_MULT.get(anti.get("strength", "moderate"), 1.0)
        if _providers(tag, deck_counts, deck, tags, relic_provides) >= threshold:
            adj += w.w_tag_penalty * mult * 0.5  # anti docks run at half penalty weight

    # deficit feeding (owner shadow review #2, 2026-07-24): "the deck seemed to lack
    # vulnerable appliers and defense. So I picked a card that gave both." The needs
    # lane above rewards a candidate whose OWN needs the deck meets; this is the
    # reverse edge — the candidate provides a tag that cards already in the deck are
    # starving for. Starvation includes exact-threshold supply (threshold+1 is the
    # redundancy target): Molten Fist behind a lone Bash met its threshold on paper
    # and still drew dead all act.
    feed = 0.0
    for c in deck:
        needer = tags.get((getattr(c, "id", "") or "").upper())
        if not needer:
            continue
        for need in needer.get("needs") or []:
            tag = need.get("tag", "")
            if tag.startswith("__") or float(own_provides.get(tag, 0.0)) <= 0:
                continue
            threshold = max(1.0, float(need.get("threshold", 1)))
            mult = _STRENGTH_MULT.get(need.get("strength", "moderate"), 1.0)
            have = _providers(tag, deck_counts, deck, tags, relic_provides)
            # a needer can't feed its own precondition (Molten Fist "provides"
            # vulnerable only AFTER the fist connects) — judge ITS starvation
            # on external supply only
            have -= float((needer.get("provides") or {}).get(tag, 0.0))
            gap = (threshold + 1.0) - have
            if gap <= 0:
                continue
            feed += w.w_deficit_feed * mult * min(1.0, gap / (threshold + 1.0))
    adj += min(feed, w.deficit_feed_cap)

    # copy cap: a second copy of a non-stacking card (Barricade) is dead weight
    if entry.get("copy_cap"):
        cid = (card_id or "").upper()
        if any((getattr(c, "id", "") or "").upper() == cid for c in deck):
            adj += w.w_copy_cap

    # controlled exhaust = thinning value in its own right (owner): scaled by remaining
    # thinnable basics, damped when the deck already thins itself. "upgraded" marks
    # cards whose exhaust only becomes targeted on upgrade (True Grit). A float value
    # scales the bonus (Stoke 2.0, owner 2026-07-24: whole-hand shred converts several
    # basics per play into random cards — better than the basics, especially early).
    ce = entry.get("controlled_exhaust")
    if ce and (ce != "upgraded" or is_upgraded):
        scale = float(ce) if isinstance(ce, (int, float)) and not isinstance(ce, bool) else 1.0
        basics = deck_counts.get("__basics", 0.0)
        thinning = _providers("deck_thinning", deck_counts, deck, tags)
        damp = 0.5 if thinning > 0 else 1.0
        adj += w.w_controlled_exhaust * scale * min(1.0, basics / 6.0) * damp

    # upgrade-awareness: the upgrade crosses a class boundary (True Grit's targeted
    # exhaust, Armaments' all-hand, Apotheosis/Stampede/Pyre cost drops) — a mild
    # anticipation bonus unupgraded, since a campfire converts it
    if entry.get("upgrade_unlocks") and not is_upgraded:
        adj += w.w_upgrade_unlocks

    return adj
