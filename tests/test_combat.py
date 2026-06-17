"""Combat-planner throttling (ENEMY_PASS Phase 1): _apply_attack must respect Slippery / damage
caps / thorns so the planner stops wasting burst into mechanics it can't see."""

from __future__ import annotations

from sts2bot.policy.combat import EnemySim, PlannedCard, SimState, _apply_attack
from sts2bot.policy.textparse import CardEffects


def _enemy(**kw) -> EnemySim:
    return EnemySim(entity_id="e", hp=100, max_hp=100, block=0, vulnerable=0, incoming=0, **kw)


def _state(enemy: EnemySim) -> SimState:
    return SimState(energy=3, enemies=(enemy,), my_block=0, my_strength=0)


def _attack(damage: int, hits: int = 1) -> PlannedCard:
    return PlannedCard(index=0, name="Atk", cost=1, fx=CardEffects(damage=damage, hits=hits),
                       targets_enemy=True, is_attack=True)


def test_apply_attack_slippery_guts_a_single_big_hit() -> None:
    out = _apply_attack(_state(_enemy(slippery=True)), 0, _attack(30))
    assert out.enemies[0].hp == 99 and out.damage_dealt == 1  # the one big hit -> 1


def test_apply_attack_slippery_only_dampens_the_first_hit() -> None:
    out = _apply_attack(_state(_enemy(slippery=True)), 0, _attack(5, hits=4))
    assert out.damage_dealt == 16 and out.enemies[0].hp == 84  # 1 + 5 + 5 + 5


def test_apply_attack_caps_damage_per_turn() -> None:
    out = _apply_attack(_state(_enemy(dmg_cap_per_turn=15)), 0, _attack(50))
    assert out.damage_dealt == 15 and out.enemies[0].hp == 85  # burst past the cap is wasted


def test_apply_attack_cap_threads_across_cards() -> None:
    s = _apply_attack(_state(_enemy(dmg_cap_per_turn=15)), 0, _attack(10))
    assert s.damage_dealt == 10 and s.enemies[0].hp_lost_this_turn == 10
    s2 = _apply_attack(s, 0, _attack(10))  # only 5 more allowed this turn (cap 15)
    assert s2.damage_dealt == 15 and s2.enemies[0].hp == 85


def test_apply_attack_thorns_costs_self_damage_per_hit() -> None:
    out = _apply_attack(_state(_enemy(thorns=5)), 0, _attack(10, hits=3))
    assert out.self_damage == 15  # 5 thorns x 3 hits landed


def test_apply_attack_unthrottled_enemy_is_unchanged() -> None:
    out = _apply_attack(_state(_enemy()), 0, _attack(30))
    assert out.enemies[0].hp == 70 and out.damage_dealt == 30 and out.self_damage == 0
