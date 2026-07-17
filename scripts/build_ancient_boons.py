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
        value=3.5, note="Neow's Fury (KB): 10 dmg + return 2 discards to hand, "
        "Exhaust — a solid free card."),
    "New Leaf": dict(value=2.0, note="Transform 1; low impact."),
    "Nutritious Oyster": dict(value=4.0, note="+11 Max HP."),
    "Pomander": dict(value=3.5, note="Upgrade a card (Bash+ early)."),
    "Precarious Shears": dict(
        value=4.0, note="Remove 2 for 13 damage; thinning is premium, hp-gate "
        "in _event covers the cost side."),
    "Precise Scissors": dict(value=3.0, note="Remove 1."),
    "Scroll Boxes": dict(
        value=3.0, note="Owner: 1-of-2 packs of 3 class cards (1 uncommon + 2 "
        "commons, non-repeating), unskippable; costs all gold (~99 at Neow)."),
    "Silken Tress": dict(
        value=2.5, note="Lose all gold; Glam-enchant the first card reward "
        "(you keep ONE of its cards — one twice-a-combat card for ~99g). "
        "New-epoch boon, harvested live 2026-07-16."),
    "Silver Crucible": dict(
        value=4.0, note="3 upgraded rewards vs one empty chest; fine trade."),
    "Small Capsule": dict(value=4.0, note="Random relic."),
    "Stone Humidifier": dict(
        value=4.5, note="+5 Max HP per rest, compounds; bot rests often."),
    # ---------------------------------------------------------------- OROBAS (Act 2)
    "Alchemical Coffer": dict(
        value=5.0, note="4 potion slots + potions; potion pass made these count."),
    "Archaic Tooth": dict(
        value=6.5, provides={"vulnerable_source": 2.0, "big_single_hit": 1.0},
        note="Owner: Break = 1 energy, 20 dmg, 5 Vulnerable — a massive strict "
        "Bash upgrade. Provides are a proxy (BREAK has no tags/KB entry yet, so "
        "§5-C deck pricing is blind to it — filed)."),
    "Driftwood": dict(
        value=5.0, note="Reroll every card reward once — selection quality all run."),
    "Electric Shrymp": dict(
        value=5.0, note="Owner: Imbued = the Skill auto-plays (tutored free) at "
        "the start of every combat. Strong with any good Skill; the enchant "
        "screen should prefer the deck's best scaling Skill."),
    "Glass Eye": dict(
        value=3.5, note="5 cards at once; free quality but real bloat risk."),
    "Prismatic Gem": dict(
        value=8.0, provides=dict(ENERGY),
        note="+1 energy/turn; reward-pool dilution is the only tax. Energy is "
        "king. NB drafting sees off-class/colorless offers without Spirebird "
        "priors or tags (text-parse + rarity only) → systematically undervalued "
        "vs in-class; conservative but safe (owner: 'probably for the best' — "
        "cross-class Spirebird samples are abysmal anyway). Deep-future: busted "
        "cross-class combos lurk (Shiv/Ethereal generators + Feel No Pain + "
        "Ashen Strike — owner)."),
    "Radiant Pearl": dict(
        value=5.5, provides={"energy_source": 1.0},
        note="Luminesce (KB): Retain, +2 energy, Exhaust — in hand every combat "
        "= ~2 flexible energy per fight."),
    "Touch of Orobas": dict(
        value=6.0, note="Owner-confirmed: Black Blood = heal 12 post-combat, "
        "a strict Burning Blood upgrade — +6/combat is major attrition relief "
        "for a bot that bleeds every fight."),
    # ---------------------------------------------------------------- PAEL (Act 2)
    "Pael's Blood": dict(
        value=6.0, provides={"draw_engine": 1.5},
        note="Passive +1 draw/turn — costs no card slot, so the drafted-draw "
        "energy caveat only half-applies."),
    "Pael's Claw": dict(
        value=3.5, note="Owner: Goopy = the Defend gains +1 Block permanently "
        "per play, but Exhausts on play — one use per fight, grows forever. "
        "Slow compounding for a real tempo tax."),
    "Pael's Eye": dict(
        value=2.0, note="Skip-turn tech the single-turn planner will never "
        "trigger deliberately; dead weight for the bot today."),
    "Pael's Flesh": dict(
        value=8.5, provides=dict(ENERGY),
        note="+1 energy from turn 3 on — the strongest common Pael offer."),
    "Pael's Growth": dict(
        value=1.5, note="Owner: Clone unlocks a rest-site action duplicating "
        "ALL Clone cards (1→2→4→8 with dedication). Bot-aware LOW: the rest "
        "handler is blind to non-standard campfire actions (Girya/Lift class, "
        "§8.4) — until it learns Clone, the enchant does nothing for us. Raise "
        "when the rest handler grows action awareness."),
    "Pael's Horn": dict(
        value=3.0, note="Relax (KB): 3 energy, 16 Block, next turn +2 draw "
        "+2 energy, Exhaust — real but unexciting cards; owner rated average."),
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
        value=4.0, note="Remove 4 for Soot-on-shuffle (Soot = unplayable "
        "Status). Thinning with a tax that grows as the deck thins (more "
        "shuffles) — self-limiting but net fine."),
    "Golden Compass": dict(
        value=5.0, note="Owner: a single guaranteed GOOD Act-2 route, 2 rooms "
        "longer (extra chest + fight), no choices. Bot-aware BONUS: a curated "
        "path sidesteps our own routing weaknesses entirely and adds income."),
    "Nutritious Soup": dict(
        value=5.0, note="Owner: Ember = Strikes cost 0, +3 dmg, Eternal. "
        "0-cost 9-dmg Strikes are real tempo; Eternal locks them in the deck "
        "forever (anti-thinning tax on late-game quality)."),
    "Pumpkin Candle": dict(
        value=6.0, provides=dict(ENERGY),
        note="+1 energy/turn, temporary (5 combats, kindle at rests / to Act 3 "
        "per variant); even temporary energy wins fights now."),
    "Seal of Gold": dict(
        value=5.0, provides=dict(ENERGY),
        note="Energy for 5g/turn — cheap tax at bot gold curves. (Log-only boon; "
        "wikis miss it.)"),
    "Storybook": dict(
        value=7.5, provides={"energy_source": 1.0},
        note="Brightest Flame (KB): gain 2 energy, draw 2, lose 1 Max HP — "
        "owner: 'by far one of the strongest picks from Tezcatara'."),
    "Toasty Mittens": dict(
        value=5.0, provides={"strength_source": 1.5},
        note="+1 Strength/turn for top-deck exhaust; steady ramp, mild mill tax."),
    "Toy Box": dict(
        value=4.5, note="Owner: melt = leftmost goes permanently inactive every "
        "3 combats — but on-pickup-effect relics lose nothing to melting, so "
        "expected value is better than it reads."),
    "Very Hot Cocoa": dict(
        value=7.5, provides=dict(ENERGY),
        note="+4 energy on turn 1 every combat — huge tempo; slightly below "
        "Flesh in long fights, above it in short ones."),
    "Yummy Cookie": dict(value=6.0, note="Upgrade 4 now; always-good."),
    # -------------------------------------------------------------- NONUPEIPE (Act 3)
    "Beautiful Bracelet": dict(
        value=4.5, note="Owner: Swift 3 = first play each combat draws 3. "
        "Three enchanted cards = solid recurring velocity."),
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
        value=5.0, note="Owner: Glam = first play each combat plays twice. "
        "Every future draft arrives pre-improved; compounds with pick quality."),
    "Jewelry Box": dict(
        value=5.0, note="Apotheosis into deck; mass-upgrade payoff."),
    "Looming Fruit": dict(value=6.0, note="+31 Max HP in Act 3 is a real buffer."),
    "Signet Ring": dict(
        value=6.0, note="999g — the A/B winner converted banked gold into 8 "
        "relics in Act 3. Requires shop competence; ours is adequate."),
    # ------------------------------------------------------------------- TANX (Act 3)
    "Claws": dict(
        value=5.0, deck_bonus=[{"tag": "strength_source", "per": 0.4, "cap": 1.6}],
        note="Owner: Maul = 1 energy, 5x2 dmg, ALL Mauls +1 dmg this combat — "
        "up to 6 self-ramping multi-hits from junk basics; multiplies with "
        "Strength. (MAUL still a KB gap for deck pricing.)"),
    "Crossbow": dict(
        value=5.0, note="Free random attack in hand each turn."),
    "Iron Club": dict(
        value=4.0, provides={"draw_engine": 0.5}, note="Draw per 4 plays."),
    "Meat Cleaver": dict(
        value=2.5, note="Owner: Cook = rest action, remove 2 cards + 9 Max HP "
        "— strong in principle, but the rest handler is blind to non-standard "
        "campfire actions (Girya class, §8.4), so it's dead weight for the bot "
        "until that lands. Raise then."),
    "Sai": dict(
        value=6.5, note="Passive 7 block/turn — pure survival, no play needed."),
    "Spiked Gauntlets": dict(
        value=7.5, provides=dict(ENERGY),
        note="+1 energy, Powers cost 1 more — mild tax. Owner picked it in the "
        "A/B #3 win."),
    "Tanx's Whistle": dict(
        value=4.0, note="Owner: Whistle = 3 energy, 33(44) dmg, Stun (delays "
        "the intent one turn; not a status — ignores Artifact; doesn't stack), "
        "Exhaust. One big tempo nuke per fight; best vs elites/bosses."),
    "Throwing Axe": dict(
        value=5.5, deck_bonus=[{"tag": "big_single_hit", "per": 0.5, "cap": 2.0}],
        note="First card each combat played twice; scales with a big opener."),
    "Tri-Boomerang": dict(
        value=6.0, deck_bonus=[{"tag": "big_single_hit", "per": 0.5, "cap": 2.0}],
        note="Owner: Instinct = doubles the card's attack damage — on your 3 "
        "best attacks. Scales with the deck's top-end."),
    "War Hammer": dict(
        value=4.5, note="Elite kill → 4 upgrades; the honest elite gate caps "
        "uptime until deck power rises."),
    # ------------------------------------------------------------------ VAKUU (Act 3)
    "Blood-Soaked Rose": dict(
        value=6.5, provides=dict(ENERGY),
        note="Owner: Enthralled = 2-cost must-play-first Exhaust curse — a "
        "once-per-combat 2-energy tax when drawn, cheap rent on +1 energy/turn."),
    "Choices Paradox": dict(
        value=4.5, note="1-of-5 retained card each combat; flexible value."),
    "Distinguished Cape": dict(
        value=3.5, note="Owner: Apparition = StS1's (1 energy, Ethereal, gain "
        "1 Intangible; upgrade drops Ethereal). Premium for a human — but the "
        "combat sim doesn't model Intangible, so the planner scores it ~0 and "
        "lets it rot; bot-aware LOW until the sim learns Intangible, then "
        "reprice toward 6+."),
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
        value=4.0, note="Remove 3 for Folly (KB: unplayable Innate Ethereal "
        "Eternal curse) — permanently eats one turn-1 hand slot; the thinning "
        "usually still wins. (Log-only boon.)"),
    "Sere Talon": dict(
        value=4.0, note="Owner: Wish = 0-cost chosen tutor from draw pile, "
        "Exhaust (upgrade: Retain). 3 tutors vs 2 random curses — better the "
        "spikier the deck's best card."),
    "Whispering Earring": dict(
        value=5.5, provides=dict(ENERGY),
        note="Owner: Vakuu spams your cards left-to-right until energy runs "
        "out (capped vs infinites). A dumb-but-energy-spending turn 1 as rent "
        "on +1 energy/turn — mild quality tax, worth it."),
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
