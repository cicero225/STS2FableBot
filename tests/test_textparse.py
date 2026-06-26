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
    fx = parse_card_description("Summon 1. Osty grows stronger.")
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
