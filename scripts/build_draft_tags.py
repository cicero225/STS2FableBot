"""Build data/card_draft_tags.json (v2) — the card-pass step-2 tag table.

Provides-tags come from the 12-agent audit (2026-07-12, wf_1c79ed42-a44) with
magnitude weights parsed from card text; needs/flags are the CURATED table below,
authored from CARD_PASS_STEP2_PROPOSAL.md including every owner review override
(the review log is the authority — see items 1-32 there).

Rerunnable: reads data/card_catalog.json for texts/weights. The audit's raw
tags_provides are baked in below (frozen from the workflow output) so the build
does not depend on scratchpad artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "card_catalog.json"
OUT = ROOT / "data" / "card_draft_tags.json"

# ---------------------------------------------------------------- needs (curated)
# Format: id -> list of (tag, threshold, strength, penalty)
# penalty=True ONLY for pure payoffs (near-blank without support) per the owner's
# chicken-and-egg principle; the Act-1 speculative window discounts it at runtime.
# Pseudo-tags (__unupgraded, __strike_named, __defends, __basics, __attacks,
# __cheap_attacks) are computed from live deck state by the machinery.
NEEDS: dict[str, list[tuple[str, int, str, bool]]] = {
    # ---- vulnerable package (weighted stacks; Bash provides 2 from the starter deck)
    "BULLY": [("vulnerable_source", 3, "strong", True)],
    "DOMINATE": [("vulnerable_source", 3, "moderate", False)],  # self-provides -> bonus-only
    "VICIOUS": [("vulnerable_source", 3, "strong", True)],
    "DISMANTLE": [("vulnerable_source", 2, "moderate", False)],
    "MOLTEN_FIST": [("vulnerable_source", 2, "strong", False)],  # 10-dmg baseline (review #3)
    "TREMBLE": [("vulnerable_payoff", 1, "moderate", False)],  # bonus-only enabler (review #3)
    "CRUELTY": [("vulnerable_source", 3, "strong", True)],
    "DEBILITATE": [("vulnerable_source", 2, "strong", False)],  # 10-dmg baseline
    # shadow review 2026-07-24: "doesn't really work unless a source of
    # vulnerable bigger than Bash already exists" -- Bash (2.0, in every
    # deck) earns half credit only at threshold 4
    "COLOSSUS": [("vulnerable_source", 4, "moderate", False)],
    # ---- exhaust package
    "ASHEN_STRIKE": [("exhaust_enabler", 3, "strong", False)],
    "EVIL_EYE": [("exhaust_enabler", 2, "moderate", False)],  # Defend baseline
    "FORGOTTEN_RITUAL": [("exhaust_enabler", 2, "strong", True)],  # dead unmet
    "SECOND_WIND": [("exhaust_payoff", 1, "mild", False)],
    "BRAND": [("exhaust_payoff", 1, "mild", False)],
    "BURNING_PACT": [("exhaust_payoff", 1, "mild", False)],
    "DARK_EMBRACE": [("exhaust_enabler", 3, "strong", True)],  # power, blank unmet
    "FEEL_NO_PAIN": [("exhaust_enabler", 2, "strong", True)],  # power, blank unmet
    "FIEND_FIRE": [("draw_engine", 1, "mild", False)],
    "PACTS_END": [("exhaust_enabler", 4, "strong", True)],
    "STOKE": [("exhaust_payoff", 1, "moderate", False)],
    "TRUE_GRIT": [("exhaust_payoff", 1, "moderate", False)],
    "CINDER": [("exhaust_payoff", 1, "mild", False)],
    "DRUM_OF_BATTLE": [("exhaust_enabler", 1, "mild", False)],
    "BOMBARDMENT": [("exhaust_enabler", 1, "moderate", False)],
    "HOWL_FROM_BEYOND": [("exhaust_enabler", 1, "moderate", False)],
    # ---- attack-density package (__attacks/__cheap_attacks are live deck counts)
    "EXPECT_A_FIGHT": [("__attacks", 10, "moderate", True)],
    "RAGE": [("__cheap_attacks", 8, "moderate", True)],
    "STAMPEDE": [("__attacks", 10, "moderate", True),
                 ("expensive_attack", 1, "moderate", False)],  # review #6
    "THRASH": [("big_single_hit", 1, "moderate", False)],  # review #7: big hits = fodder
    "JUGGLING": [("__cheap_attacks", 8, "moderate", True)],
    "PILLAGE": [("__attacks", 10, "mild", False)],
    "STOMP": [("__cheap_attacks", 6, "moderate", False)],
    "AGGRESSION": [("big_single_hit", 1, "moderate", False)],  # review #8: quality > count
    "BOLAS": [("strength_source", 1, "moderate", False)],
    "CASCADE": [("__attacks", 10, "moderate", False)],
    "CLOAK_AND_DAGGER": [("attack_density_payoff", 1, "mild", False)],
    "HAVOC": [("__attacks", 12, "moderate", False)],  # review #11: powers are fine
    "PRIMAL_FORCE": [("__basics", 5, "moderate", False)],
    "SETUP_STRIKE": [("multi_hit", 2, "mild", False)],
    "UP_MY_SLEEVE": [("strength_source", 1, "moderate", False)],
    "RATTLE": [("companion_attack", 2, "strong", True)],
    # ---- self-HP-loss package
    "SPITE": [("self_hp_loss_source", 1, "moderate", True)],
    "RUPTURE": [("self_hp_loss_source", 1, "strong", True)],  # Act-1 window applies
    # Owner 2026-08-20 (new-discovery pass): Inferno self-feeds its trigger
    # (loses 1 hp at turn start) so no penalty, but real sources make it an
    # engine; Tear Asunder pays off on ANY hp loss ('doesn't specify why you
    # lost HP' -- enemy chip counts), decent solo -> moderate bonus, no penalty.
    "INFERNO": [("self_hp_loss_source", 1, "strong", False)],
    "TEAR_ASUNDER": [("self_hp_loss_source", 1, "moderate", False)],
    # ---- strength / multi-hit package (all bonus-only)
    "CONFLAGRATION": [("strength_source", 1, "moderate", False)],
    "WHIRLWIND": [("strength_source", 1, "moderate", False),
                  ("energy_source", 1, "moderate", False)],
    "PECK": [("strength_source", 1, "moderate", False)],
    "SWORD_BOOMERANG": [("strength_source", 1, "moderate", False)],
    "CELESTIAL_MIGHT": [("strength_source", 1, "mild", False)],
    "EXTERMINATE": [("strength_source", 1, "moderate", False)],
    "FISTICUFFS": [("strength_source", 1, "mild", False)],
    "OMNISLICE": [("strength_source", 1, "mild", False)],
    "TWIN_STRIKE": [("strength_source", 1, "mild", False)],
    "VOLLEY": [("strength_source", 1, "moderate", False),
               ("energy_source", 1, "moderate", False)],
    "FIGHT_ME": [("multi_hit", 2, "mild", False)],  # review #27
    "INFLAME": [("multi_hit", 2, "mild", False)],
    "ENVENOM": [("multi_hit", 2, "moderate", False)],
    "LETHALITY": [("big_single_hit", 1, "mild", False)],  # review #22: no penalty
    "ONE_TWO_PUNCH": [("big_single_hit", 1, "moderate", False)],
    "COSMIC_INDIFFERENCE": [("big_single_hit", 1, "mild", False)],
    "HEADBUTT": [("big_single_hit", 1, "mild", False)],  # review #23
    "EQUILIBRIUM": [("big_single_hit", 1, "mild", False)],
    "UNRELENTING": [("expensive_attack", 1, "mild", False)],
    "MIRAGE": [("poison_source", 1, "strong", True)],  # blank on Ironclad
    "HAILSTORM": [("frost_source", 1, "strong", True)],
    "COLLISION_COURSE": [("status_cards_payoff", 1, "mild", False)],
    # ---- block package
    "BODY_SLAM": [("block_engine", 4, "strong", True)],
    "JUGGERNAUT": [("block_engine", 3, "moderate", False)],  # Defends still proc it
    "BARRICADE": [("block_engine", 2, "moderate", False)],
    "PROLONG": [("block_engine", 1, "moderate", False)],  # review #13: snapshot, softened
    "UNMOVABLE": [("block_engine", 1, "moderate", True)],  # Act-1 window keeps it takeable
    # ---- other density / deck-property
    # shadow review 2026-07-24: clean Bloodletting->Stoke plays; the shred is
    # "an invisible source of cards that might need bloodletting"
    "BLOODLETTING": [("expensive_attack", 2, "moderate", False),
                     ("hand_dump", 1, "mild", False)],
    "ARMAMENTS": [("__unupgraded", 8, "mild", False)],  # review #15: mainly good as +
    "PERFECTED_STRIKE": [("__strike_named", 5, "moderate", False)],  # review #16
    "APOTHEOSIS": [("__unupgraded", 8, "strong", False)],
    "CRESCENT_SPEAR": [("star_cost_source", 3, "strong", True)],  # Ironclad never supplies
    "FASTEN": [("__defends", 4, "strong", True)],  # review #17
    "HELLRAISER": [("__strike_named", 4, "strong", True), ("draw_engine", 1, "mild", False)],
    "PANACHE": [("draw_engine", 1, "moderate", False)],
    "AUTOMATION": [("draw_engine", 2, "moderate", False)],
}

# anti-synergy: penalty when a tag IS well-represented (review: Battle Trance draw-lock,
# Panic Button block-lock, Expect a Fight energy-lock)
ANTI: dict[str, list[tuple[str, int, str]]] = {
    "BATTLE_TRANCE": [("draw_engine", 2, "mild")],
    # shadow review 2026-07-24: "Second Wind and Stoke get in each other's way" --
    # two whole-hand value-dumpers can't both fire; dock either into the other
    "SECOND_WIND": [("hand_dump", 1, "strong")],
    "STOKE": [("hand_dump", 1, "strong")],
    "PANIC_BUTTON": [("block_engine", 2, "moderate")],
    "EXPECT_A_FIGHT": [("energy_source", 1, "mild")],
}

COPY_CAP = {"BARRICADE"}
# review #4/#5: controlled exhaust = thinning value; True Grit only once upgraded.
# Float = scale on w_controlled_exhaust (True = 1.0). STOKE 2.0: owner draft A/B
# leg-3 (X9VM7AR5PF, 2026-07-24) — "the random cards you derive from Stoke
# shredding strikes and defends is almost always better value than Strikes/
# Defends... I'm underestimating Stoke as a card (especially early)". Whole-hand
# shred converts SEVERAL basics per play, so it outscales the one-card thinners;
# the basics/6 scaling already fades it as the deck outgrows its basics.
CONTROLLED_EXHAUST: dict[str, bool | str | float] = {
    "BRAND": True, "BURNING_PACT": True, "TRUE_GRIT": "upgraded",
    "STOKE": 2.0,
}
# review #5/#6/#15/#30: the upgrade crosses a class boundary
UPGRADE_UNLOCKS = {"TRUE_GRIT", "STAMPEDE", "ARMAMENTS", "APOTHEOSIS", "PYRE"}

# ---------------------------------------------------------------- provides (audit + weights)
# Frozen from the 12-agent audit output; magnitude weights below override the default 1.
PROVIDES: dict[str, list[str]] = {
    "BASH": ["vulnerable_source"],
    "FALLING_STAR": ["vulnerable_source", "weak_source", "front_load"],
    "THUNDERCLAP": ["vulnerable_source", "aoe"],
    "UPPERCUT": ["vulnerable_source", "weak_source"],
    "SHOCKWAVE": ["vulnerable_source", "weak_source", "aoe"],
    "TREMBLE": ["vulnerable_source"],
    "TAUNT": ["vulnerable_source"],
    "DOMINATE": ["vulnerable_source", "strength_source"],
    "DEBILITATE": ["vulnerable_source"],
    "MOLTEN_FIST": ["vulnerable_source"],
    "BULLY": ["vulnerable_payoff"],
    "CRUELTY": ["vulnerable_payoff"],
    "VICIOUS": ["vulnerable_payoff", "draw_engine"],
    "DISMANTLE": ["vulnerable_payoff"],
    # exhaust
    "TRUE_GRIT": ["exhaust_enabler", "block_engine"],
    "SECOND_WIND": ["exhaust_enabler", "block_engine", "hand_dump"],
    "FIEND_FIRE": ["exhaust_enabler", "big_single_hit"],
    "BURNING_PACT": ["exhaust_enabler", "draw_engine", "deck_thinning"],
    "BRAND": ["exhaust_enabler", "strength_source", "deck_thinning"],
    "THRASH": ["exhaust_enabler", "multi_hit"],
    "CINDER": ["exhaust_enabler", "big_single_hit"],
    "STOKE": ["exhaust_enabler", "hand_dump"],
    "SHIV": ["exhaust_enabler"],
    "CLOAK_AND_DAGGER": ["exhaust_enabler", "block_engine"],
    "UP_MY_SLEEVE": ["exhaust_enabler", "multi_hit"],
    "LUMINESCE": ["exhaust_enabler", "energy_source"],
    "OFFERING": ["self_hp_loss_source", "energy_source", "draw_engine", "front_load"],
    "HEMOKINESIS": ["self_hp_loss_source", "front_load"],
    "BLOODLETTING": ["self_hp_loss_source", "energy_source"],
    "HELLRAISER": ["self_hp_loss_source"],
    "BLOOD_WALL": ["block_engine", "self_hp_loss_source"],
    "BRAND_STR": [],
    "ASHEN_STRIKE": ["exhaust_payoff"],
    "DARK_EMBRACE": ["exhaust_payoff", "draw_engine"],
    "FEEL_NO_PAIN": ["exhaust_payoff", "block_engine"],
    "PACTS_END": ["exhaust_payoff", "aoe"],
    "FORGOTTEN_RITUAL": ["exhaust_payoff", "energy_source"],
    "EVIL_EYE": ["exhaust_payoff", "block_engine"],
    "DRUM_OF_BATTLE": ["draw_engine"],
    # strength / hits
    "INFLAME": ["strength_source"],
    "DEMON_FORM": ["strength_source", "power_setup"],
    "SETUP_STRIKE": ["strength_source"],
    "FIGHT_ME": ["strength_source", "multi_hit"],
    "TWIN_STRIKE": ["multi_hit"],
    "SWORD_BOOMERANG": ["multi_hit"],
    "PECK": ["multi_hit"],
    "CELESTIAL_MIGHT": ["multi_hit"],
    "EXTERMINATE": ["multi_hit", "aoe"],
    "CONFLAGRATION": ["multi_hit", "aoe"],
    "WHIRLWIND": ["multi_hit", "aoe"],
    "VOLLEY": ["multi_hit"],
    "RAGE": ["attack_density_payoff", "block_engine"],
    "STAMPEDE": ["attack_density_payoff"],
    "ENVENOM": ["attack_density_payoff", "poison_source"],
    "JUGGLING": ["attack_density_payoff"],
    "AGGRESSION": ["attack_density_payoff"],
    "PANACHE": ["attack_density_payoff", "aoe"],
    "AUTOMATION": ["energy_source"],
    # big hits / expensive attacks (expensive_attack also auto-derived below)
    "BLUDGEON": ["big_single_hit"],
    "HEMOKINESIS_BIG": [],
    "MANGLE": ["big_single_hit"],
    "STOMP": ["aoe"],
    "GIANT_ROCK": ["big_single_hit"],
    "KINGLY_PUNCH": ["big_single_hit"],
    "ULTIMATE_STRIKE": ["big_single_hit"],
    "SEEKER_STRIKE": ["big_single_hit"],
    "BODY_SLAM": ["block_payoff"],
    # block
    "SHRUG_IT_OFF": ["block_engine", "draw_engine"],
    "IRON_WAVE": ["block_engine"],
    "IMPERVIOUS": ["block_engine"],
    "FLAME_BARRIER": ["block_engine"],
    "STONE_ARMOR": ["block_engine", "power_setup"],
    "BARRICADE": ["block_payoff", "power_setup"],
    "JUGGERNAUT": ["block_payoff", "power_setup"],
    "ULTIMATE_DEFEND": ["block_engine"],
    "UNMOVABLE": ["block_payoff"],
    "PROLONG": ["block_payoff"],
    "EQUILIBRIUM": ["block_engine", "retain"],
    "PANIC_BUTTON": ["front_load"],
    # draw / energy
    "BATTLE_TRANCE": ["draw_engine"],
    "POMMEL_STRIKE": ["draw_engine"],
    "ACROBATICS": ["draw_engine"],
    "MASTER_OF_STRATEGY": ["draw_engine", "front_load"],
    "PYRE": ["energy_source", "power_setup"],
    "RELAX": ["energy_source", "block_engine"],
    "PRODUCTION": ["energy_source"],
    "SPOILS_MAP": [],
    # misc engines
    "ANGER": ["attack_density_payoff"],
    "RAMPAGE": [],
    "FEED": [],
    "DARK_SHACKLES": ["front_load"],
    "NOT_YET": [],
    "INFERNAL_BLADE": ["attack_generator"],
    "DISCOVERY": ["attack_generator"],
    "SECRET_WEAPON": ["attack_generator"],
    "METAMORPHOSIS": ["attack_generator"],
    "MAYHEM": [],
    "HAVOC": [],
    "BOLAS": ["multi_hit"],
    "ONE_TWO_PUNCH": ["attack_density_payoff"],
    "LETHALITY": ["exhaust_enabler"],  # review #22: ethereal self-exhaust = fodder
    "PERFECTED_STRIKE": [],
    "OMNISLICE": ["aoe"],
    "FISTICUFFS": ["block_engine"],
    "SLICE": [],
    "FLASH_OF_STEEL": [],
    "DRAMATIC_ENTRANCE": ["aoe", "front_load"],
    "SNAP": ["companion_attack", "retain"],
    "UNLEASH": ["companion_attack"],
    "RATTLE": ["companion_attack", "multi_hit"],
    "BODYGUARD": ["summon_source"],
    "PULL_AGGRO": ["summon_source", "block_engine"],
    "FASTEN": ["block_payoff", "power_setup"],
    "ARMAMENTS": ["block_engine"],
    "APOTHEOSIS": [],
    "HEADBUTT": [],
    "COSMIC_INDIFFERENCE": ["block_engine"],
    "CASCADE": [],
    "EXPECT_A_FIGHT": ["energy_source"],
    "SPITE": [],
    "RUPTURE": ["power_setup"],
    # Owner 2026-08-20: Inferno = important hp-loss card AND aoe (6 to ALL per
    # on-turn hp loss); its own 1/turn start-of-turn loss makes it a source too
    "INFERNO": ["self_hp_loss_source", "aoe", "power_setup"],
    "TEAR_ASUNDER": ["big_single_hit"],
}

# per-proc autoblock (review #12/#26): recurring block counts as MORE than one card
WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "STONE_ARMOR": {"block_engine": 3.0},   # Plating procs every turn
    "FEEL_NO_PAIN": {"block_engine": 2.0},  # procs per exhaust
    "RAGE": {"block_engine": 2.0},          # procs per attack
}


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    tags: dict[str, dict] = {}

    def entry(cid: str) -> dict:
        return tags.setdefault(cid, {})

    for cid, plist in PROVIDES.items():
        if not plist or cid not in catalog:
            continue
        prov: dict[str, float] = {}
        text = catalog[cid].get("text") or ""
        for tag in plist:
            weight = 1.0
            # stack-magnitude weighting (review #1): Apply N Vulnerable/Weak
            if tag in ("vulnerable_source", "weak_source"):
                kw = "Vulnerable" if tag == "vulnerable_source" else "Weak"
                if m := re.search(rf"Apply (\d+) {kw}", text):
                    weight = float(m.group(1))
            weight = WEIGHT_OVERRIDES.get(cid, {}).get(tag, weight)
            prov[tag] = weight
        entry(cid)["provides"] = prov

    # expensive_attack auto-derivation: any Attack costing 2+ is a Stampede-class
    # end-of-turn candidate / Bloodletting-class energy sink (review #25)
    for cid, c in catalog.items():
        if not isinstance(c, dict) or c.get("type") != "Attack":
            continue
        try:
            if int(c.get("cost") or "0") >= 2:
                entry(cid).setdefault("provides", {})["expensive_attack"] = 1.0
        except ValueError:
            pass

    for cid, needs in NEEDS.items():
        entry(cid)["needs"] = [
            {"tag": t, "threshold": thr, "strength": s, "penalty": pen}
            for t, thr, s, pen in needs
        ]
    for cid, antis in ANTI.items():
        entry(cid)["anti"] = [
            {"tag": t, "threshold": thr, "strength": s} for t, thr, s in antis
        ]
    for cid in COPY_CAP:
        entry(cid)["copy_cap"] = True
    for cid, v in CONTROLLED_EXHAUST.items():
        entry(cid)["controlled_exhaust"] = v
    for cid in UPGRADE_UNLOCKS:
        entry(cid)["upgrade_unlocks"] = True

    unknown = [cid for cid in tags if cid not in catalog]
    if unknown:
        raise SystemExit(f"ids not in catalog: {unknown}")

    OUT.write_text(json.dumps({
        "note": "card-pass step 2 tag table (owner-reviewed 2026-07-12; "
                "CARD_PASS_STEP2_PROPOSAL.md review log is the authority). "
                "Rebuild: scripts/build_draft_tags.py",
        "tags": dict(sorted(tags.items())),
    }, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(tags)} cards "
          f"({sum(1 for t in tags.values() if t.get('needs'))} with needs)")


if __name__ == "__main__":
    main()
