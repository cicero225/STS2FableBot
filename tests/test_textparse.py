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
