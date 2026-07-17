"""Generate data/ancient_boons.json — the Ancients-pass boon catalog (PLAN §8.5.5a).

Sources: local run logs (459 runs, 106 unique option-sets across all 7 post-Act-1
Ancients — authoritative for titles/descriptions, includes boons the wikis miss) +
sts2wiki.org/ancients for the full pool. Values are on the event-heuristic scale
(relic ≈ 6.0 reference); `uncertain: True` marks boons whose STS2-specific keyword
(Goopy, Imbued, Maul, ...) we can't yet price — flagged for owner review.

Fields per boon (keyed by exact option title):
  value       base pick value at choice time
  deck_bonus  [{tag, per, cap}] — choice-time fit: + per weighted provider in deck
  provides    tag weights merged into deck providers AFTER pickup (drafttags)
  draft_bonus {tag: bonus} — post-pickup: flat draft bonus for offered cards
              providing the tag (the Legion → block-engine steering mechanism)
  note        one-line rationale
  uncertain   True = valuation blocked on unknown STS2 keyword; owner review

Run: .venv/Scripts/python scripts/build_ancient_boons.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "ancient_boons.json"

ENERGY = {"energy_source": 1.5}

BOONS: dict[str, dict] = {
    # ---------------------------------------------------------------- NEOW (Act 1)
    "Fishing Rod": dict(
        value=5.0, note="Every 3 combats upgrade a random card — live-validated "
        "(both A/B #3 runs carried it to good effect)."),
    "Arcane Scroll": dict(value=4.0, note="Random Rare; solid average."),
    "Booming Conch": dict(
        value=2.5, note="Elite-combat draw; bot declines most elites, low uptime."),
    "Cursed Pearl": dict(
        value=3.0, note="333g minus a curse; gold engine needs shop skill we lack."),
    "Golden Pearl": dict(value=3.5, note="150g flat."),
    "Large Capsule": dict(
        value=5.5, note="2 relics for mild deck bloat — best Neow economy."),
    "Lava Rock": dict(value=4.5, note="2 boss relics, delayed but real."),
    "Lead Paperweight": dict(value=3.0, note="1-of-2 colorless; average."),
    "Leafy Poultice": dict(
        value=2.5, note="Transform 2 basics at -10 Max HP; the HP is real money."),
    "Lost Coffer": dict(value=3.5, note="Card reward + potion."),
    "Neow's Torment": dict(
        value=2.5, uncertain=True, note="Neow's Fury card unknown."),
    "New Leaf": dict(value=2.0, note="Transform 1; low impact."),
    "Nutritious Oyster": dict(value=4.0, note="+11 Max HP."),
    "Pomander": dict(value=3.5, note="Upgrade a card (Bash+ early)."),
    "Precarious Shears": dict(
        value=4.0, note="Remove 2 for 13 damage; thinning is premium, hp-gate "
        "in _event covers the cost side."),
    "Precise Scissors": dict(value=3.0, note="Remove 1."),
    "Scroll Boxes": dict(
        value=2.5, uncertain=True, note="Pack contents unknown; loses all gold."),
    "Silver Crucible": dict(
        value=4.0, note="3 upgraded rewards vs one empty chest; fine trade."),
    "Small Capsule": dict(value=4.0, note="Random relic."),
    "Stone Humidifier": dict(
        value=4.5, note="+5 Max HP per rest, compounds; bot rests often."),
    # ---------------------------------------------------------------- OROBAS (Act 2)
    "Alchemical Coffer": dict(
        value=5.0, note="4 potion slots + potions; potion pass made these count."),
    "Archaic Tooth": dict(
        value=4.5, uncertain=True,
        note="Bash→Break (ancient starter); Break's text unknown but starter "
        "upgrades are usually strict wins."),
    "Driftwood": dict(
        value=5.0, note="Reroll every card reward once — selection quality all run."),
    "Electric Shrymp": dict(
        value=2.5, uncertain=True, note="Imbued enchant unknown."),
    "Glass Eye": dict(
        value=3.5, note="5 cards at once; free quality but real bloat risk."),
    "Prismatic Gem": dict(
        value=8.0, provides=dict(ENERGY),
        note="+1 energy/turn; reward-pool dilution is the only tax. Energy is king."),
    "Radiant Pearl": dict(
        value=3.5, uncertain=True, note="Luminesce card unknown."),
    "Touch of Orobas": dict(
        value=5.5, uncertain=True,
        note="Burning Blood → Black Blood; if the StS1 analog holds (bigger "
        "post-combat heal) it's strong attrition relief for the bot."),
    # ---------------------------------------------------------------- PAEL (Act 2)
    "Pael's Blood": dict(
        value=6.0, provides={"draw_engine": 1.5},
        note="Passive +1 draw/turn — costs no card slot, so the drafted-draw "
        "energy caveat only half-applies."),
    "Pael's Claw": dict(
        value=2.5, uncertain=True, note="Goopy enchant unknown."),
    "Pael's Eye": dict(
        value=2.0, note="Skip-turn tech the single-turn planner will never "
        "trigger deliberately; dead weight for the bot today."),
    "Pael's Flesh": dict(
        value=8.5, provides=dict(ENERGY),
        note="+1 energy from turn 3 on — the strongest common Pael offer."),
    "Pael's Growth": dict(
        value=3.5, uncertain=True, note="Clone enchant unknown."),
    "Pael's Horn": dict(
        value=2.5, uncertain=True,
        note="2 Relax cards; owner rated it average. Relax text unknown."),
    "Pael's Legion": dict(
        value=6.0,
        deck_bonus=[{"tag": "block_engine", "per": 0.35, "cap": 2.5}],
        provides={"block_payoff": 2.0},
        draft_bonus={"block_engine": 1.2},
        note="Doubles a card's block every 2 turns. A/B #3's decisive boon: the "
        "owner picked it sensing a block-light deck, then drafted Barricade to "
        "bank the doubled block (93 banked in the Insatiable win)."),
    "Pael's Tears": dict(
        value=4.0, note="Energy banking; the greedy planner rarely ends turns "
        "with surplus, so uptime is low for the bot."),
    "Pael's Tooth": dict(
        value=4.5, note="Remove 5, return upgraded over combats — genuine "
        "thinning+upgrades. (The old event heuristic's '+5 for remove' bait "
        "overrated it vs Legion, but it isn't a bad boon.)"),
    "Pael's Wing": dict(
        value=4.5, note="Card-reward sacrifices → relic per 2. Synergizes with "
        "our high skip rate: skips become income."),
    # -------------------------------------------------------------- TEZCATARA (Act 2)
    "Biiig Hug": dict(
        value=4.0, uncertain=True,
        note="Remove 4 for Soot-on-shuffle; Soot's text unknown."),
    "Golden Compass": dict(
        value=2.5, uncertain=True,
        note="Single special Act-2 path; removes routing agency, path unknown."),
    "Nutritious Soup": dict(
        value=3.0, uncertain=True, note="Tezcatara's Ember enchant unknown."),
    "Pumpkin Candle": dict(
        value=6.0, provides=dict(ENERGY),
        note="+1 energy/turn, temporary (5 combats, kindle at rests / to Act 3 "
        "per variant); even temporary energy wins fights now."),
    "Seal of Gold": dict(
        value=5.0, provides=dict(ENERGY),
        note="Energy for 5g/turn — cheap tax at bot gold curves. (Log-only boon; "
        "wikis miss it.)"),
    "Storybook": dict(
        value=3.0, uncertain=True, note="Brightest Flame card unknown."),
    "Toasty Mittens": dict(
        value=5.0, provides={"strength_source": 1.5},
        note="+1 Strength/turn for top-deck exhaust; steady ramp, mild mill tax."),
    "Toy Box": dict(
        value=4.0, uncertain=True,
        note="4 melting Wax relics; front-loaded value, contents random."),
    "Very Hot Cocoa": dict(
        value=7.5, provides=dict(ENERGY),
        note="+4 energy on turn 1 every combat — huge tempo; slightly below "
        "Flesh in long fights, above it in short ones."),
    "Yummy Cookie": dict(value=6.0, note="Upgrade 4 now; always-good."),
    # -------------------------------------------------------------- NONUPEIPE (Act 3)
    "Beautiful Bracelet": dict(
        value=3.5, uncertain=True, note="Swift 3 enchant unknown."),
    "Blessed Antler": dict(
        value=5.5, provides=dict(ENERGY),
        note="Energy minus 3 Dazed/combat draw pollution."),
    "Brilliant Scarf": dict(
        value=4.0, note="5th card free; needs velocity the bot only sometimes has."),
    "Delicate Frond": dict(
        value=6.0, note="Full potion refill every combat — enormous with the "
        "potion policy actually drinking them."),
    "Diamond Diadem": dict(
        value=2.5, note="≤2 plays → half damage; fights the planner's nature."),
    "Fur Coat": dict(
        value=5.5, note="7 marked combats at 1 HP — free Act-3 normals."),
    "Glitter": dict(
        value=3.5, uncertain=True, note="Glam enchant unknown."),
    "Jewelry Box": dict(
        value=5.0, note="Apotheosis into deck; mass-upgrade payoff."),
    "Looming Fruit": dict(value=6.0, note="+31 Max HP in Act 3 is a real buffer."),
    "Signet Ring": dict(
        value=6.0, note="999g — the A/B winner converted banked gold into 8 "
        "relics in Act 3. Requires shop competence; ours is adequate."),
    # ------------------------------------------------------------------- TANX (Act 3)
    "Claws": dict(
        value=3.0, uncertain=True, note="Maul card unknown; up-to-6 transform."),
    "Crossbow": dict(
        value=5.0, note="Free random attack in hand each turn."),
    "Iron Club": dict(
        value=4.0, provides={"draw_engine": 0.5}, note="Draw per 4 plays."),
    "Meat Cleaver": dict(
        value=3.0, uncertain=True, note="Cook mechanic unknown."),
    "Sai": dict(
        value=6.5, note="Passive 7 block/turn — pure survival, no play needed."),
    "Spiked Gauntlets": dict(
        value=7.5, provides=dict(ENERGY),
        note="+1 energy, Powers cost 1 more — mild tax. Owner picked it in the "
        "A/B #3 win."),
    "Tanx's Whistle": dict(
        value=3.0, uncertain=True, note="Whistle card unknown."),
    "Throwing Axe": dict(
        value=5.5, deck_bonus=[{"tag": "big_single_hit", "per": 0.5, "cap": 2.0}],
        note="First card each combat played twice; scales with a big opener."),
    "Tri-Boomerang": dict(
        value=3.5, uncertain=True, note="Instinct enchant unknown."),
    "War Hammer": dict(
        value=4.5, note="Elite kill → 4 upgrades; the honest elite gate caps "
        "uptime until deck power rises."),
    # ------------------------------------------------------------------ VAKUU (Act 3)
    "Blood-Soaked Rose": dict(
        value=6.5, uncertain=True, provides=dict(ENERGY),
        note="Energy + Enthralled card; Enthralled's tax unknown."),
    "Choices Paradox": dict(
        value=4.5, note="1-of-5 retained card each combat; flexible value."),
    "Distinguished Cape": dict(
        value=4.5, uncertain=True,
        note="-9 Max HP for 3 Apparitions; if Apparition = StS1 Intangible "
        "this is underpriced — confirm."),
    "Fiddle": dict(
        value=5.0, provides={"draw_engine": 2.0},
        note="+2 draw/turn but no in-turn draw — anti-synergy with drafted draw."),
    "Jeweled Mask": dict(
        value=4.0, deck_bonus=[{"tag": "power_setup", "per": 0.5, "cap": 2.0}],
        note="Free random Power at combat start; scales with Power count."),
    "Lord's Parasol": dict(
        value=6.0, note="Entire merchant inventory free at next shop."),
    "Music Box": dict(
        value=5.5, note="Ethereal copy of first attack each turn."),
    "Preserved Fog": dict(
        value=4.0, uncertain=True,
        note="Remove 3, add Folly; Folly unknown. (Log-only boon.)"),
    "Sere Talon": dict(
        value=2.5, uncertain=True, note="2 curses + 3 Wishes; Wishes unknown."),
    "Whispering Earring": dict(
        value=5.5, uncertain=True, provides=dict(ENERGY),
        note="Energy, but Vakuu hijacks turn 1 — unpredictable for the planner."),
    # ------------------------------------------------------------- DARV (Acts 2 & 3)
    "Astrolabe": dict(value=5.5, note="Transform 3 + upgrade them."),
    "Black Star": dict(
        value=5.0, note="Elites drop 2 relics; pairs with routing income work — "
        "value rises when the elite gate opens up."),
    "Calling Bell": dict(
        value=5.0, note="3 relics for one unique curse; usually worth it."),
    "Dusty Tome": dict(
        value=4.5, deck_bonus=[{"tag": "exhaust_payoff", "per": 0.5, "cap": 2.0}],
        note="Ironclad: Corruption+ — archetype-defining with exhaust payoffs "
        "(Feel No Pain), risky without."),
    "Ectoplasm": dict(
        value=5.5, provides=dict(ENERGY),
        note="Energy for a gold lock; hurts Act-3 shop conversion but energy "
        "wins the fights that get you there. (Log-only boon.)"),
    "Empty Cage": dict(value=4.5, note="Remove 2, clean thinning."),
    "Pandora's Box": dict(
        value=3.5, note="Transform ALL basics — high variance mid-run when "
        "basics still carry the defense."),
    "Runic Pyramid": dict(
        value=6.0, note="Hand retention; even the single-turn planner benefits "
        "from bigger effective hands."),
    "Snecko Eye": dict(
        value=2.0, note="Draw 2 + Confused: randomized costs BREAK the "
        "planner's cost model — mispriced until the sim learns Confused. "
        "Deliberately low for the bot, not a statement about the relic."),
    "Velvet Choker": dict(
        value=6.5, provides=dict(ENERGY),
        note="Energy at ≤6 plays/turn; combat.py already models the card cap. "
        "(Log-only for DARV pool.)"),
}


def main() -> None:
    for entry in BOONS.values():
        entry.setdefault("uncertain", False)
        entry.setdefault("deck_bonus", [])
        entry.setdefault("provides", {})
        entry.setdefault("draft_bonus", {})
    out = {
        "_meta": {
            "source": "scripts/build_ancient_boons.py (Ancients pass, PLAN §8.5.5a)",
            "scale": "event-heuristic units (relic ≈ 6.0)",
            "n_boons": len(BOONS),
            "n_uncertain": sum(1 for b in BOONS.values() if b["uncertain"]),
        },
        "boons": BOONS,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(BOONS)} boons, "
          f"{out['_meta']['n_uncertain']} flagged uncertain)")


if __name__ == "__main__":
    main()
