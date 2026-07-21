"""Generate data/event_choices.json — the events-pass option catalog (EVENTS_PASS.md).

Keyed by OPTION TITLE, not (event, option): the mod's event_id lags screen
transitions, and titles are stable and self-identifying. Values on the event-
heuristic scale (relic ≈ 6.0), same as the boon catalog. Sources: harvested option
texts (452-run corpus) + owner keyword definitions where known (Swift = first play
each combat draws N). `uncertain` marks unknown STS2 keywords for owner review.

Run: .venv/Scripts/python scripts/build_event_choices.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "event_choices.json"

CHOICES: dict[str, dict] = {
    # ---- Self-Help Book (enchant one of your cards)
    "Read the Back": dict(value=4.0,
                          note="Sharp 2 (+dmg/hit) on an Attack; SB 8.2. Owner: beats "
                          "Swift-Power only with a 3x+ multi-hit target — the enchant "
                          "target picker prefers multi-hits."),
    "Read a Random Passage": dict(value=4.2,
                                  note="Nimble 2 on a Skill; SB 8.5; owner: Nimble > "
                                  "Sharp generally."),
    "Read the Entire Book": dict(value=5.5,
                                 note="Swift 2 on a Power (owner: first play each "
                                 "combat draws 2 — powers get played once, so this "
                                 "is 2 draw every combat it's cast)."),
    # ---- Brain Leech
    "Rip the Leech Off": dict(value=4.5,
                              note="5 HP for a Colorless card reward; owner took it "
                              "in A/B #2-era play, Spirebird agrees."),
    "Share Knowledge": dict(value=3.5, note="1-of-5 random cards; decent selection."),
    # ---- Abyssal Baths (repeatable loop)
    "Immerse": dict(value=5.0, note="+2 Max HP for 3 damage — great rate; loop."),
    "Linger": dict(value=4.5, note="+2 Max HP for 4 damage; keep looping."),
    "Abstain": dict(value=2.5, note="Heal 10; take only when the HP math flips."),
    # ---- This or That
    "This": dict(value=3.5, note="~64g for 6 HP; fair."),
    "That": dict(value=4.5, note="Random relic + Clumsy; relics are deck power and "
                 "Clumsy is a mild curse."),
    # ---- Room Full of Cheese
    "Search": dict(value=5.0, note="14 HP for the Chosen Cheese relic — seen in two "
                   "win decks; pay it."),
    "Devour": dict(value=5.0, note="Title alias of 'Search' (same Chosen Cheese "
                   "option; the event uses both). Owner-QA'd correct pick."),
    "Gorge": dict(value=3.0, note="2 of 8 commons; deck bloat vs selection."),
    # ---- Legends Were True
    "Nab the Map": dict(value=5.0,
                        note="Spoils Map = 600g at the Act-3 main chest; we protect "
                        "it from removal and exhaust it freely (7f0a0c6). Real EV "
                        "if the run goes deep; the router likes gold now."),
    # ---- Sunken Statue / Wellspring
    "Grab the Sword": dict(value=5.5, note="Sword of Stone relic, free."),
    "Dive into the Water": dict(value=4.0, note="~109g for 7 HP."),
    "Bathe": dict(value=3.0, note="Wellspring heal-ish option; Spirebird carried it."),
    # ---- Wood Carvings (enchant traps + starter transforms)
    "Snake": dict(value=5.5,
                  note="REVERSED 2026-07-20 (owner + SB 11.9): Slither = random 0-3 "
                  "cost on draw — positive EV stapled to any cost>=2 card, and "
                  "Ironclad always has Bash. The old 'Slither trap' anchor was a "
                  "TARGETING mistake (a cost-1 Strike), not a bad option; the "
                  "enchant target picker now takes the highest-cost card."),
    "Bird": dict(value=3.0,
                 note="Starter -> Peck; SB 5.0. Owner: Toric usually better; Peck "
                 "edges it with Strength gain in deck OR Vantom as the boss."),
    "Torus": dict(value=4.0,
                  note="Starter -> Toric Toughness; SB 9.5; owner: usually the pick."),
    # ---- Sunken Treasury (+ chest twins elsewhere)
    "First Chest": dict(value=3.5, note="~56-64g free."),
    "Second Chest": dict(value=4.0,
                         note="300-360g + Greed curse. Big income for one curse; "
                         "gold converts well since the late-shop loop."),
    # ---- Drowning Beacon
    "Bottle": dict(value=3.0, note="Glowwater Potion (downside class but free)."),
    "Climb": dict(value=1.5, note="Fresnel Lens for -13 Max HP — steep."),
    # ---- Spiraling Whirlpool
    "Observe": dict(value=5.5,
                    note="Spiral = Replay 1 on a basic (mediocre -> decent); SB 15.3 "
                    "and owner agree. Planner prices the Replay text correctly "
                    "(verified: Strike+Spiral parses 6x2)."),
    "Drink": dict(value=2.5, note="Heal 26; situational by HP."),
    # ---- Endless Conveyor (pay-gold upgrade loop)
    "Observe the Chef": dict(value=4.0, note="Free random upgrade."),
    "Grab Spicy Snappy off the Belt": dict(
        value=3.5, note="40g for a random upgrade + the loop continues."),
    "Grab Caviar off the Belt": dict(value=4.5, note="SB 14.6; keep feasting."),
    "Grab Fried Eel off the Belt": dict(value=4.3, note="SB 13.6; keep feasting."),
    # ---- Future of Potions
    "Insert Common Potion": dict(value=3.5,
                                 note="Sacrifice the tier's potion for a same-rarity "
                                 "card reward (declinable cards, event NOT declinable)."),
    "Insert Uncommon Potion": dict(value=4.0,
                                   note="Owner: higher rarity better, unless the "
                                   "potion is protected-class (see EVENTS_PASS)."),
    "Insert Rare Potion": dict(value=4.5,
                               note="Owner: highest rarity is the default pick; "
                               "protected-potion veto is a potion-pass item."),
    # ---- Dense Vegetation / misc
    "Trudge On": dict(value=3.5, note="~70g for 8 HP."),
    "Fight!": dict(value=3.0, note="Optional fight for loot; deck-power dependent."),
    # ---- Jungle Maze
    "Solo Quest": dict(value=4.5, note="~148g for 18 HP — big income, real cost."),
    "Join Forces": dict(value=3.5, note="~53g free."),
    # ---- Lost Wisp / Tea Master / Symbiote / Tablet / Aroma
    "Capture the Wisp": dict(value=4.0, note="Lost Wisp relic (seen in a win deck)."),
    "Tea of Discourtesy": dict(value=4.5, note="Relic; in multiple win decks."),
    "Kill with Fire": dict(value=3.5, note="Symbiote removal-ish; Spirebird liked it."),
    "Smash": dict(value=4.0, note="Heal 20 HP free (Tablet of Truth)."),
    "Decipher": dict(value=2.0, note="-3 Max HP for one random upgrade — poor rate."),
    "Let Go": dict(value=3.5, note="Transform a card (Aroma of Chaos)."),
    "Maintain Control": dict(value=3.5, note="Upgrade a card."),
    "Exchange Gold": dict(value=3.0, note="42g for 2 random potions."),
    "Hug the Tree": dict(value=2.5, note="9 HP for a chosen transform."),
    "Extract Nectar": dict(value=3.0, note="35g free."),
    "Reach Deeper": dict(value=3.0, note="Deeper for 5 HP; chain EV positive-ish."),
    "Slowly Find an Exit": dict(value=2.0, note="8 HP for one random potion — meh."),
    "Light Door": dict(value=4.5, note="Upgrade 2 random cards, free."),
    "Dark Door": dict(value=4.0, note="Remove 1 card, free."),
    "Overcome": dict(value=4.0, note="SB 8.9; engage."),
    "Accept": dict(value=3.0,
                   note="The Decider is NOT declinable (Reject loops then ends the "
                   "run). Sub-choices per owner: 2-relics > Shame-upgrade; "
                   "Regret+300g > heal-10 (unless desperate / no shops left); "
                   "Doubt+2-rewards vs Double+Transform-2 by basics count."),
}


def main() -> None:
    for entry in CHOICES.values():
        entry.setdefault("uncertain", False)
    out = {
        "_meta": {
            "source": "scripts/build_event_choices.py (events pass, EVENTS_PASS.md)",
            "scale": "event-heuristic units (relic ~ 6.0)",
            "keying": "OPTION TITLE (event_id lags transitions in mod state)",
            "n_options": len(CHOICES),
            "n_uncertain": sum(1 for c in CHOICES.values() if c["uncertain"]),
        },
        "choices": CHOICES,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(CHOICES)} options, "
          f"{out['_meta']['n_uncertain']} uncertain)")


if __name__ == "__main__":
    main()
