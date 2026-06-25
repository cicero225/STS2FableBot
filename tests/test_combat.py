"""Combat-planner throttling (ENEMY_PASS Phase 1): _apply_attack must respect Slippery / damage
caps / thorns so the planner stops wasting burst into mechanics it can't see."""

from __future__ import annotations

from sts2bot.client.models import parse_state
from sts2bot.kb.config import load_policy_config
from sts2bot.policy.combat import EnemySim, PlannedCard, SimState, _apply_attack, plan_combat_turn
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


def test_apply_attack_skittish_soaks_follow_up_hits() -> None:
    # Skittish: the first hit lands, then it gains 6 Block which soaks the follow-ups. 5 dmg x4 ->
    # 5 (then +6 block), 0 (5 vs 6, 1 block left), 4 (1 block), 5 = 14 dealt (vs 20 unthrottled).
    out = _apply_attack(_state(_enemy(skittish=6)), 0, _attack(5, hits=4))
    assert out.damage_dealt == 14 and out.enemies[0].hp == 86


def test_apply_attack_skittish_does_not_dampen_a_single_big_hit() -> None:
    # One big hit lands in full -- the +6 Block triggers after it, with no follow-up to soak. So
    # Skittish punishes chip/multi-hit, not single big hits (the mirror of Slippery).
    out = _apply_attack(_state(_enemy(skittish=6)), 0, _attack(30))
    assert out.damage_dealt == 30 and out.enemies[0].hp == 70


def _slippery_fight(statuses: list[dict]) -> dict:
    def card(i, cid, name, cost, desc):
        return {"index": i, "id": cid, "name": name, "type": "Attack", "cost": str(cost),
                "description": desc, "can_play": True, "target_type": "AnyEnemy"}
    return {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                       "energy": 4, "status": [],
                       "hand": [card(0, "BLUDGEON", "Bludgeon", 3, "Deal 32 damage."),
                                card(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.")]},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "v0", "name": "Vantom", "hp": 50, "max_hp": 173,
                                    "block": 0, "status": statuses,
                                    "intents": [{"type": "attack", "label": "10"}]}]}}


def test_planner_sequences_small_hit_first_into_slippery() -> None:
    # end-to-end payoff: vs a Slippery enemy the planner plays the small hit first (wasting the
    # first-HP-loss-to-1), then lands the big one; without Slippery it leads with the big hit.
    w = load_policy_config().combat
    slip = [{"id": "SLIPPERY_POWER", "name": "Slippery",
             "description": "The next time it loses HP, it only loses 1 HP instead."}]
    vs_slip = plan_combat_turn(parse_state(_slippery_fight(slip)), w)
    vs_none = plan_combat_turn(parse_state(_slippery_fight([])), w)
    assert vs_slip.action.payload()["card_index"] == 1  # Strike first, to waste Slippery
    assert vs_none.action.payload()["card_index"] == 0  # Bludgeon first when it lands in full


def test_planner_counts_unplayed_beckon_in_hp_loss() -> None:
    # Soul Fysh's Beckon ("at end of turn, if in hand, lose 6 HP") is unblockable, bypassing the
    # incoming/block tally. The planner spends 1 energy on Strike, leaving Beckon unplayed, so
    # hp_loss must include the 6 -- the hail-mary reads it (owner: bot died under-counting it).
    w = load_policy_config().combat

    def card(i, cid, name, cost, desc, typ, tgt):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tgt}

    state = {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 40, "max_hp": 80, "block": 0,
                        "energy": 1, "status": [],
                        "hand": [card(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                                      "Attack", "AnyEnemy"),
                                 card(1, "BECKON", "Beckon", 1,
                                      "End of your turn, if in your Hand, lose 6 HP.",
                                      "Status", "None")]},
             "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                        "enemies": [{"entity_id": "s0", "name": "Soul Fysh", "hp": 100,
                                     "max_hp": 100, "block": 0, "status": [],
                                     "intents": [{"type": "attack", "label": "5"}]}]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 0  # Strike played, Beckon left in hand
    assert d.scores["hp_loss"] == 11.0  # 5 incoming + 6 unblockable Beckon, not just 5


def test_planner_under_ringing_caps_to_a_single_card() -> None:
    # Ringing (Ceremonial Beast low-HP) caps you to 1 card/turn. The fix verified here is only the
    # cap: the planner must not *start* a 2-card plan it can't finish (the live miss -- blocked,
    # then couldn't hit). WHICH single card is best (attack vs block, factoring the clean turn that
    # follows) is the deferred §5-C nuance, so we don't assert it.
    import re

    w = load_policy_config().combat

    def card(i, cid, name, typ, cost, desc, tt="AnyEnemy"):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tt}

    ring = {"id": "RINGING_POWER", "name": "Ringing",
            "description": "You can only play 1 card this turn."}
    hand = [card(0, "DEFEND_IRONCLAD", "Defend", "Skill", 1, "Gain 5 Block.", tt="None"),
            card(1, "BLUDGEON", "Bludgeon", "Attack", 3, "Deal 32 damage.")]
    beast = {"entity_id": "b0", "name": "Ceremonial Beast", "hp": 50, "max_hp": 200, "block": 0,
             "status": [], "intents": [{"type": "attack", "label": "6"}]}

    def plan(player_status):
        battle = {"round": 1, "turn": "player", "is_play_phase": True, "enemies": [beast]}
        state = {"state_type": "monster", "run": {"act": 1, "floor": 17, "ascension": 0},
                 "player": {"character": "The Ironclad", "hp": 40, "max_hp": 80, "block": 0,
                            "energy": 4, "status": player_status, "hand": hand},
                 "battle": battle}
        rationale = plan_combat_turn(parse_state(state), w).rationale
        return re.search(r"plan \[(.*?)\]", rationale).group(1)

    assert ">" not in plan([ring])  # Ringing: a single card, never a 2-card plan
    assert ">" in plan([])  # uncapped: the planner sequences two cards
