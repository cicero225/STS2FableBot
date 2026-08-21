"""Card-pass step 2: the deck-context tag machinery (owner-reviewed 2026-07-12).

Uses the real data/card_draft_tags.json so the tests validate the shipped table,
mirroring how policy tests use the real policy config.
"""

from sts2bot.kb.config import load_policy_config
from sts2bot.policy.drafttags import deck_tag_weights, load_draft_tags, score_adjustment

W = load_policy_config().card_rewards
TAGS = load_draft_tags()


class C:
    def __init__(self, cid, name=None, typ="Attack", cost="1", upgraded=False):
        self.id = cid
        self.name = name or cid.replace("_", " ").title()
        self.type = typ
        self.cost = cost
        self.is_upgraded = upgraded


def _starter(strikes=5, defends=4):
    deck = [C("STRIKE_IRONCLAD", "Strike") for _ in range(strikes)]
    deck += [C("DEFEND_IRONCLAD", "Defend", typ="Skill") for _ in range(defends)]
    deck.append(C("BASH", "Bash", cost="2"))
    return deck


def test_table_loaded() -> None:
    assert TAGS, "data/card_draft_tags.json missing or empty"
    assert "provides" in TAGS["BASH"] and TAGS["BASH"]["provides"]["vulnerable_source"] == 2.0


def test_weighted_sources_feed_payoff_bonus() -> None:
    # Bully needs vulnerable_source at threshold 3 (weighted): starter Bash provides 2
    # -> partial bonus; adding Tremble (3 stacks) crosses the threshold -> larger bonus.
    base = score_adjustment("BULLY", _starter(), TAGS, W)
    with_tremble = score_adjustment("BULLY", [*_starter(), C("TREMBLE", typ="Skill")], TAGS, W)
    assert 0 < base < with_tremble


def test_pure_payoff_docked_at_zero_with_act1_window() -> None:
    # Rupture with NO self-HP-loss source: docked, but Act 1 runs at the speculative
    # discount (owner: Rupture-class cards are often worth taking in Act 1 anyway).
    act1 = score_adjustment("RUPTURE", _starter(), TAGS, W, act=1)
    act2 = score_adjustment("RUPTURE", _starter(), TAGS, W, act=2)
    assert act2 < act1 < 0
    # with an enabler the dock vanishes and the bonus applies
    fed = score_adjustment("RUPTURE", [*_starter(), C("BLOODLETTING", typ="Skill", cost="0")],
                           TAGS, W, act=2)
    assert fed > 0


def test_self_provision_keeps_enabler_pickable() -> None:
    # Dominate provides the vulnerable it needs: never docked even in an empty deck.
    assert score_adjustment("DOMINATE", [], TAGS, W, act=2) > 0
    # Tremble (bonus-only enabler per review #3): no dock without payoffs either
    assert score_adjustment("TREMBLE", [], TAGS, W, act=2) >= 0


def test_copy_cap_barricade() -> None:
    without = score_adjustment("BARRICADE", _starter(), TAGS, W)
    with_copy = score_adjustment("BARRICADE", [*_starter(), C("BARRICADE", typ="Power")],
                                 TAGS, W)
    assert with_copy <= without + W.w_copy_cap + 2.0  # dock applied (allow bonus drift)
    assert with_copy < without


def test_controlled_exhaust_thinning_value() -> None:
    # Brand in a basics-heavy deck earns the thinning bonus (review #4)...
    heavy = score_adjustment("BRAND", _starter(strikes=5, defends=4), TAGS, W)
    thin = score_adjustment("BRAND", [C("BLUDGEON", cost="3")], TAGS, W)
    assert heavy > thin
    # ...and True Grit's exhaust is only controlled once UPGRADED (review #5)
    tg_base = score_adjustment("TRUE_GRIT", _starter(), TAGS, W, is_upgraded=False)
    tg_up = score_adjustment("TRUE_GRIT", _starter(), TAGS, W, is_upgraded=True)
    # unupgraded gets the anticipation bonus instead; upgraded gets the real thing
    assert tg_up > tg_base - W.w_upgrade_unlocks


def test_stoke_shred_scale_outvalues_one_card_thinners_early() -> None:
    """Owner draft A/B leg-3 (X9VM7AR5PF, 2026-07-24): Stoke's whole-hand shred turns
    basics into random cards — better than the basics, ESPECIALLY early. Stoke carries
    controlled_exhaust=2.0: on a starter-heavy deck it must out-bonus a 1.0-scale
    thinner (Brand), and the edge must fade as the deck outgrows its basics."""
    early_stoke = score_adjustment("STOKE", _starter(), TAGS, W)
    early_brand = score_adjustment("BRAND", _starter(), TAGS, W)
    assert early_stoke > early_brand
    # thin deck with NO exhaust payoffs (an FNP here would rightly earn Stoke the
    # deficit-feed bonus instead — that lane has its own test)
    thin = [C("BLUDGEON", cost="3")]
    late_stoke = score_adjustment("STOKE", thin, TAGS, W)
    # early shred credit (basics-scaled part) exceeds what's left of it late
    assert early_stoke > late_stoke


def test_colossus_needs_vuln_beyond_bash() -> None:
    """Shadow review 2026-07-24: "Colossus doesn't really work unless a source of
    vulnerable bigger than Bash already exists." Bash (2.0, in every starter) earns
    HALF credit at the raised threshold 4; a real vuln package earns full."""
    bash_only = score_adjustment("COLOSSUS", _starter(), TAGS, W)
    stacked = score_adjustment("COLOSSUS", [*_starter(), C("TREMBLE", typ="Skill")],
                               TAGS, W)
    assert bash_only < stacked
    assert bash_only <= W.w_tag_bonus * 0.5 + 0.01  # half credit, nothing more


def test_hand_dump_collision_second_wind_vs_stoke() -> None:
    """Shadow review: "Second Wind and Stoke get in each other's way" — two whole-hand
    value-dumpers can't both fire. Either into a deck holding the other gets docked;
    Fiend Fire (a finisher you hold, not a value dump) is exempt."""
    base_sw = score_adjustment("SECOND_WIND", _starter(), TAGS, W)
    sw_into_stoke = score_adjustment("SECOND_WIND", [*_starter(), C("STOKE", typ="Skill")],
                                     TAGS, W)
    assert sw_into_stoke < base_sw
    base_st = score_adjustment("STOKE", _starter(), TAGS, W)
    st_into_sw = score_adjustment("STOKE", [*_starter(), C("SECOND_WIND", typ="Skill")],
                                  TAGS, W)
    assert st_into_sw < base_st
    ff_into_stoke = score_adjustment("FIEND_FIRE", [*_starter(), C("STOKE", typ="Skill")],
                                     TAGS, W)
    ff_base = score_adjustment("FIEND_FIRE", _starter(), TAGS, W)
    assert ff_into_stoke >= ff_base  # no dump-collision dock for the finisher


def test_bloodletting_fed_by_hand_dumpers() -> None:
    """Shadow review: Bloodletting->Stoke is a clean play pattern, and the shred is
    "an invisible source of cards that might need bloodletting" — a deck holding a
    hand-dumper values Bloodletting higher."""
    base = score_adjustment("BLOODLETTING", _starter(), TAGS, W)
    with_stoke = score_adjustment("BLOODLETTING", [*_starter(), C("STOKE", typ="Skill")],
                                  TAGS, W)
    assert with_stoke > base


def test_controlled_exhaust_counts_curses_double() -> None:
    """Owner post-fight draft (LKG20K3FBE): took True Grit because its exhaust is the
    ONLY in-fight mitigation for an Eternal curse (Bad Luck). A cursed deck values
    targeted exhaust more than the same deck without the curse."""
    thin = [C("BLUDGEON", cost="3"), C("SHRUG_IT_OFF", typ="Skill")]
    cursed = [*thin, C("BAD_LUCK", typ="Curse", cost="0")]
    assert (score_adjustment("BRAND", cursed, TAGS, W)
            > score_adjustment("BRAND", thin, TAGS, W))
    # edge cases (owner): retain curses park in hand, ethereal curses exhaust
    # themselves — neither needs an enabler
    parked = C("POOR_SLEEP", typ="Curse", cost="0")
    parked.description = "Unplayable. Retain."
    self_solving = C("FLEETING_DREAD", typ="Curse", cost="0")
    self_solving.description = "Unplayable. Ethereal."
    soft_cursed = [*thin, parked, self_solving]
    assert (score_adjustment("BRAND", soft_cursed, TAGS, W)
            == score_adjustment("BRAND", thin, TAGS, W))


def test_deficit_feeding_rewards_the_provider_the_deck_starves_for() -> None:
    """Owner shadow review #2 (Uppercut+ over Colossus): "the deck seemed to lack
    vulnerable appliers... so I picked a card that gave both." Uppercut (provides
    vulnerable_source) into a deck holding Molten Fist behind a lone Bash earns the
    deficit-feed bonus; into the same deck without the starving needer it earns less;
    with the tag well-supplied (threshold+1 reached) the bonus is gone."""
    starving = [*_starter(), C("MOLTEN_FIST")]
    fed = score_adjustment("UPPERCUT", starving, TAGS, W)
    no_needer = score_adjustment("UPPERCUT", _starter(), TAGS, W)
    assert fed > no_needer
    # Bash 2.0 + Tremble 3.0 = 5.0 >= threshold+1 (3): redundancy target met, no feed
    saturated = [*_starter(), C("MOLTEN_FIST"), C("TREMBLE", typ="Skill")]
    assert score_adjustment("UPPERCUT", saturated, TAGS, W) < fed


def test_colossus_prior_carries_owner_dock() -> None:
    """Owner 2026-07-24: "the global prior for Colossus is a bit high" — passed it
    twice in one evening of shadow A/Bs. The committed priors carry the -0.8 dock."""
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).resolve().parent.parent / "data"
                    / "priors_cards.json").read_text(encoding="utf-8"))
    e = d["cards"]["IRONCLAD"]["COLOSSUS"]
    assert e.get("owner_adj") == -0.8
    assert e["s"] < 2.5


def test_upgrade_unlocks_anticipation() -> None:
    up = score_adjustment("APOTHEOSIS", _starter(), TAGS, W, is_upgraded=True)
    base = score_adjustment("APOTHEOSIS", _starter(), TAGS, W, is_upgraded=False)
    assert base == up + W.w_upgrade_unlocks  # same needs, plus anticipation when unupgraded


def test_pseudo_tag_strike_density() -> None:
    # Perfected Strike counts name-contains-Strike (review #16): starter (5 Strikes +
    # Bash) scores the __strike_named bonus higher than a strike-less deck.
    many = score_adjustment("PERFECTED_STRIKE", _starter(strikes=5), TAGS, W)
    none = score_adjustment("PERFECTED_STRIKE",
                            [C("IMPERVIOUS", typ="Skill") for _ in range(9)], TAGS, W)
    assert many > none


def test_anti_synergy_battle_trance() -> None:
    # two draw engines in deck -> Battle Trance's draw-lock dock fires (review item)
    draws = [C("SHRUG_IT_OFF", typ="Skill"), C("ACROBATICS", typ="Skill")]
    with_draw = score_adjustment("BATTLE_TRANCE", _starter() + draws, TAGS, W)
    without = score_adjustment("BATTLE_TRANCE", _starter(), TAGS, W)
    assert with_draw < without


def test_untagged_card_is_neutral() -> None:
    assert score_adjustment("NOT_A_CARD", _starter(), TAGS, W) == 0.0


def test_draw_penalized_without_energy_source() -> None:
    """Owner model rework (2026-07-14): StS2 energy is scarce — pure draw / strike+draw
    is a weak speculative draft. No flat draw bonus; a draw card is PENALIZED when the
    deck has no energy_source, neutral when one exists. Spirebird is not overridden."""
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Pommel:
        id = "POMMEL_STRIKE"
        name = "Pommel Strike"
        type = "Attack"
        cost = "1"
        rarity = "Common"
        is_upgraded = False
        description = "Deal 9 damage. Draw 1 card."

    starter = _starter()
    no_energy = r._card_score(Pommel(), 10, "The Ironclad", act=1, deck=starter)
    with_energy = r._card_score(Pommel(), 10, "The Ironclad", act=1,
                                deck=[*starter, C("BLOODLETTING", typ="Skill", cost="0")])
    assert with_energy > no_energy  # the penalty lifts once an energy source exists
    assert with_energy - no_energy == 2.0  # exactly the configured penalty


def test_xcost_damage_docked_early_not_late() -> None:
    """Owner 2026-07-15 (A/B #2): Whirlwind-class X-cost damage is INEFFICIENT early —
    its payoffs (card efficiency, surplus energy) are late-game. Act-1 dock + no flat
    AoE bonus; a dedicated AoE (Conflagration) is the control and keeps its bonus."""
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self, cid, name, desc, cost, rarity="Uncommon"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = "Attack", cost, rarity
            self.is_upgraded = False

    whirl = Cd("WHIRLWIND", "Whirlwind", "Deal 5 damage to ALL enemies X times.", "X")
    confl = Cd("CONFLAGRATION", "Conflagration", "Deal 2 damage to ALL enemies 4 times.",
               "1", rarity="Rare")
    w = r.config.card_rewards
    deck = _starter()

    early = r._card_score(whirl, 11, "The Ironclad", act=1, deck=deck)
    late = r._card_score(whirl, 11, "The Ironclad", act=2, deck=deck)
    # the Act-1 dock applies early and lifts later (act-tilt aside, the dock dominates)
    assert late - early >= abs(w.penalty_xcost_damage_early) - 1e-6

    # control: Conflagration keeps the flat AoE bonus; Whirlwind never gets it.
    # Compare like-for-like by stripping each card's other terms via a same-cost twin:
    twin = Cd("CONFLAGRATION", "Conflagration", "Deal 8 damage.", "1", rarity="Rare")
    assert (r._card_score(confl, 11, "The Ironclad", act=2, deck=deck)
            - r._card_score(twin, 11, "The Ironclad", act=2, deck=deck)) >= w.bonus_aoe - 1e-6


def test_first_big_hit_switch() -> None:
    """Owner 2026-07-14: until the deck holds any >=12-damage card, offered big hits get
    a strong one-time bonus — a starter deck's first job is acquiring a real hit. The
    switch flips the CJN9M609YW f2 pick (Hemokinesis over Pommel) and self-extinguishes
    once a big hit is in deck."""
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self, cid, name, desc, rarity="Common"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = "Attack", "1", rarity
            self.is_upgraded = False

    pommel = Cd("POMMEL_STRIKE", "Pommel Strike", "Deal 9 damage. Draw 1 card.")
    hemo = Cd("HEMOKINESIS", "Hemokinesis", "Lose 2 HP. Deal 15 damage.", "Uncommon")
    starter = _starter()

    s_pommel = r._card_score(pommel, 11, "The Ironclad", act=1, deck=starter)
    s_hemo = r._card_score(hemo, 11, "The Ironclad", act=1, deck=starter)
    assert s_hemo > s_pommel  # the switch outweighs the community-prior gap

    # once a big hit is in deck the switch extinguishes: same offer, bonus gone
    with_hit = [*starter, C("HEMOKINESIS")]
    s_hemo_after = r._card_score(hemo, 12, "The Ironclad", act=1, deck=with_hit)
    assert s_hemo - s_hemo_after == r.config.card_rewards.w_first_big_hit


def test_block_bonus_is_act1_scoped() -> None:
    # Owner 2026-07-14: block earns its (lesser) bonus in Act 1 only; later acts price
    # block via the capability delta instead of a flat heuristic.
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Shrug:
        id = "SHRUG_IT_OFF"
        name = "Shrug It Off"
        type = "Skill"
        cost = "1"
        rarity = "Common"
        is_upgraded = False
        description = "Gain 8 Block."  # block only: isolates the block bonus

    deck = [*_starter(), C("BLOODLETTING", typ="Skill", cost="0")]  # energy: no draw term
    act1 = r._card_score(Shrug(), 10, "The Ironclad", act=1, deck=deck)
    act2 = r._card_score(Shrug(), 10, "The Ironclad", act=2, deck=deck)
    assert act1 > act2  # includes act-tilt too, but the 1.5 early bonus dominates


def test_fasten_protects_defends_from_removal() -> None:
    # Review #16/#17: a basics-keyed payoff in deck flips basics from removal fodder to
    # enablers — Defend's removal-quality rises when Fasten is present.
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Defend:
        id = "DEFEND_IRONCLAD"
        name = "Defend"
        type = "Skill"
        cost = "1"
        is_upgraded = False
        description = "Gain 5 Block."

    plain = r._card_quality(Defend(), "The Ironclad", deck=_starter())
    protected = r._card_quality(Defend(), "The Ironclad",
                                deck=[*_starter(), C("FASTEN", typ="Power")])
    assert protected > plain
    # Strikes stay unprotected by Fasten (it keys __defends, not __strike_named)
    class Strike(Defend):
        id = "STRIKE_IRONCLAD"
        name = "Strike"
        type = "Attack"
        description = "Deal 6 damage."
    s_plain = r._card_quality(Strike(), "The Ironclad", deck=_starter())
    s_fasten = r._card_quality(Strike(), "The Ironclad",
                               deck=[*_starter(), C("FASTEN", typ="Power")])
    assert s_fasten == s_plain
    # ...but Perfected Strike protects them
    s_ps = r._card_quality(Strike(), "The Ironclad",
                           deck=[*_starter(), C("PERFECTED_STRIKE")])
    assert s_ps > s_plain


def test_router_integration_rupture_pick() -> None:
    # End-to-end through _card_score: Rupture scores materially higher when the deck
    # holds a self-HP-loss enabler (act 2, past the speculative window).
    from sts2bot.policy.standard import StandardRouter
    r = StandardRouter(combat_stats=None, bestiary={})

    class Card:
        id = "RUPTURE"
        name = "Rupture"
        type = "Power"
        cost = "1"
        rarity = "Uncommon"
        is_upgraded = False
        description = "Whenever you lose HP on your turn, gain 1 Strength."

    bare = r._card_score(Card(), 12, "The Ironclad", act=2, deck=_starter())
    fed = r._card_score(Card(), 12, "The Ironclad", act=2,
                        deck=[*_starter(), C("HEMOKINESIS")])
    assert fed > bare


def test_early_damage_bonus_saturates_with_damage_picks() -> None:
    """Owner (A/B #3 Sword Boomerang misdraft): the Act-1 damage-first bias must stop
    paying once real damage picks are in — full below sat_start non-basic damage cards,
    half at it, zero beyond. Same offer, three deck states."""
    from sts2bot.policy.standard import StandardRouter

    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self, cid, name, desc, rarity="Common"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = "Attack", "1", rarity
            self.is_upgraded = False

    offer = Cd("SWORD_BOOMERANG", "Sword Boomerang", "Deal 3 damage to a random enemy 3 times.")
    w = r.config.card_rewards
    fresh = _starter()  # 0 damage picks -> full bonus
    # BULLY + DISMANTLE are real KB damage cards; TAUNT is not (control that non-damage
    # picks don't count toward saturation)
    two = [*_starter(), C("BULLY"), C("TAUNT", typ="Skill"), C("DISMANTLE")]
    three = [*two, C("POMMEL_STRIKE")]

    s_fresh = r._card_score(offer, len(fresh), "The Ironclad", act=1, deck=fresh)
    s_two = r._card_score(offer, len(two), "The Ironclad", act=1, deck=two)
    s_three = r._card_score(offer, len(three), "The Ironclad", act=1, deck=three)
    # isolate the taper: deduct the tag adjustment differences by comparing against a
    # non-damage twin offered to the same decks
    twin = Cd("SWORD_BOOMERANG", "Sword Boomerang", "Gain 3 Block.")
    d_fresh = s_fresh - r._card_score(twin, len(fresh), "The Ironclad", act=1, deck=fresh)
    d_two = s_two - r._card_score(twin, len(two), "The Ironclad", act=1, deck=two)
    d_three = s_three - r._card_score(twin, len(three), "The Ironclad", act=1, deck=three)
    # full -> half -> zero, within the block-bonus offset shared by both comparisons
    assert d_fresh - d_two >= 0.5 * w.early_damage_bonus - 1e-6
    assert d_two - d_three >= 0.5 * w.early_damage_bonus - 1e-6


def test_underdocks_region_swaps_early_bonuses() -> None:
    """Owner 2026-07-17 (region retrospective): the Underdocks rewards defense/scaling —
    the damage-first Act-1 tilt fits only the Overgrowth (arrival flipped OG 72->90%,
    UD 87->77% at the 07-14 rework). Region comes from the region-exclusive boss name."""
    from sts2bot.policy.standard import StandardRouter, _act1_region

    assert _act1_region("Soul Fysh") == "underdocks"
    assert _act1_region("Lagavulin Matriarch") == "underdocks"
    assert _act1_region("The Kin") == "overgrowth"
    assert _act1_region("Vantom") == "overgrowth"
    assert _act1_region(None) is None
    assert _act1_region("Some Future Boss") is None

    r = StandardRouter(combat_stats=None, bestiary={})
    w = r.config.card_rewards

    class Cd:
        def __init__(self, cid, name, desc, typ="Attack"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = typ, "1", "Common"
            self.is_upgraded = False

    atk = Cd("SWORD_BOOMERANG", "Sword Boomerang", "Deal 3 damage to a random enemy 3 times.")
    blk = Cd("IRON_DEFENSE", "Iron Defense", "Gain 8 Block.", typ="Skill")
    deck = _starter()

    d_og = r._card_score(atk, 11, "The Ironclad", act=1, deck=deck)
    d_ud = r._card_score(atk, 11, "The Ironclad", act=1, deck=deck, region="underdocks")
    assert d_og - d_ud >= (w.early_damage_bonus - w.ud_early_damage_bonus) - 1e-6

    b_og = r._card_score(blk, 11, "The Ironclad", act=1, deck=deck)
    b_ud = r._card_score(blk, 11, "The Ironclad", act=1, deck=deck, region="underdocks")
    assert b_ud - b_og >= (w.ud_early_block_bonus - w.early_block_bonus) - 1e-6

    # act 2+: region must be irrelevant (later acts price via capability delta)
    a2_og = r._card_score(atk, 11, "The Ironclad", act=2, deck=deck)
    a2_ud = r._card_score(atk, 11, "The Ironclad", act=2, deck=deck, region="underdocks")
    assert abs(a2_og - a2_ud) < 1e-9


def test_matriarch_boss_rule_premiums_big_instances() -> None:
    """Owner 2026-07-17 — first boss-specific draft rule. Lagavulin Matriarch's
    Strategic cycle stacks -2 Str/-2 Dex (a per-INSTANCE tax): forensics showed a
    deck of 8-damage chips zeroed out over 19 rounds while 15/17-damage hits killed
    her before the second debuff. Big hits and big blocks earn a premium when she is
    the cached act boss; chip instances and X-cost damage do not."""
    from sts2bot.policy.standard import StandardRouter, _boss_draft_rule

    assert _boss_draft_rule("Lagavulin Matriarch") is not None
    assert _boss_draft_rule("Ceremonial Beast") is None  # no rule for him (yet)
    assert _boss_draft_rule(None) is None

    r = StandardRouter(combat_stats=None, bestiary={})
    rule = _boss_draft_rule("Lagavulin Matriarch")

    class Cd:
        def __init__(self, cid, name, desc, typ="Attack", cost="2"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = typ, cost, "Common"
            self.is_upgraded = False

    deck = _starter()
    big = Cd("BLUDGEON", "Bludgeon", "Deal 32 damage.")
    chip = Cd("SWORD_BOOMERANG", "Sword Boomerang",
              "Deal 3 damage to a random enemy 3 times.", cost="1")
    wall = Cd("BLOOD_WALL", "Blood Wall", "Lose 2 HP. Gain 16 Block.", typ="Skill")
    dfd = Cd("IRON_DEFENSE", "Iron Defense", "Gain 5 Block.", typ="Skill", cost="1")

    def delta(card):
        with_rule = r._card_score(card, 11, "The Ironclad", act=1, deck=deck,
                                  boss_rule=rule)
        without = r._card_score(card, 11, "The Ironclad", act=1, deck=deck)
        return with_rule - without

    assert delta(big) >= rule["hit_bonus"] - 1e-6
    assert abs(delta(chip)) < 1e-9      # 3-per-hit chip earns nothing
    assert delta(wall) >= rule["block_bonus"] - 1e-6
    assert abs(delta(dfd)) < 1e-9       # 5-block earns nothing

    # Powers earn the sleep-window setup bonus (owner: 3 free turns amortize them)
    rupture = Cd("RUPTURE", "Rupture",
                 "Whenever you lose HP from a card, gain 1 Strength.", typ="Power")
    assert delta(rupture) >= rule["power_bonus"] - 1e-6


def test_vantom_boss_rule_premiums_multihit_and_big_block() -> None:
    """Vantom forensics (4 clean-build fights): Slippery 9 wasted five rounds of
    single-hit attacks in zero-multi-hit decks, and his 26/28/30 cycle-nuke landed on
    zero block every time. His rule premiums multi-hit chip and big blocks — the
    OPPOSITE attack profile from the Matriarch's big-instance rule."""
    from sts2bot.policy.standard import StandardRouter, _boss_draft_rule

    rule = _boss_draft_rule("Vantom")
    assert rule is not None and "multihit_bonus" in rule
    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self, cid, name, desc, typ="Attack", cost="1"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = typ, cost, "Common"
            self.is_upgraded = False

    deck = _starter()
    boomer = Cd("SWORD_BOOMERANG", "Sword Boomerang",
                "Deal 3 damage to a random enemy 3 times.")
    single = Cd("BLUDGEON", "Bludgeon", "Deal 32 damage.", cost="3")
    wall = Cd("BLOOD_WALL", "Blood Wall", "Lose 2 HP. Gain 16 Block.", typ="Skill")

    def delta(card):
        return (r._card_score(card, 11, "The Ironclad", act=1, deck=deck,
                              boss_rule=rule)
                - r._card_score(card, 11, "The Ironclad", act=1, deck=deck))

    assert delta(boomer) >= rule["multihit_bonus"] - 1e-6  # multi-hit strips Slippery
    assert abs(delta(single)) < 1e-9  # Vantom's rule has no big-hit premium
    assert delta(wall) >= rule["block_bonus"] - 1e-6  # blocks the 26-30 nuke


def test_matriarch_rule_card_bonus_primal_force() -> None:
    """A/B #4 (owner): Primal Force is named Matriarch tech — it converts a chip
    deck's 8s into 16-damage Giant Rocks, mass-crossing her instance threshold."""
    from sts2bot.policy.standard import StandardRouter, _boss_draft_rule

    rule = _boss_draft_rule("Lagavulin Matriarch")
    assert rule["card_bonus"]["PRIMAL_FORCE"] > 0
    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self):
            self.id, self.name = "PRIMAL_FORCE", "Primal Force"
            self.description = "Transform ALL Attacks you play this combat into Giant Rocks."
            self.type, self.cost, self.rarity = "Power", "2", "Uncommon"
            self.is_upgraded = False

    deck = _starter()
    with_rule = r._card_score(Cd(), 11, "The Ironclad", act=1, deck=deck, boss_rule=rule)
    without = r._card_score(Cd(), 11, "The Ironclad", act=1, deck=deck)
    # earns the named-card bonus ON TOP of the generic power bonus
    assert with_rule - without >= (rule["card_bonus"]["PRIMAL_FORCE"]
                                   + rule["power_bonus"]) - 1e-6


def test_waterfall_rule_premiums_big_blocks_and_rest() -> None:
    """Waterfall Giant (owner-confirmed): the death-eruption lands 1-2 turns after the
    kill as a telegraphed DeathBlow — the fight-side lane exists; the draft/route
    levers are big block instances (absorb ~40) and entry HP (rest_loss_bonus)."""
    from sts2bot.policy.standard import _boss_draft_rule

    rule = _boss_draft_rule("Waterfall Giant")
    assert rule is not None
    assert rule["min_block"] == 9 and rule["rest_loss_bonus"] > 0
    assert "min_hit" not in rule  # no big-hit premium: kill-ASAP works at any size


def test_kin_rule_premiums_aoe() -> None:
    """The Kin (2 Followers + 190-HP Priest): AoE is the axis — the one death-deck
    with Conflagration cleared the Followers by r5 and nearly won from 52hp. X-cost
    spend-energy damage (Whirlwind) stays excluded per the owner's standing read."""
    from sts2bot.policy.standard import StandardRouter, _boss_draft_rule

    rule = _boss_draft_rule("The Kin")
    assert rule and rule["aoe_bonus"] > 0
    r = StandardRouter(combat_stats=None, bestiary={})

    class Cd:
        def __init__(self, cid, name, desc, cost="1"):
            self.id, self.name, self.description = cid, name, desc
            self.type, self.cost, self.rarity = "Attack", cost, "Rare"
            self.is_upgraded = False

    deck = _starter()
    confl = Cd("CONFLAGRATION", "Conflagration", "Deal 2 damage to ALL enemies 4 times.")
    whirl = Cd("WHIRLWIND", "Whirlwind", "Deal 5 damage to ALL enemies X times.", "X")

    def delta(card):
        return (r._card_score(card, 11, "The Ironclad", act=1, deck=deck, boss_rule=rule)
                - r._card_score(card, 11, "The Ironclad", act=1, deck=deck))

    assert delta(confl) >= rule["aoe_bonus"] - 1e-6
    assert abs(delta(whirl)) < 1e-9  # X-cost exclusion holds


def test_insatiable_rule_names_barricade() -> None:
    """The Insatiable: A/B #3's human win came from a Barricade block engine banking
    93 — Barricade is named tech vs him, big blocks premiumed, rest gate bumped."""
    from sts2bot.policy.standard import _boss_draft_rule

    rule = _boss_draft_rule("The Insatiable")
    assert rule and rule["min_block"] == 9 and rule["rest_loss_bonus"] > 0
    assert rule["card_bonus"]["BARRICADE"] > 0


def test_attack_density_pseudo_tags_are_computed() -> None:
    """Bug found via audit item 36 (owner's cheap-attacks question): __attacks
    and __cheap_attacks were consumed by seven needs rows but never computed --
    Rage's penalty docked even attack-dense decks."""
    from types import SimpleNamespace as NS
    def c(cid, typ="Attack", cost="1"):
        return NS(id=cid, name=cid.title(), type=typ, cost=cost, is_upgraded=False)
    deck = ([c("STRIKE_IRONCLAD")] * 5 + [c("ANGER", cost="0")] * 2
            + [c("BLUDGEON", cost="3")] + [c("DEFEND_IRONCLAD", typ="Skill")] * 4)
    counts = deck_tag_weights(deck)
    assert counts["__attacks"] == 8.0        # 5 strikes + 2 angers + bludgeon
    assert counts["__cheap_attacks"] == 7.0  # bludgeon (cost 3) excluded
