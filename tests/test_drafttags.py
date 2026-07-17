"""Card-pass step 2: the deck-context tag machinery (owner-reviewed 2026-07-12).

Uses the real data/card_draft_tags.json so the tests validate the shipped table,
mirroring how policy tests use the real policy config.
"""

from sts2bot.kb.config import load_policy_config
from sts2bot.policy.drafttags import load_draft_tags, score_adjustment

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
