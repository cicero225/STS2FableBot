from sts2bot.policy.textparse import (
    parse_card_description,
    parse_hp_cost,
    parse_intent_damage,
)


def test_simple_damage() -> None:
    fx = parse_card_description("Deal 6 damage.")
    assert fx.damage == 6 and fx.hits == 1 and not fx.aoe
    assert fx.total_damage == 6


def test_multi_hit_damage() -> None:
    fx = parse_card_description("Deal 4 damage 2 times.")
    assert fx.damage == 4 and fx.hits == 2 and fx.total_damage == 8


def test_aoe_damage() -> None:
    fx = parse_card_description("Deal 8 damage to ALL enemies.")
    assert fx.damage == 8 and fx.aoe


def test_block_draw_energy() -> None:
    fx = parse_card_description("Gain 5 Block. Draw 2 cards. Gain 1 Energy.")
    assert fx.block == 5 and fx.draw == 2 and fx.energy_gain == 1


def test_debuffs_and_costs() -> None:
    fx = parse_card_description("Deal 8 damage. Apply 2 Vulnerable. Apply 1 Weak. Lose 3 HP.")
    assert fx.vulnerable == 2 and fx.weak == 1 and fx.self_hp_cost == 3


def test_unrecognized_text_is_inert() -> None:
    # "Summon N" now parses as block-equivalent, so use genuinely unparseable text here.
    fx = parse_card_description("Osty grows stronger. Transform a card in your Hand.")
    assert not fx.has_any_effect and fx.total_damage == 0


def test_intent_labels() -> None:
    assert parse_intent_damage("11") == 11
    assert parse_intent_damage("3x4") == 12
    assert parse_intent_damage("2 × 8") == 16
    assert parse_intent_damage("Buff") == 0
    assert parse_intent_damage(None) == 0


def test_hp_cost_phrases() -> None:
    assert parse_hp_cost("Trudge on. Take 8 damage.") == 8
    assert parse_hp_cost("Lose 6 HP. Gain 2 Energy.") == 6
    assert parse_hp_cost("Obtain 100 gold.") == 0


def test_max_hp_loss_is_a_heavy_cost() -> None:
    """The 'max HP vampire' event killed three runs while parsing as free."""
    assert parse_hp_cost("Keep digging. Lose 1 Max HP.") == 8
    fx = parse_card_description("Lose 2 Max HP. Obtain a relic.")
    assert fx.max_hp_cost == 2 and fx.self_hp_cost == 0


def test_conditional_language_detected() -> None:
    evil_eye = parse_card_description(
        "Gain 4 Block. If a card was Exhausted this turn, gain 8 Block instead."
    )
    assert evil_eye.block == 4 and evil_eye.conditional
    dark_embrace = parse_card_description("Whenever a card is Exhausted, draw 1 card.")
    assert dark_embrace.conditional
    cascade = parse_card_description("Play the top X cards of your draw pile.")
    assert cascade.conditional and not cascade.has_any_effect
    strike = parse_card_description("Deal 6 damage.")
    assert not strike.conditional


def test_iconized_energy_gain() -> None:
    # The game renders gained energy as ICON tokens, not "N Energy" text. The text regex missed it
    # so Luminesce / Bloodletting / Offering parsed to 0 energy and got left unplayed (owner-caught
    # 2026-06-26). Count the per-character energy icons after "Gain"; don't count star_icon.
    icon = "[ironclad_energy_icon.png]"
    assert parse_card_description(f"Retain. Gain {icon}{icon}. Exhaust.").energy_gain == 2
    assert parse_card_description(f"Lose 3 HP. Gain {icon}{icon}.").energy_gain == 2
    off = parse_card_description(f"Lose 6 HP. Gain {icon}{icon}. Draw 3 cards. Exhaust.")
    assert off.energy_gain == 2 and off.draw == 3 and off.self_hp_cost == 6
    assert parse_card_description("Gain [silent_energy_icon.png].").energy_gain == 1  # other chars
    assert parse_card_description("Gain [star_icon.png].").energy_gain == 0  # star != energy
    assert parse_card_description("Gain 2 Energy.").energy_gain == 2  # text form still works


def test_damage_times_with_target_clause() -> None:
    # Conflagration = "Deal 2 damage to ALL enemies 4 times." parsed as 2 dmg x1 — a 4x
    # under-value that cascaded into Bloodletting looking pointless (owner-caught live
    # 2026-07-09: BL+ skipped because its payoff card looked worthless).
    fx = parse_card_description("Deal 2 damage to ALL enemies 4 times.")
    assert (fx.damage, fx.hits, fx.aoe) == (2, 4, True)
    fx = parse_card_description("Deal 5 damage to a random enemy 3 times.")
    assert (fx.damage, fx.hits) == (5, 3)
    fx = parse_card_description("Deal 6 damage 3 times.")  # adjacent form still works
    assert (fx.damage, fx.hits) == (6, 3)


def test_damage_paren_resolved_hits() -> None:
    # Live text pre-resolves dynamic hit counts: "Deal 4 damage. Hits an additional time for
    # each time you lost HP this combat. (Hits 6 times)" — trust the game's resolved number.
    fx = parse_card_description(
        "Deal 4 damage. Hits an additional time for each time you lost HP this combat. "
        "(Hits 6 times)")
    assert (fx.damage, fx.hits) == (4, 6)


def test_card_pass_tranche_b_parses() -> None:
    # Card-pass step 1, tranche B (2026-07-09): each case is a REAL card text the parser
    # previously misread, verified via the 13-agent empirical audit (data/card_notes.json).
    p = parse_card_description
    fx = p("Osty deals 6 damage. Deals additional damage equal to Osty's current HP.")
    assert fx.damage == 6  # third-person "deals" (companion damage) counted
    fx = p("Deal 6 damage to ALL enemies twice.")
    assert (fx.damage, fx.hits, fx.aoe) == (6, 2, True)  # word-numeral hits
    fx = p("Apply 3 Weak and Vulnerable to ALL enemies. Exhaust.")
    assert (fx.weak, fx.vulnerable) == (3, 3)  # compound debuff
    fx = p("Put 3 cards from your Discard Pile into your Hand. Exhaust.")
    assert fx.draw == 3  # retrieval reads as draw
    fx = p("Gain 4 Plating.")
    # RETIRED CONTRACT (fuzz find #1, 2026-08-10): Plating used to parse as
    # immediate block; it's end-of-turn decaying block, now its own channel
    assert fx.block == 0 and fx.plating == 4
    fx = p("Gain 6 Block. Add 1 Shiv into your Hand.")
    assert (fx.block, fx.damage, fx.hits) == (6, 4, 1)  # Shiv approximation
    fx = p("Deal 8 damage. Damage ALL other enemies equal to the damage dealt.")
    assert fx.aoe  # splash counts as AoE
    fx = p("Gain 12 Block. Whenever you are attacked this turn, deal 4 damage back.")
    assert fx.damage == 0 and fx.block == 12  # retaliation is not on-play damage
    fx = p("Draw 2 cards. When this card is Exhausted, gain "
           "[ironclad_energy_icon.png][ironclad_energy_icon.png].")
    assert fx.energy_gain == 0 and fx.draw == 2  # trigger-sentence energy not immediate
    fx = p("Gain 15 Block. Next turn, draw 2 cards and gain "
           "[colorless_energy_icon.png][colorless_energy_icon.png]. Exhaust.")
    assert fx.draw == 0 and fx.block == 15  # next-turn effects deferred


def test_attack_generator_credited() -> None:
    # Owner live-caught (2026-07-09): 0-cost Infernal Blade+ ("Add a random Attack into your
    # Hand. It's free to play this turn. Exhaust.") parsed to nothing and sat unplayed at
    # pure friction cost. Credit an average random attack; the replan sees the real card.
    fx = parse_card_description(
        "Add a random Attack into your Hand. It's free to play this turn. Exhaust.")
    assert fx.damage == 8 and fx.hits == 1 and fx.has_any_effect


def test_delta_audit_fixes() -> None:
    # Panache (harness-confirmed FALSE LETHAL): "Every time you play 5 cards in a single turn,
    # deal 10 damage to ALL enemies." must parse to NO immediate damage.
    p = parse_card_description
    fx = p("Every time you play 5 cards in a single turn, deal 10 damage to ALL enemies.")
    assert fx.damage == 0
    # Fisticuffs: "Gain Block equal to damage dealt" -> block ~= damage
    fx = p("Deal 7 damage. Gain Block equal to damage dealt.")
    assert (fx.damage, fx.block) == (7, 7)


def test_self_death_rider_flagged() -> None:
    # The Gambit: the block still parses, but the rider must be flagged so planner/draft
    # gate it (the bot can never certify combat-long perfect blocking).
    p = parse_card_description
    fx = p("Gain 50 Block. If you take unblocked attack damage this combat, die.")
    assert fx.self_death_rider and fx.block == 50
    # no false positives: enemy-death and protective wording stay unflagged
    assert not p("Deal 8 damage. If this kills the enemy, gain 10 gold.").self_death_rider
    assert not p("Gain 12 Block.").self_death_rider


def test_summon_as_block_equivalent() -> None:
    # No companion state in the API: Summon N ~ N block-equivalent protection.
    p = parse_card_description
    fx = p("Summon 5.")  # Bodyguard
    assert fx.block == 5 and fx.has_any_effect
    fx = p("Summon 4. Gain 7 Block.")  # Pull Aggro: summon ADDS to real block
    assert fx.block == 11
    # Invoke: "Next turn, Summon 2..." is deferred -> no immediate credit
    fx = p("Next turn, Summon 2 and gain [necrobinder_energy_icon.png].")
    assert fx.block == 0


def test_replay_enchant_scales_effects() -> None:
    # Live shape (2026-07-12): Spiral-enchanted Strike reads "Deal 6 damage. Replay 1."
    # Replay N = played N ADDITIONAL times: all effects scale by N+1.
    p = parse_card_description
    fx = p("Deal 6 damage. Replay 1.")
    assert fx.total_damage == 12
    fx = p("Deal 2 damage 4 times. Replay 1.")  # multi-hit: hits double, per-hit stays
    assert (fx.damage, fx.hits) == (2, 8)
    fx = p("Gain 5 Block. Replay 2.")
    assert fx.block == 15
    fx = p("Lose 2 HP. Deal 15 damage. Replay 1.")  # costs repeat too
    assert (fx.self_hp_cost, fx.total_damage) == (4, 30)
    assert p("Deal 6 damage.").total_damage == 6  # no enchant, no scaling


def test_discovery_generator_credited() -> None:
    # Discovery: "Choose 1 of 3 random cards to add into your Hand." parsed to nothing ->
    # sat unplayed at friction cost (delta audit; same class as Infernal Blade).
    fx = parse_card_description(
        "Choose 1 of 3 random cards to add into your Hand. It's free to play this turn. "
        "Exhaust.")
    assert fx.damage == 8 and fx.has_any_effect


def test_plating_is_not_immediate_block() -> None:
    """Fuzz-harness find #1 (2026-08-10, Stone Armor+ n=4 avg -6.0 blk, 0%
    within +-1): 'Gain N Plating' grants its block at END of turn, decaying --
    parsing it as immediate block phantom-fed Body Slam-class and Fortifier
    effects. Now a separate channel; the sims route it to end_turn_block."""
    fx = parse_card_description("Ethereal. Gain 6 Plating.")
    assert fx.block == 0
    assert fx.plating == 6
    fx2 = parse_card_description(
        "Gain 4 Plating. Draw 2 cards the first time this is played. Bound")
    assert fx2.block == 0 and fx2.plating == 4 and fx2.draw == 2
    # real block untouched
    fx3 = parse_card_description("Gain 5 Block.")
    assert fx3.block == 5 and fx3.plating == 0
