"""Combat-planner throttling (ENEMY_PASS Phase 1): _apply_attack must respect Slippery / damage
caps / thorns so the planner stops wasting burst into mechanics it can't see."""

from __future__ import annotations

from sts2bot.client.models import parse_state
from sts2bot.kb.config import load_policy_config
from sts2bot.policy.combat import (
    EnemySim,
    PlannedCard,
    SimState,
    _apply_attack,
    _apply_card,
    _enemy_attacking,
    plan_combat_turn,
)
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


def test_planner_treats_unplayed_toxic_as_blockable() -> None:
    # Toxic ("if in hand at end of turn, take 5 dmg") is BLOCKABLE -- unlike Beckon's unblockable
    # "lose N HP", leftover block soaks it (owner correction). Planner plays Defend (8 block) vs 3
    # incoming + 5 Toxic; block covers both, so hp_loss is 0 (mismodeled as unblockable it'd be 5).
    w = load_policy_config().combat

    def card(i, cid, name, cost, desc, typ, tgt, can_play=True):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": can_play, "target_type": tgt}

    state = {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 40, "max_hp": 80, "block": 0,
                        "energy": 1, "status": [],
                        "hand": [card(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 8 Block.",
                                      "Skill", "None"),
                                 card(1, "TOXIC", "Toxic", 0,
                                      "If this is in your hand at end of turn, take 5 damage.",
                                      "Status", "None", can_play=False)]},
             "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                        "enemies": [{"entity_id": "s0", "name": "Spawn", "hp": 100,
                                     "max_hp": 100, "block": 0, "status": [],
                                     "intents": [{"type": "attack", "label": "3"}]}]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 0  # Defend played, Toxic left in hand
    assert d.scores["hp_loss"] == 0.0  # 3 incoming + 5 Toxic, both blockable, soaked by 8 block


def _power_state(enemy_hp: int, hp: int, power_desc: str) -> dict:
    def card(i, cid, name, cost, desc, typ, tgt):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tgt}
    return {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80, "block": 0,
                       "energy": 1, "status": [],
                       "hand": [card(0, "POW", "Power", 1, power_desc, "Power", "None"),
                                card(1, "BIGSTRIKE", "Heavy Strike", 1, "Deal 12 damage.",
                                     "Attack", "AnyEnemy")]},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Slug", "hp": enemy_hp,
                                    "max_hp": enemy_hp, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "5"}]}]}}


def test_planner_front_loads_a_power_when_the_fight_is_long() -> None:
    # Horizon: vs a high-HP enemy (many turns left) a per-turn Power is worth its buff x remaining
    # turns, so it goes down ASAP -- here over a same-cost Heavy Strike (owner: Juggernaut should
    # not sit early). A near-dead enemy (1 turn left) flips it: just kill, don't bank a buff.
    w = load_policy_config().combat
    metallicize = "At the start of your turn, gain 3 Block."
    long_fight = plan_combat_turn(parse_state(_power_state(100, 80, metallicize)), w)
    short_fight = plan_combat_turn(parse_state(_power_state(10, 80, metallicize)), w)
    assert long_fight.action.payload()["card_index"] == 0   # Power front-loaded in the long fight
    assert short_fight.action.payload()["card_index"] == 1  # near-lethal: Heavy Strike, not Power


def test_planner_does_not_front_load_a_self_damage_power_at_low_hp() -> None:
    # Self-damage powers (Inferno) front-load only while healthy; at low HP their upkeep drain
    # makes eager play dangerous, so the horizon bonus drops to flat and a real Strike wins.
    w = load_policy_config().combat
    inferno = "At the start of your turn, lose 2 HP. Gain 4 Block."
    healthy = plan_combat_turn(parse_state(_power_state(100, 80, inferno)), w)  # 100% HP
    hurt = plan_combat_turn(parse_state(_power_state(100, 16, inferno)), w)     # 20% HP, below cut
    assert healthy.action.payload()["card_index"] == 0  # front-loaded while healthy
    assert hurt.action.payload()["card_index"] == 1     # not front-loaded when hurt -> Strike wins


def test_planner_plays_zero_cost_energy_card_to_enable_more() -> None:
    # Energy-gain IS modeled: Production (0c, +2 energy) unlocks Defend x2 + Strike x3 on 3 base
    # energy (5 total), so the planner plays it FIRST. (Owner asked "did we wire energy cards?" --
    # yes: parser sets energy_gain, _apply_card adds it to the DFS budget.)
    w = load_policy_config().combat

    def card(i, cid, name, cost, desc, typ, tgt):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tgt}

    hand = [card(0, "PRODUCTION", "Production", 0, "Gain 2 Energy. Exhaust.", "Skill", "None"),
            card(1, "DEF1", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            card(2, "DEF2", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            card(3, "STR1", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            card(4, "STR2", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            card(5, "STR3", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    state = {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 40, "max_hp": 80, "block": 0,
                        "energy": 3, "status": [], "hand": hand},
             "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                        "enemies": [{"entity_id": "e0", "name": "Slug", "hp": 100, "max_hp": 100,
                                     "block": 0, "status": [],
                                     "intents": [{"type": "attack", "label": "10"}]}]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 0  # Production first, to unlock the fuller turn


def test_planner_counts_deathblow_intent_as_incoming() -> None:
    # Waterfall Giant's Steam-Eruption explosion telegraphs as a "DeathBlow" intent (boss goes
    # invincible at an HP sentinel), not "attack". The attack-only filter missed it, so the bot saw
    # 0 incoming and didn't block / hail-mary a lethal (owner). Now it counts DeathBlow.
    w = load_policy_config().combat

    def card(i, cid, name, cost, desc, typ, tgt):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tgt}

    state = {"state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 5, "max_hp": 80, "block": 0,
                        "energy": 1, "status": [],
                        "hand": [card(0, "DEFEND", "Defend", 1, "Gain 8 Block.", "Skill", "None"),
                                 card(1, "STRIKE", "Strike", 1, "Deal 6 damage.", "Attack",
                                      "AnyEnemy")]},
             "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                        "enemies": [{"entity_id": "wg", "name": "Waterfall Giant", "hp": 999999999,
                                     "max_hp": 999999999, "block": 0, "status": [],
                                     "intents": [{"type": "DeathBlow", "label": "10",
                                                  "title": "Death Blow"}]}]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 0  # Defend, don't chip the invincible boss
    assert d.scores["hp_loss"] == 2.0  # 10 DeathBlow - 8 block (was 0: incoming missed entirely)


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


# ---------------------------------------------------------------- combat-modeling pass


def test_apply_attack_invincible_enemy_takes_no_damage() -> None:
    # Waterfall Giant mid-eruption is reported at a sentinel HP and is invincible: damage is wasted
    # (it dies on its own), only mitigation matters. The planner must not chip it.
    out = _apply_attack(_state(_enemy(invincible=True)), 0, _attack(30))
    assert out.damage_dealt == 0 and out.enemies[0].hp == 100  # unchanged; the attack did nothing


def _vuln_card(vuln: int = 0, weak: int = 0, order: tuple[str, ...] = ()) -> PlannedCard:
    return PlannedCard(index=0, name="Dbf", cost=1,
                       fx=CardEffects(vulnerable=vuln, weak=weak), targets_enemy=True,
                       debuff_order=order)


def test_artifact_eats_a_lone_vulnerable_so_it_lands_nothing() -> None:
    # Dominate (1 Vulnerable) into Artifact 2: Artifact negates it -> zero effect, decrement to 1.
    s = SimState(energy=3, enemies=(_enemy(artifact=2),), my_block=0, my_strength=0)
    out = _apply_card(s, _vuln_card(vuln=1, order=("vulnerable",)), 0)
    assert out.vuln_applied == 0 and out.enemies[0].vulnerable == 0
    assert out.enemies[0].artifact == 1  # one strip consumed


def test_artifact_strips_one_per_unique_status_in_card_text_order() -> None:
    # Uppercut (Weak THEN Vulnerable) into Artifact 1: the Weak is eaten (Artifact -> 0), then the
    # Vulnerable lands. Magnitude-blind: it's one strip per status, not per stack (owner).
    s = SimState(energy=3, enemies=(_enemy(artifact=1),), my_block=0, my_strength=0)
    out = _apply_card(s, _vuln_card(vuln=1, weak=1, order=("weak", "vulnerable")), 0)
    assert out.enemies[0].artifact == 0
    assert out.weak_applied == 0  # Weak was the first status, eaten by Artifact
    assert out.vuln_applied == 1 and out.enemies[0].vulnerable == 1  # Vulnerable then lands


def test_pen_nib_doubles_the_tenth_attack_only() -> None:
    # Counter at 9 -> the next attack is the 10th and doubles; the one after returns to normal.
    s = SimState(energy=9, enemies=(_enemy(),), my_block=0, my_strength=0, pen_nib_counter=9)
    s = _apply_card(s, _attack(10), 0)
    assert s.damage_dealt == 20 and s.pen_nib_counter == 10  # doubled
    s = _apply_card(s, _attack(10), 0)
    assert s.damage_dealt == 30  # +10 only (counter 10 -> not a multiple-of-10 boundary)


def test_pen_nib_absent_relic_never_doubles() -> None:
    s = SimState(energy=9, enemies=(_enemy(),), my_block=0, my_strength=0)  # counter None
    s = _apply_card(s, _attack(10), 0)
    assert s.damage_dealt == 10 and s.pen_nib_counter is None


def test_enemy_attacking_keys_off_the_crossing_not_the_level() -> None:
    # The Plow stun is one-time: it fires when our damage CROSSES the threshold, not whenever HP
    # happens to sit below it. An enemy already below the line (stun spent, now awake) attacks.
    def es(hp, stunned=False):
        return EnemySim(entity_id="e", hp=hp, max_hp=300, block=0, vulnerable=0, incoming=40,
                        stun_threshold=150, stunned_this_turn=stunned)
    assert _enemy_attacking(es(160)) is True  # above threshold: attacks
    assert _enemy_attacking(es(140)) is True  # below but NOT crossed this turn (awake again)
    assert _enemy_attacking(es(140, stunned=True)) is False  # we crossed it -> stunned, skips turn
    assert _enemy_attacking(es(0)) is False  # dead


def test_apply_attack_sets_stun_flag_only_on_the_crossing() -> None:
    def es(hp):
        return SimState(energy=3, my_block=0, my_strength=0,
                        enemies=(EnemySim(entity_id="e", hp=hp, max_hp=300, block=0, vulnerable=0,
                                          incoming=40, stun_threshold=150),))
    crossed = _apply_attack(es(158), 0, _attack(12))  # 158 -> 146, crosses 150
    assert crossed.enemies[0].stunned_this_turn is True
    not_crossed = _apply_attack(es(170), 0, _attack(12))  # 170 -> 158, still above 150
    assert not_crossed.enemies[0].stunned_this_turn is False
    already_below = _apply_attack(es(140), 0, _attack(12))  # started below: no fresh crossing
    assert already_below.enemies[0].stunned_this_turn is False


def test_planner_attacks_to_stun_threshold_to_survive() -> None:
    # Ceremonial Beast: 150-HP stun threshold, telegraphing a 40 hit. At 5 HP with no block cards,
    # attacking it from 158 -> below 150 stuns it (skips the hit). The planner takes the kill-
    # the-turn line over a useless tiny block.
    w = load_policy_config().combat

    def card(i, cid, name, cost, desc, typ, tgt):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
                "description": desc, "can_play": True, "target_type": tgt}

    beast = {"entity_id": "b0", "name": "Ceremonial Beast", "hp": 158, "max_hp": 300, "block": 0,
             "status": [{"id": "STUN_THRESHOLD", "name": "Stun",
                         "description": "Stunned when its HP reaches 150 or below."}],
             "intents": [{"type": "attack", "label": "40"}]}
    state = {"state_type": "monster", "run": {"act": 1, "floor": 17, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 5, "max_hp": 80, "block": 0,
                        "energy": 1, "status": [],
                        "hand": [card(0, "DEF", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
                                 card(1, "STRIKE", "Strike", 1, "Deal 12 damage.", "Attack",
                                      "AnyEnemy")]},
             "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": [beast]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 1  # Strike to cross the stun threshold, not Defend
    assert d.scores["hp_loss"] == 0.0  # stunned -> the 40 hit doesn't land


def test_healing_credited_when_hurt_capped_at_damage_taken() -> None:
    # Not Yet (Heal 10) capped at the HP actually missing; played when hurt it should be preferred
    # over an idle skip. heal_room caps the credit (no overheal).
    heal = PlannedCard(index=0, name="Not Yet", cost=2,
                       fx=CardEffects(heal=10), targets_enemy=False)
    s = SimState(energy=2, enemies=(_enemy(),), my_block=0, my_strength=0, heal_room=4)
    out = _apply_card(s, heal, None)
    assert out.healing == 4  # capped at the missing 4 HP, no overheal
    s2 = SimState(energy=2, enemies=(_enemy(),), my_block=0, my_strength=0, heal_room=25)
    assert _apply_card(s2, heal, None).healing == 10  # full heal when there's room


def test_player_weak_cuts_my_attack_damage() -> None:
    # I'm Weak (Kin Orb of Weakness): my Attacks deal 25% less, so a 10 hit lands 7 (int floor).
    base = _apply_attack(_state(_enemy()), 0, _attack(10))
    weak = _apply_attack(SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0,
                                  my_weak=True), 0, _attack(10))
    assert base.damage_dealt == 10 and weak.damage_dealt == 7


def test_player_frail_cuts_block_i_gain() -> None:
    # I'm Frail (Kin Orb of Frailty): Block gained from cards is 25% less, so a 10-Block card -> 7.
    block_card = PlannedCard(index=0, name="Defend", cost=1, fx=CardEffects(block=10),
                             targets_enemy=False)
    healthy = _apply_card(SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0),
                          block_card, None)
    frail = _apply_card(SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0,
                                 my_frail=True), block_card, None)
    assert healthy.my_block == 10 and frail.my_block == 7
