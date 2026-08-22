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
# Star pair (owner design 2026-08-20): star_source (star-GIVING cards
# provide; star-COST cards need it strong+penalty -- draft veto in
# standard.py stays as backstop) and star_sink (star-cost cards provide;
# PURE star-givers need it with penalty -- pointless without sinks). Cards
# giving stars as a RIDER (Solar Strike dmg+1 star; Knockout Blow dmg+5 on
# kill, weight mild for the kill condition) provide star_source, need nothing.
# Audit #2 new-tag vocabulary (owner approved 2026-08-20, category 1):
# shiv_source, doom_source, soul_source, orb_source, status_source. Owner
# notes: mostly off-color, minor for Ironclad, BANKED for future classes;
# status_source approved with no providers yet -- Defect/Regent pools carry
# status-card generators that feed Rocket Punch-class payoffs, fill in as
# cards appear. Pseudo-tags __skills/__powers/__zero_cost are built-in-field
# counts (drafttags.deck_tag_weights); __ethereal is TEXT-based and lands
# with its first consumer via the card-effects KB.
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
    "FIEND_FIRE": [("draw_engine", 1, "mild", False)],  # +hand_dump family, item 56
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
    # item 74 owner reshape: big_single_hit need DROPPED (review #8 superseded)
    "BOLAS": [("strength_source", 1, "moderate", False)],
    # Item 66 (owner): don't PENALIZE the X-cost for needing energy, but it
    # improves with it -- bonus-only, the exact Whirlwind shape. (Owner:
    # Cascade can pull 3-cost cards out for 1; Whirlwind is the below-rate one.)
    "CASCADE": [("__attacks", 10, "moderate", False),
                ("energy_source", 1, "moderate", False)],
    "CLOAK_AND_DAGGER": [("attack_density_payoff", 1, "mild", False)],
    # Item 76 (owner reshape, supersedes review #11): Havoc's value is
    # CHEATING OUT expensive cards and powers (a power played off Havoc
    # exhausts for free -- powers leave play anyway), not attack density.
    # Downside: burning a valuable. Topdeck synergy (Headbutt, Ironclad's
    # only one) + Cascade comparison ('no exhaust is actually an advantage')
    # noted. 'Not a very good card this patch' -- owner.
    "HAVOC": [("expensive_attack", 1, "moderate", False),
              ("__powers", 2, "moderate", False)],
    "PRIMAL_FORCE": [("__basics", 5, "moderate", False)],
    "SETUP_STRIKE": [("multi_hit", 2, "mild", False)],
    "UP_MY_SLEEVE": [("strength_source", 1, "moderate", False)],
    "RATTLE": [("companion_attack", 2, "strong", True),
               ("summon_source", 1, "strong", True)],  # owner: no Osty, no card
    "SNAP": [("summon_source", 1, "strong", True)],
    "UNLEASH": [("summon_source", 1, "strong", True)],
    # ---- self-HP-loss package
    "SPITE": [("self_hp_loss_source", 1, "moderate", True)],
    "RUPTURE": [("self_hp_loss_source", 1, "strong", True)],  # Act-1 window applies
    # Owner 2026-08-20 (new-discovery pass): Inferno self-feeds its trigger
    # (loses 1 hp at turn start) so no penalty, but real sources make it an
    # engine; Tear Asunder pays off on ANY hp loss ('doesn't specify why you
    # lost HP' -- enemy chip counts), decent solo -> moderate bonus, no penalty.
    "INFERNO": [("self_hp_loss_source", 1, "strong", False)],
    "TEAR_ASUNDER": [("self_hp_loss_source", 1, "moderate", False)],
    # (Bombardment's exhaust_enabler need was ALREADY in the July table above;
    # owner decode 2026-08-20 confirms it: prefers exhausted over 3 energy but
    # bootstraps by direct play. Music Box interplay in relic_notes.)
    # Audit #2 §2 approvals (owner 2026-08-20): item 1 as proposed; item 3
    # corrected -- Cloak of Stars costs 1 STAR (catalog is blind to star_cost;
    # verified from live payloads, 4 observations) -> star pair semantics.
    "ACCURACY": [("shiv_source", 2, "strong", True)],
    "CLOAK_OF_STARS": [("star_source", 1, "strong", True)],
    # Item 6 (owner 2026-08-20): Hidden Cache is a PURE star giver -- not
    # literally unplayable, but 'effectively nothing' without star-cost
    # cards; owner discourages on Ironclad. star-pair needs star_sink.
    # GENESIS decode banked (not yet discovered/in catalog): '2 Energy, at
    # the start of your turn gain 2 stars' -- so strong an enabler it might
    # kernel a star synergy, 'still a little dicey'; add on discovery with a
    # milder star_sink need.
    "HIDDEN_CACHE": [("star_sink", 1, "strong", True)],
    # Item 7 (owner IMPORTANT clarification 2026-08-20): ALL Osty-referencing
    # cards REQUIRE Osty -- outside Necrobinder he does not exist without a
    # 'Summon' card, and he dies after tanking (analogous to stars for
    # Regent; Necrobinder's base relic summons 1/turn so SHE always has one).
    # Osty attacks also ignore the owner's Str/Weak/Vigor entirely
    # (fx.companion gates them in combat.py + rollout).
    "POKE": [("summon_source", 1, "strong", True)],
    # Item 8 (owner deferred to me): block_engine asserts the deck GENERATES
    # block (Body Slam-class consumers); Dex only AMPLIFIES block plays, so
    # dex cards get the need in the amplifier direction instead -- bonus, no
    # penalty (worth more where block cards exist). Footwork pre-ruled by
    # the same precedent (its 2 Dex > Prowess's 1 -> moderate).
    "PROWESS": [("block_engine", 1, "mild", False)],
    "FOOTWORK": [("block_engine", 1, "moderate", False)],
    # Item 14 (owner; Necrobinder): Shroud needs A LOT of doom to be value
    # (per-turn power source or many doom cards -- Ironclad unlikely) ->
    # threshold 2. NO block_engine provides: the block is conditional on
    # doom landing, and provides can't be gated on needs -- a doomless deck
    # must not count Shroud as block generation (Body Slam-class consumers).
    "SHROUD": [("doom_source", 2, "strong", True)],
    # Item 15 (owner + audit's too-good-to-be-true flag both right):
    # Devastate costs 4 STARS on top of 1 energy (3 live observations;
    # catalog star-blindness again) -> star-pair need.
    "DEVASTATE": [("star_source", 1, "strong", True)],
    # Item 17 (approved; owner: Souls are a NECROBINDER mechanic -- this card
    # depends on soul generation to function). Providers exist in-table
    # (Reave, Severance) per the verifier amendment.
    "HAUNT": [("soul_source", 1, "strong", True)],
    # Item 20 (approved): Havoc/Cascade family -- value = avg deck quality
    "CATASTROPHE": [("__attacks", 10, "moderate", False)],
    # Item 22 (approved): Focus-this-turn is dead without orbs (owner);
    # channelers provide orb_source so the need is satisfiable in-pool
    "HOTFIX": [("orb_source", 1, "strong", True)],
    # Item 27: moderate, no penalty (fires naturally on dumped-out turns;
    # Retain waits for the moment)
    "RESTLESSNESS": [("hand_dump", 1, "moderate", False)],
    # Item 31: retrieval wants a premium fetch target (Cosmic Indifference
    # convention)
    "GRAVEBLAST": [("big_single_hit", 1, "mild", False)],
    # Item 33: trigger frequency rides cycling speed
    "STRATAGEM": [("draw_engine", 1, "mild", False)],
    # Item 35: threshold 2 like Shroud (owner: needs consistent doom), but
    # NO penalty -- the 6-block baseline keeps it playable
    "DEATHS_DOOR": [("doom_source", 2, "strong", False)],
    "TIMES_UP": [("doom_source", 1, "strong", True)],  # item 64: zero without Doom
    "KINGLY_KICK": [("draw_engine", 1, "mild", False),
                    ("energy_source", 1, "moderate", False)],  # item 68
    "KINGLY_PUNCH": [("draw_engine", 1, "moderate", False)],  # item 77/4c group
    "REND": [("vulnerable_source", 2, "moderate", False),
             ("weak_source", 1, "mild", False)],  # item 80
    "GUIDING_STAR": [("star_source", 1, "strong", True)],
    "PAGESTORM": [("__ethereal", 4, "strong", True)],
    "PILLAR_OF_CREATION": [("attack_generator", 2, "strong", True)],
    "GUNK_UP": [("strength_source", 1, "mild", False)],  # item 44 multi-hit scaler
    # Items 47-48 (approved 2026-08-21): evoke-dependent, dead orb-less.
    # Owner note: Multi-Cast is UNUSUALLY GOOD with Plasma (X energy) or
    # Dark (X x banked damage) -- orb-type nuance for the future Defect pass.
    "MULTI_CAST": [("orb_source", 1, "strong", True)],
    "THUNDER": [("orb_source", 1, "strong", True)],
    # Item 49 (rollout half shipped in lane 4c; tag half per the 4c decode:
    # the group needs draw_engine as bonus, no penalty -- natural draws feed it)
    "MURDER": [("draw_engine", 1, "moderate", False)],
    # Item 50 (owner YES): attack-heavy decks dock Second Wind -- see ANTI.
    # Item 52 (approved + item-7 family rule): Osty attack -> summon needed
    "SQUEEZE": [("companion_attack", 2, "moderate", False),
                ("summon_source", 1, "strong", True)],
    # Item 53 (approved WITH verifier correction: power_setup does NOT mark
    # every Power -- use the __powers deck count instead)
    "SYNTHESIS": [("__powers", 2, "moderate", False)],
    # Item 54 (approved)

    # Item 55 (owner: DEAD in a default 3-energy deck -- needs +1 energy or
    # a cost cheat; 'not playable in a default deck')
    "BURY": [("energy_source", 1, "strong", True)],
    # Owner follow-up: Meteor Strike (5 energy, Defect) is the other >3-cost
    # card -- needs +2 energy above base, threshold 2. (Its Channel 3 Plasma
    # partly self-repays NEXT turns -- 3 energy/turn passive -- but the cast
    # itself still needs the gate.)
    "METEOR_STRIKE": [("energy_source", 2, "strong", True)],
    # Item 60/54 energy needs REVERTED: redundant with the dedicated
    # penalty_draw_no_energy machinery (July design deliberately chose
    # penalty-only for draw-vs-energy; the pinned Pommel test enforces it)
    "SIC_EM": [("summon_source", 1, "strong", True)],
    "HIGH_FIVE": [("summon_source", 1, "strong", True)],
    "FLATTEN": [("summon_source", 1, "strong", True)],
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
    "SECOND_WIND": [("hand_dump", 1, "strong"),
                    ("__attacks", 12, "moderate")],  # item 50 owner YES
    "STOKE": [("hand_dump", 1, "strong")],
    "PANIC_BUTTON": [("block_engine", 2, "moderate")],
    "EXPECT_A_FIGHT": [("energy_source", 1, "mild")],
    # Item 45 (approved 2026-08-21): fires only with ZERO attacks in hand --
    # near-dead in attack-heavy decks (__attacks now computed, bug fixed)
    "IMPATIENCE": [("__attacks", 8, "moderate")],
    # Item 74: Aggression fetches RANDOM attacks from discard -- a
    # strike-heavy deck makes bad pulls (owner: pairs with strike-REMOVAL)
    "AGGRESSION": [("__basics", 6, "moderate")],
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
    "PURITY": 2.0,  # item 19 approved: up to 3 chosen exhausts per play
}
# review #5/#6/#15/#30: the upgrade crosses a class boundary
# HOLOGRAM added 2026-08-20 (owner: dropping Exhaust on upgrade fundamentally
# changes the card -- 'upgraded Hologram without exhaust is way better' even
# on Ironclad; repeatable discard recursion vs a one-shot).
UPGRADE_UNLOCKS = {"TRUE_GRIT", "STAMPEDE", "ARMAMENTS", "APOTHEOSIS", "PYRE",
                   "HOLOGRAM",
                   # items 29/31 (2026-08-21): upgrades REMOVE Exhaust --
                   # one-shot -> permanent cycler / repeatable recursion
                   "THINKING_AHEAD", "GRAVEBLAST",
                   "KNOW_THY_PLACE",  # item 32: upgrade drops Exhaust
                   "INFERNAL_BLADE",  # item 58 owner: upgrades to 0 cost -- meaningful
                   "DISCOVERY"}  # item 75: upgrade removes Exhaust

# ---------------------------------------------------------------- provides (audit + weights)
# Frozen from the 12-agent audit output; magnitude weights below override the default 1.
PROVIDES: dict[str, list[str]] = {
    "BASH": ["vulnerable_source"],
    "FALLING_STAR": ["vulnerable_source", "weak_source", "front_load"],
    "THUNDERCLAP": ["vulnerable_source", "aoe"],
    "UPPERCUT": ["vulnerable_source", "weak_source"],
    "SHOCKWAVE": ["vulnerable_source", "weak_source", "aoe"],
    "TREMBLE": ["vulnerable_source", "exhaust_enabler"],  # item 73; flag struck (11th)
    "TAUNT": ["vulnerable_source", "block_engine"],  # item 63: Defend-grade block
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
    "FIEND_FIRE": ["exhaust_enabler", "big_single_hit", "hand_dump"],  # item 56
    "BURNING_PACT": ["exhaust_enabler", "draw_engine", "deck_thinning"],
    "BRAND": ["exhaust_enabler", "strength_source", "deck_thinning"],
    "THRASH": ["exhaust_enabler", "multi_hit"],
    "CINDER": ["exhaust_enabler", "big_single_hit"],
    "STOKE": ["exhaust_enabler", "hand_dump"],
    "SHIV": ["exhaust_enabler"],
    # shiv_source added 2026-08-20 (Accuracy dependency; Shivs exhaust, hence
    # the July exhaust_enabler reads stay)
    "CLOAK_AND_DAGGER": ["exhaust_enabler", "block_engine", "shiv_source"],
    "UP_MY_SLEEVE": ["exhaust_enabler", "multi_hit", "shiv_source"],
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
    # Item 74 (owner reshape): power_setup IS right (the planner needs the
    # setup tag to ever play it) + a soft per-turn card-advantage engine
    # (draw_engine). Pairing corrected: NOT big single hits -- best with
    # strike-removal and cheap repeat-play scalers (Thrash/Rampage; NOT
    # on-draw effects like Kingly Punch/Kick); a fetched Bludgeon can land
    # on an awkward turn. Encoded as the __basics anti below.
    "AGGRESSION": ["attack_density_payoff", "power_setup", "draw_engine"],
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
    # Item 71: big_single_hit DROPPED (9 dmg is not Bludgeon-class -- the
    # reverse saturation trap); choose-1-of-3 tutoring = selective draw.
    # fx.tutors now earns the 0-cost/surplus early-play nudge in combat.
    "SEEKER_STRIKE": ["draw_engine"],
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
    # item 59; flag struck (8th)
    "MASTER_OF_STRATEGY": ["draw_engine", "front_load", "exhaust_enabler"],
    "PYRE": ["energy_source", "power_setup"],
    "RELAX": ["energy_source", "block_engine"],
    "PRODUCTION": ["energy_source"],
    "SPOILS_MAP": [],
    # misc engines
    "ANGER": ["attack_density_payoff"],
    "RAMPAGE": [],
    "FEED": [],
    "DARK_SHACKLES": ["front_load"],
    "INFERNAL_BLADE": ["attack_generator", "exhaust_enabler"],  # item 58; flag struck (7th)
    # Item 62 (owner): a TUTOR, not a creator -- attack_generator REMOVED
    # (Pillar-class creation triggers never fire off a fetch); selective
    # draw is the honest provide. Enabler base-only (upgrade drops Exhaust).
    "SECRET_WEAPON": ["draw_engine", "exhaust_enabler"],
    # Item 61 re-examined with the owner's Glass decode: on Ironclad the
    # first Channel grants a free slot and the SECOND Glass pushes out
    # (evokes) the first -- 9x2 single-target + ~8 AoE evoke now + a
    # decaying 4/3/2/1 AoE stream. Front-loaded AoE is real: aoe at half
    # weight + orb_source; multi_hit as proposed.
    "REFRACT": ["multi_hit", "orb_source", "aoe"],
    # Item 64 (approved, flag struck 10th): doom-scaling nuke
    "TIMES_UP": ["exhaust_enabler"],
    # Item 76: every play exhausts the played card -- a real enabler event
    # (flag struck, 12th)
    "HAVOC": ["exhaust_enabler"],
    # Item 79 (approved; Silent): next-turn draw fires at TURN START, so
    # unlike in-turn riders it is NOT dead under Fiddle
    "PREDATOR": ["draw_engine"],
    # Item 80 (approved + owner refinement): payoff for ANY unique debuff
    # (stacking vuln adds nothing) -> vulnerable_payoff is 'moderate at
    # best'; weak counts too. Planner term SHIPPED: fx.dmg_per_unique_debuff
    # (+N per unique debuff at plan start; owner's family: vuln/weak/poison/
    # doom/shrunken/str-down).
    "REND": ["vulnerable_payoff"],
    # Item 65 (lane 4d token-creation): a GENUINE creator -- the 0-cost copy
    # is created, so Pillar-class triggers fire (unlike Secret Weapon's fetch)
    "ADAPTIVE_STRIKE": ["attack_generator"],
    # Item 68 (approved + owner: '4 cost' -- but the per-draw cost decay
    # SOFTENS the gate vs Bury's hard 4, hence moderate/no-penalty)
    "KINGLY_KICK": ["big_single_hit"],
    # Item 69 (dispute upheld, owner concurs): next-Skill-costs-0 is NOT
    # energy_source (would falsely pay Whirlwind-class surplus needs and
    # trip Expect a Fight's anti). No honest existing tag; left untagged.
    # DECODE: the rider applies to the next skill played THIS COMBAT, not
    # necessarily the next card.
    "DISCOVERY": ["attack_generator"],  # item 75: half weight below; upgrade class
    "METAMORPHOSIS": ["attack_generator"],
    "MAYHEM": [],
    "BOLAS": ["multi_hit"],
    "ONE_TWO_PUNCH": ["attack_density_payoff"],
    "LETHALITY": ["exhaust_enabler"],  # review #22: ethereal self-exhaust = fodder
    # Defile (audit #2 item 4, owner 2026-08-20): same Lethality precedent --
    # ethereal auto-exhaust IF UNPLAYED is a passive side benefit to exhaust
    # benefactors. Owner ruling: NOT the 'wants-to-be-exhausted' class (that
    # means DELIBERATE exhaustion, Howl/Bombardment); you normally play it.
    # Necrobinder note banked: that class carries most Ethereal cards now,
    # and Ethereal is an indirect exhaust with heavy interaction.
    "DEFILE": ["exhaust_enabler"],
    # Flick-Flack (item 5, approved): plain aoe. Sly decode (owner): 'this
    # card is played when DISCARDED' -- benefits from discard outlets;
    # primarily Silent. Sly/discard_source pair banked for future classes
    # (no Ironclad discard outlets in the current pool).
    "FLICK_FLACK": ["aoe"],
    # Item 8 ruling: strength_source only (block_engine half struck -- Dex is
    # an amplifier, not a generator; the needs table carries that direction)
    "PROWESS": ["strength_source"],
    # Item 9 (approved + amendment): Soul token = 0-cost 'Draw 2. Exhaust.'
    # soul_source is Necrobinder-domain (owner) -- future-class pair like Sly
    "REAVE": ["exhaust_enabler", "draw_engine", "soul_source"],
    # Item 10 (approved): all value in energy icons (Luminesce class).
    # NO upgrade_unlocks: '+Retain' is ordinary upgrade value, the flag is
    # for step-change unlocks (True Grit/Armaments class -- owner ruling).
    "WISP": ["energy_source"],
    # Item 11 (owner 2026-08-20): orb decode -- unlike stars/Osty, orb cards
    # are NOT dead solo (the game grants a first orb slot on your first
    # channel); merely underrated outside Defect. Orb model CONFIRMED by
    # owner (channel -> slot, per-turn passive + evoke on leaving, overflow
    # evokes oldest, Focus scales both) with StS2 BASE NUMBERS:
    #   Frost: 2 block/turn passive, evoke 5.
    #   Lightning: 3 dmg to RANDOM target/turn, evoke 8.
    #   Dark: evoke-ONLY damage, starts 6 at creation, +6/turn banked;
    #         evoke targets the LOWEST-HP enemy.
    #   Plasma: 1 energy/turn passive, evoke 2 -- UNAFFECTED by Focus.
    #   Glass (NEW in StS2): 4 AoE dmg to ALL enemies/turn passive, evoke =
    #         double the CURRENT passive; the passive DECAYS 1/turn (4,3,2..).
    # frost_source joins the vocabulary alongside orb_source (owner-approved).
    "COLD_SNAP": ["orb_source", "frost_source"],
    # Item 12 (approved; Regent card): plain aoe; the '-1 Str to ALL this
    # turn' rider has no synergy vocabulary (owner concurs) -- a possible
    # rollout nuance, filed.
    "CRUSH_UNDER": ["aoe"],
    # Item 13 (approved provides, flag STRUCK): exhausts itself ON PLAY =
    # active exhaust feed; NOT the deliberate-exhaust class (owner, same
    # Defile precedent -- that flag means True Grit+ target material).
    "NOT_YET": ["exhaust_enabler"],
    # Item 15: a premium hit WHEN payable (star cost carried in needs/veto)
    "DEVASTATE": ["big_single_hit"],
    # Item 18 (approved, flag struck): a card that exhausts, NOT one you
    # deliberately exhaust (3rd confirmation of the tightened class-1 rule).
    "HOLOGRAM": ["exhaust_enabler"],
    # Item 19 (approved): premium controlled mass-exhaust
    "PURITY": ["exhaust_enabler", "deck_thinning", "retain"],
    # Item 21 (approved): Shrug It Off shape
    "FINESSE": ["block_engine", "draw_engine"],
    # Item 22 amendment (owner: technically an enabler but WEAK -- keep the
    # weight low so it never outweighs real enablers)
    "HOTFIX": ["exhaust_enabler"],
    # Item 23 (semi-approved): aoe provides; the Bomb's ROLLOUT ask was
    # already shipped in lane 4b (pending queue) -- no double work.
    "THE_BOMB": ["aoe"],
    # Item 25 (approved; Silent card): front_load kept for provider-side
    # consistency (Dark Shackles pattern) though the tag is currently DEAD
    # (7 providers, zero consumers -- reserved for a big-opener need);
    # wants-exhausted flag struck (4th confirmation). The -6 Str rider is
    # now MODELED (fx.enemy_str_down: damageless AoE softens all attackers;
    # Crush Under's damaging variant rides _apply_attack).
    "PIERCING_WAIL": ["front_load", "exhaust_enabler"],
    # Item 26 (semi-approved): vigor rollout lane already shipped in the
    # player-power split; the tag is the only new piece.
    "PREP_TIME": ["power_setup"],
    # Item 27 (owner): emptying the hand is a REAL, non-trivial condition.
    # hand_dump providers are SECOND_WIND and STOKE -- but Second Wind is a
    # TRAP for Restlessness (it would exhaust Restlessness too; owner:
    # 'hard to catch with just tags'), so the need counts it optimistically.
    # Retain softens the conditional deadness (RETAIN_PENALTY_SOFTEN in
    # drafttags does this generically for retain cards now).
    "RESTLESSNESS": ["draw_engine", "energy_source", "retain"],
    # Item 28 (owner + dispute agree): star GAIN, not star_cost_source --
    # rider-giver per the star-pair design, needs nothing.
    "SOLAR_STRIKE": ["star_source"],
    # Item 29 (broadly approved): 0-cost draw-2 + topdeck-1. Synergy notes
    # banked (owner): the draws feed Kingly Punch-class draw-scalers, and
    # the TOPDECK is a (minor) Regent synergy space -- see I_AM_INVINCIBLE.
    "THINKING_AHEAD": ["draw_engine", "exhaust_enabler"],
    # Owner decode (item 29 thread): Regent, '10 Block, plays itself at end
    # of turn if on top of the draw pile'. Topdeck synergy deliberately NOT
    # a tag (owner: minor space); plain block provides.
    "I_AM_INVINCIBLE": ["block_engine"],
    # Item 30 (filed to future classes in the 'other' triage; provider baked
    # as cheap insurance -- satisfies Mirage's poison need if ever drafted)
    "DEADLY_POISON": ["poison_source"],
    # Item 31 (broadly approved, Hologram-parallel; NOT wants-exhausted)
    "GRAVEBLAST": ["exhaust_enabler"],
    # Item 32 (approved; Regent card): 0-cost double debuff
    "KNOW_THY_PLACE": ["vulnerable_source", "weak_source"],
    # Item 33 (approved; rollout tutor stays deferred per lane 4c)
    "STRATAGEM": ["draw_engine"],
    # Item 34 (approved; owner surprised it was uncovered): repeatable AoE +
    # hp-loss feeder for the Rupture/Inferno/Tear Asunder package
    "BREAKTHROUGH": ["aoe", "self_hp_loss_source"],
    # Item 35 (owner: NOT dead without doom, 'only slightly better than a
    # basic defend' -- real block baseline, unlike Shroud's zero)
    "DEATHS_DOOR": ["block_engine"],
    # Item 36 (mostly approved): 0-cost cantrip; ALSO counts toward
    # __cheap_attacks automatically -- the owner's question exposed that the
    # pseudo-tag was never computed (fixed in drafttags 2026-08-21)
    "FLASH_OF_STEEL": ["draw_engine"],
    # Item 37 (owner star catch #3; live data says star_cost 2 -- owner
    # recalled 1, payload wins, flagged): premium draw attack WHEN payable
    "GUIDING_STAR": ["draw_engine"],
    # Item 38 (approved; first __ethereal consumer -- flag-based count)
    "PAGESTORM": ["draw_engine"],
    # Item 39 (approved + owner note: attack_generator is CREAKY -- future
    # classes bring skill-generators (Silent) and per-turn colorless
    # creators (Regent power); split into a card_generator family WHEN the
    # second consumer type appears, not now)
    "PILLAR_OF_CREATION": ["block_engine"],
    # Item 40 (approved; owner: 11-for-2 under rate, orb NOT dead in hand
    # -- free first slot; evoking needs another orb)
    "SHADOW_SHIELD": ["block_engine", "orb_source"],
    # Item 41 (approved; owner: 'retain is just a keyword' -- Sow HAS it)
    "SOW": ["aoe", "retain"],
    # Item 42 (owner ruling): Thrumming Hatchet gets NO tag -- return-on-play
    # recurrence is NOT the Retain keyword, and the recurring-attack family
    # (Bolus, Make It So!) is primarily Regent space; the ROLLOUT prices the
    # recurrence instead (returns_to_hand, 4a-iii). MAKE IT SO! decode
    # banked: '0 energy, deal 6, every 3 skills you play in a turn, put this
    # into your hand' -- conditional recurrence, unmodeled.
    # Item 43 (approved): per-turn block + hp-loss power; sim already handles
    # both since the player-power lane split (the audit's verifier note
    # predates that ship).
    "CRIMSON_MANTLE": ["block_engine", "self_hp_loss_source", "power_setup"],
    # Item 44 (owner): SLIMED decode banked -- 1-cost status, exhausts when
    # played, draws 1; NOT enough to count Gunk Up as exhaust synergy. But
    # status GENERATION is 'a whole Defect synergy package now, an important
    # one' -> Gunk Up becomes status_source's FIRST provider (self-pollution
    # doubles as generation; tagged for the future per owner).
    "GUNK_UP": ["multi_hit", "status_source"],
    # Item 45 (approved): draw engine gated by the ANTI below
    "IMPATIENCE": ["draw_engine"],
    # Item 46 (approved as before -- flag struck, 6th; owner: no GUARANTEE
    # the random colorless is an attack -> generator at half weight)
    "JACK_OF_ALL_TRADES": ["attack_generator", "exhaust_enabler"],
    # Item 52: 25 base = big single hit (expensive_attack auto-derives)
    "SQUEEZE": ["big_single_hit"],
    # Item 54 (owner: discard synergy is a worthwhile SILENT category --
    # classified NOW per the status_source precedent): Acrobatics discards,
    # so it is discard_source's first provider (Sly payoffs will need it)
    "ACROBATICS": ["draw_engine", "discard_source"],
    # Item 55: Bludgeon-class hit (energy gate in needs)
    "BURY": ["big_single_hit"],
    # Item 57: vuln weight from the fixed 'applies' regex; aoe + companion
    "HIGH_FIVE": ["vulnerable_source", "aoe", "companion_attack"],
    # Meteor Strike: big hit + channels 3 Plasma (orb verifier amendment)
    "METEOR_STRIKE": ["big_single_hit", "orb_source"],
    "PERFECTED_STRIKE": [],
    "OMNISLICE": ["aoe"],
    "FISTICUFFS": ["block_engine"],
    "SLICE": [],
    "DRAMATIC_ENTRANCE": ["aoe", "front_load"],
    "SNAP": ["companion_attack", "retain"],
    "UNLEASH": ["companion_attack"],
    "RATTLE": ["companion_attack", "multi_hit"],
    "POKE": ["companion_attack"],  # item 7 approved
    # summon_source providers (owner Osty requirement): Summon-text cards
    "BODYGUARD": ["summon_source"],
    "PULL_AGGRO": ["summon_source", "block_engine"],
    "INVOKE": ["summon_source", "energy_source"],
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
    # §2 approvals 2026-08-20: Blur dispute upheld (block_engine only --
    # 'retain' is the hand keyword, Blur retains BLOCK); shiv providers baked
    # with Accuracy's need (audit dependency note); Cloak of Stars block.
    "BLUR": ["block_engine"],
    "CLOAK_OF_STARS": ["block_engine"],
}

# per-proc autoblock (review #12/#26): recurring block counts as MORE than one card
WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "STONE_ARMOR": {"block_engine": 3.0},   # Plating procs every turn
    "FEEL_NO_PAIN": {"block_engine": 2.0},  # procs per exhaust
    "RAGE": {"block_engine": 2.0},          # procs per attack
    "UP_MY_SLEEVE": {"shiv_source": 3.0},   # 3 Shivs per play
    "PURITY": {"exhaust_enabler": 3.0},     # item 19: up to 3 procs per play
    "HOTFIX": {"exhaust_enabler": 0.5},     # item 22 owner: weak enabler value
    "CRIMSON_MANTLE": {"block_engine": 3.0},  # item 43: procs every turn (Stone Armor precedent)
    "DARK_EMBRACE": {"draw_engine": 2.0},   # item 67: per-exhaust proc (FNP/Rage precedent)
    "JACK_OF_ALL_TRADES": {"attack_generator": 0.5},  # item 46: random type, no attack guarantee
    "REFRACT": {"aoe": 0.5},  # item 61: decaying Glass stream, not full AoE
    "DISCOVERY": {"attack_generator": 0.5},  # item 75 owner: 3 RANDOM cards, no attack guarantee
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
            # stack-magnitude weighting (review #1): Apply N Vulnerable/Weak.
            # Item 51 fix: combined phrasing 'Apply 3 Weak and Vulnerable'
            # left vulnerable_source at 1.0 while weak_source got 3.0.
            if tag in ("vulnerable_source", "weak_source"):
                kw = "Vulnerable" if tag == "vulnerable_source" else "Weak"
                if m := re.search(rf"Appl(?:y|ies) (\d+) (?:\w+ and )?{kw}",
                                  text, re.IGNORECASE):
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
    # Upgrade removes Exhaust (item 62 precedent ruling): these cards' self-
    # exhaust enabler provides are BASE-ONLY -- an upgraded copy in the deck
    # does not exhaust and must not count as a provider (_providers gates it)
    for cid in ("HOLOGRAM", "GRAVEBLAST", "THINKING_AHEAD", "SECRET_WEAPON",
                "DISCOVERY"):  # item 75: same upgrade-removes-Exhaust class
        entry(cid)["exhaust_drops_on_upgrade"] = True

    # Innate providers (owner rule 2026-08-20): a card that is Innate AND
    # provides a synergy tag is more likely ACTIVE turn one, so it should
    # encourage drafting its synergy pieces harder. Flag from catalog text;
    # the provider boost lives in drafttags._providers (modest -- the owner's
    # caveat: the planner may not actually play it T1).
    for cid in tags:
        text = (catalog.get(cid, {}) or {}).get("text") or ""
        if re.search(r"\bInnate\b", text):
            entry(cid)["innate"] = True
        if re.search(r"\bEthereal\b", text):
            entry(cid)["ethereal"] = True  # __ethereal counts these (item 38)

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
