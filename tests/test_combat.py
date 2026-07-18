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
    _score,
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
    out = _apply_attack(_state(_enemy(slippery_stacks=1)), 0, _attack(30))
    assert out.enemies[0].hp == 99 and out.damage_dealt == 1  # the one big hit -> 1


def test_apply_attack_slippery_one_stack_dampens_only_the_first_hit() -> None:
    out = _apply_attack(_state(_enemy(slippery_stacks=1)), 0, _attack(5, hits=4))
    assert out.damage_dealt == 16 and out.enemies[0].hp == 84  # 1 + 5 + 5 + 5 (one charge spent)


def test_apply_attack_slippery_stacks_each_eat_one_hit() -> None:
    # Vantom enters with 9 Slippery: a multi-hit card spends one charge per hit (each -> 1), so a
    # 5x4 card deals just 4 here (4 charges spent), leaving 5 charges. Big single hits are wasted.
    out = _apply_attack(_state(_enemy(slippery_stacks=9)), 0, _attack(5, hits=4))
    assert out.damage_dealt == 4 and out.enemies[0].slippery_stacks == 5  # 1+1+1+1, 9-4 left


def test_apply_attack_slippery_charges_thread_across_cards() -> None:
    # Charges persist across cards in a turn: two 1-hit attacks into Vantom each deal 1 and each
    # spend a charge (so a sequence of cheap hits is how you strip it, not one big hit).
    s = _apply_attack(_state(_enemy(slippery_stacks=9)), 0, _attack(20))
    assert s.damage_dealt == 1 and s.enemies[0].slippery_stacks == 8
    s2 = _apply_attack(s, 0, _attack(20))
    assert s2.damage_dealt == 2 and s2.enemies[0].slippery_stacks == 7


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


def _beckon_state(energy: int, hand: list, enemy_hp: int = 100, hp: int = 40,
                  enemy_status: list | None = None, incoming: str = "5") -> dict:
    return {"state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80, "block": 0,
                       "energy": energy, "status": [], "hand": hand},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "s0", "name": "Soul Fysh", "hp": enemy_hp,
                                    "max_hp": 100, "block": 0, "status": enemy_status or [],
                                    "intents": [{"type": "attack", "label": incoming}]}]}}


def _bcard(i, cid, name, cost, desc, typ, tgt, can_play=True):
    return {"index": i, "id": cid, "name": name, "type": typ, "cost": str(cost),
            "description": desc, "can_play": can_play, "target_type": tgt}


_BECKON_DESC = "End of your turn, if in your Hand, lose 6 HP."
_INTANGIBLE = [{"id": "INTANGIBLE_POWER", "name": "Intangible", "amount": 1,
                "description": "Reduce all damage taken and HP loss to 1. Lasts for 1 turn."}]


def test_planner_values_clearing_a_beckon() -> None:
    # The stranded-Beckon penalty lives in the scored objective (not just the post-hoc hp_loss
    # diagnostic), so the search PREFERS spending 1 energy to clear 6 unblockable HP over a
    # 6-damage Strike into a 100-HP enemy at half health (bsmwhj26u Soul Fysh losses).
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(1, hand)), w)
    assert d.action.payload()["card_index"] == 1  # clear the Beckon, don't poke
    assert d.scores["hp_loss"] == 5.0  # only the blockable-incoming 5 remains


def test_planner_counts_stranded_beckon_in_hp_loss() -> None:
    # With 1 energy and TWO Beckons, one must strand: hp_loss still reports the honest
    # 5 incoming + 6 unblockable (the hail-mary reads it; owner: bot died under-counting it).
    w = load_policy_config().combat
    hand = [_bcard(0, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None"),
            _bcard(1, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(1, hand)), w)
    assert d.action.payload()["card_index"] in (0, 1)  # clears one of them
    assert d.scores["hp_loss"] == 11.0  # 5 incoming + 6 for the stranded one


def test_planner_clears_beckons_instead_of_poking_intangible() -> None:
    # The measured bsmwhj26u failure: Fysh Intangible (all damage -> 1), two Beckons in hand,
    # 3 energy. Attacks are ~worthless (per-turn cap 1) and each Beckon cleared saves 6
    # unblockable HP -- the plan must start with a Beckon, not an attack.
    w = load_policy_config().combat
    hand = [_bcard(0, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None"),
            _bcard(1, "POMMEL_STRIKE", "Pommel Strike", 1, "Deal 9 damage. Draw 1 card.",
                   "Attack", "AnyEnemy"),
            _bcard(2, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None"),
            _bcard(3, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(
        parse_state(_beckon_state(3, hand, enemy_hp=172, hp=35,
                                  enemy_status=_INTANGIBLE, incoming="13")), w)
    assert d.action.payload()["card_index"] in (0, 2)  # a Beckon leads the plan
    plan = d.rationale.split("[")[1].split("]")[0]
    assert plan.count("Beckon") == 2  # and BOTH get cleared in the chosen sequence


def test_planner_skips_beckon_clearing_on_lethal() -> None:
    # Fight ends before end of turn on a kill: the Beckon never fires, so don't waste the
    # energy -- take the lethal.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(1, hand, enemy_hp=5)), w)
    assert d.action.payload()["card_index"] == 0  # Strike kills; Beckon penalty is moot
    assert "LETHAL" in d.rationale


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


def test_pen_nib_preview_semantics_at_counter_nine() -> None:
    # LIVE-VALIDATED 2026-07-09 (owner's June gotcha): at counter 9 the game PRE-DOUBLES every
    # attack's rules text, so parsed damage already carries the double. The first attack keeps
    # its parsed value untouched; later attacks in the same plan halve back to base.
    s = SimState(energy=9, enemies=(_enemy(),), my_block=0, my_strength=0, pen_nib_counter=9,
                 pen_turn_started_at_nine=True)
    s = _apply_card(s, _attack(20), 0)  # "20" = the pre-doubled text of a base-10 attack
    assert s.damage_dealt == 20 and s.pen_nib_counter == 10  # taken at face value (real double)
    s = _apply_card(s, _attack(20), 0)  # same doubled TEXT, but the double is spent
    assert s.damage_dealt == 30  # +10: the preview halves back to base


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


def test_player_weak_is_prebaked_not_reapplied() -> None:
    """CORRECTED 2026-07-14 (trace-verified): the player's own Weak is PRE-BAKED into
    the card text — a Strike under Weak already READS "Deal 4 damage" (6 x 0.75). The
    sim must NOT re-apply WEAK_MULT (that double-counted). The text a Weak player sees
    for a base-10 attack is 7, and 7 is what lands."""
    weak = _apply_attack(SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0,
                                  my_weak=True), 0, _attack(7))
    assert weak.damage_dealt == 7  # face value, NOT 7*0.75=5


def _crab(hp: int, eid: str = "c", **kw) -> EnemySim:
    return EnemySim(entity_id=eid, hp=hp, max_hp=200, block=0, vulnerable=0, incoming=10,
                    crab_rage=True, **kw)


def test_crab_rage_single_kill_enrages_the_survivor() -> None:
    # Kaiser Crab: killing one claw (single-target) buffs the survivor +99 Block + 6 Str (~+6 dmg),
    # so the planner sees the premature kill leaves an unkillable wall.
    s = SimState(energy=3, my_block=0, my_strength=0,
                 enemies=(_crab(8, "ROCKET"), _crab(200, "CRUSHER")))
    out = _apply_card(s, _attack(20), 0)  # 20 dmg kills the 8-HP Rocket
    rocket, crusher = out.enemies
    assert rocket.hp == 0
    assert crusher.block == 99 and crusher.incoming == 16  # enraged: +99 Block, +6 to its hit


def test_crab_rage_aoe_double_kill_enrages_no_one() -> None:
    # An AoE that kills BOTH claws in one card triggers no enrage (they die together) — the cheese.
    s = SimState(energy=3, my_block=0, my_strength=0,
                 enemies=(_crab(8, "ROCKET"), _crab(8, "CRUSHER")))
    aoe = PlannedCard(index=0, name="Cleave", cost=1,
                      fx=CardEffects(damage=20, aoe=True), targets_enemy=False)
    out = _apply_card(s, aoe, None)
    assert all(e.hp == 0 for e in out.enemies) and all(e.block == 0 for e in out.enemies)


def test_score_penalizes_a_crab_rage_split() -> None:
    # Ending a turn with one claw dead and another alive eats a (small) penalty vs leaving both
    # alive — a gentle nudge against a needless split (killing a claw is otherwise usually a boon).
    w = load_policy_config().combat
    split = SimState(energy=0, my_block=0, my_strength=0,
                     enemies=(_crab(0, "ROCKET"), _crab(150, "CRUSHER")))
    both_alive = SimState(energy=0, my_block=0, my_strength=0,
                          enemies=(_crab(150, "ROCKET"), _crab(150, "CRUSHER")))
    assert _score(split, w) < _score(both_alive, w)


def _bclaw(eid: str, incoming: int, hp: int = 150) -> EnemySim:
    # back-attack in isolation (no crab_rage, so the split penalty doesn't muddy the comparison)
    return EnemySim(entity_id=eid, hp=hp, max_hp=200, block=0, vulnerable=0, incoming=incoming,
                    back_attack=True)


def test_back_attack_adds_50pct_to_the_unfaced_claw() -> None:
    # Surrounded + 2 claws: the claw you face (state.facing) hits base; the OTHER hits +50%.
    w = load_policy_config().combat
    enemies = (_bclaw("ROCKET", 30), _bclaw("CRUSHER", 10))
    facing_rocket = SimState(energy=0, my_block=0, my_strength=0, surrounded=True,
                             facing="ROCKET", enemies=enemies)
    facing_crusher = SimState(energy=0, my_block=0, my_strength=0, surrounded=True,
                              facing="CRUSHER", enemies=enemies)
    # facing Rocket -> Crusher(10) is behind: incoming 30 + 10 + 5 = 45.
    # facing Crusher -> Rocket(30) is behind: incoming 30 + 10 + 15 = 55 -> worse (more loss).
    assert _score(facing_rocket, w) > _score(facing_crusher, w)


def test_back_attack_vanishes_once_one_claw_dies() -> None:
    # Down to a single claw you face it permanently — no +50%. So the surviving claw's incoming is
    # just its base, even while Surrounded is still flagged (the boon from killing a claw).
    w = load_policy_config().combat
    two = SimState(energy=0, my_block=0, my_strength=0, surrounded=True, facing="ROCKET",
                   enemies=(_bclaw("ROCKET", 30), _bclaw("CRUSHER", 10)))
    one = SimState(energy=0, my_block=0, my_strength=0, surrounded=True, facing="ROCKET",
                   enemies=(_bclaw("ROCKET", 30), _bclaw("CRUSHER", 10, hp=0)))
    # the +50% on the unfaced Crusher (worth -5 in hp_loss) is gone once it's dead -> higher score
    assert _score(one, w) > _score(two, w)


def test_player_frail_is_prebaked_not_reapplied() -> None:
    """CORRECTED 2026-07-14 (trace-verified): Frail is PRE-BAKED into the card text — a
    Defend under Frail already READS "Gain 3 Block" (5 x 0.75). The sim must take the
    text at face value; re-applying FRAIL_MULT double-counted it. Same class as the
    Strength/Dex pre-bake and the Pen Nib preview."""
    # the text a Frail player actually sees for a base-10 block card: 7
    block_card = PlannedCard(index=0, name="Defend", cost=1, fx=CardEffects(block=7),
                             targets_enemy=False)
    frail = _apply_card(SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0,
                                 my_frail=True), block_card, None)
    assert frail.my_block == 7  # face value, NOT 7*0.75=5


def test_whirlwind_x_cost_hits_resolve_to_energy() -> None:
    # "Deal 6 damage to ALL enemies X times": X-cost resolves to current energy, and the hit
    # count is that same X. At 3 energy Whirlwind is 3x6=18 -- it must beat a 9-damage Strike+.
    w = load_policy_config().combat
    hand = [_bcard(0, "WHIRLWIND", "Whirlwind", "X",
                   "Deal 6 damage to ALL enemies X times.", "Attack", "AllEnemy"),
            _bcard(1, "STRIKE_P", "Strike+", 1, "Deal 9 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand)), w)
    assert d.action.payload()["card_index"] == 0  # Whirlwind first at full X


def test_bloodletting_tempo_pricing_follows_the_hp_floor() -> None:
    # Two owner steers pinned together (2026-07-09). Parse layer: Conflagration ("Deal 2 damage
    # to ALL enemies 4 times") reads its real 2x4 value, so Bloodletting's payoff is visible.
    # Pricing layer: card self-HP costs are a TEMPO trade -- flat-cheap while projected end HP
    # stays above self_hp_cheap_floor (owner: "play Bloodletting+ as low as 15 hp"), scarcity
    # only below it. So BL is IN the plan even at 30/80, and out at 20/80 (projected 12 <= 15).
    w = load_policy_config().combat
    icon = "[ironclad_energy_icon.png]"

    def hand():
        return [_bcard(0, "CONFLAGRATION", "Conflagration", 1,
                       "Deal 2 damage to ALL enemies 4 times.", "Attack", "AllEnemy"),
                _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
                _bcard(2, "STRIKE_P", "Strike+", 1, "Deal 9 damage.", "Attack", "AnyEnemy"),
                _bcard(3, "BLOODLETTING_P", "Bloodletting+", 0,
                       f"Lose 3 HP. Gain {icon}{icon}{icon}.", "Skill", "None"),
                _bcard(4, "ASHEN_P", "Ashen Strike+", 1, "Deal 10 damage.", "Attack", "AnyEnemy")]

    for hp in (80, 30):
        d = plan_combat_turn(parse_state(_beckon_state(3, hand(), enemy_hp=197, hp=hp)), w)
        plan = d.rationale.split("[")[1].split("]")[0]
        assert "Bloodletting+" in plan and "Conflagration" in plan, hp

    low = plan_combat_turn(parse_state(_beckon_state(3, hand(), enemy_hp=197, hp=20)), w)
    plan_low = low.rationale.split("[")[1].split("]")[0]
    assert "Bloodletting+" not in plan_low  # projected 12 <= floor 15: scarcity is back
    assert "Conflagration" in plan_low  # the parse fix holds regardless of HP


def test_projected_death_wall_blocks_suicidal_self_cost() -> None:
    # A non-lethal turn that projects you to <=0 HP is walled off outright ("unless it led to
    # death by fatal" -- owner); on a lethal end-state the wall doesn't apply (fight ends first).
    from dataclasses import replace
    w = load_policy_config().combat
    alive = _state(_enemy())
    suicidal = replace(alive, self_damage=6)
    assert _score(suicidal, w, my_hp=3) < _score(alive, w, my_hp=3) - 400
    killed = replace(alive, enemies=(replace(alive.enemies[0], hp=0),), self_damage=6, kills=1)
    assert _score(killed, w, my_hp=3) > _score(suicidal, w, my_hp=3)  # lethal: no wall


def test_negative_dexterity_thins_card_block() -> None:
    # Soul Siphon drives player Dexterity negative; a drained Defend really grants less block,
    # so the planner must not over-block-on-paper (Lagavulin trace 2026-07-09: Dex hit -4).
    from dataclasses import replace as dc_replace
    base = SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0)
    defend = PlannedCard(index=0, name="Defend", cost=1, fx=CardEffects(block=8),
                         targets_enemy=False, is_attack=False)
    plain = _apply_card(base, defend, None)
    drained = _apply_card(dc_replace(base, my_dex=-4), defend, None)
    assert plain.my_block == 8 and drained.my_block == 4
    boosted = _apply_card(dc_replace(base, my_dex=2), defend, None)
    assert boosted.my_block == 10  # positive Dexterity now counts too


def test_planner_does_not_chip_a_sleeper_awake() -> None:
    # Lagavulin starts Asleep (free setup turns; waking sheds her Plating for her). Chipping
    # earns no offensive credit, so with a non-lethal hand the planner banks a Power instead
    # of attacking her awake (2026-07-09 trace: bot chipped 222->213 on round 1).
    w = load_policy_config().combat
    asleep = [{"id": "ASLEEP_POWER", "name": "Asleep", "amount": 3,
               "description": "Awakens upon losing HP or after 3 turns."}]
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "DEMON_FORM", "Demon Form", 3,
                   "At the start of your turn, gain 2 Strength.", "Power", "None")]
    d = plan_combat_turn(
        parse_state(_beckon_state(3, hand, enemy_hp=222, hp=75,
                                  enemy_status=asleep, incoming="0")), w)
    assert d.action.payload().get("card_index") == 1  # the Power, not the wake-chip


def test_planner_still_kills_a_sleeper_when_lethal() -> None:
    # The exception: if the attack kills the sleeper outright, take it (no wake ever happens).
    w = load_policy_config().combat
    asleep = [{"id": "ASLEEP_POWER", "name": "Asleep", "amount": 3,
               "description": "Awakens upon losing HP or after 3 turns."}]
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(
        parse_state(_beckon_state(3, hand, enemy_hp=5, hp=75,
                                  enemy_status=asleep, incoming="0")), w)
    assert d.action.payload().get("card_index") == 0 and "LETHAL" in d.rationale


def test_free_heal_played_before_the_killing_blow() -> None:
    # Owner-caught 2026-07-09: lethal taken with 2 spare energy while Not Yet (2e, Heal 10)
    # sat in hand -- nothing resolves after the kill, so the heal must go FIRST. The DFS no
    # longer extends past a lethal state, so only heal-then-kill keeps the healing credit.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "NOT_YET", "Not Yet", 2, "Heal 10 HP.", "Skill", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=5, hp=40)), w)
    assert d.action.payload()["card_index"] == 1  # heal first...
    plan = d.rationale.split("[")[1].split("]")[0]
    assert "LETHAL" in d.rationale and plan.startswith("Not Yet")  # ...then the kill


def test_player_disintegration_counts_as_blockable_incoming() -> None:
    # Knowledge Demon's Disintegration is a PLAYER status ("At the end of your turn, take 6
    # damage" -- captured live 2026-07-09). The planner must reserve block for it: with no
    # enemy attack incoming, it still plays Defend to soak the end-of-turn tick.
    w = load_policy_config().combat
    state = _beckon_state(
        3,
        [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 8 Block.", "Skill", "None"),
         _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")],
        enemy_hp=300, hp=20, incoming="0")
    state["battle"]["enemies"][0]["intents"] = [{"type": "buff", "label": ""}]
    state["player"]["status"] = [{"id": "DISINTEGRATION_POWER", "name": "Disintegration",
                                  "amount": 6,
                                  "description": "At the end of your turn, take 6 damage."}]
    d = plan_combat_turn(parse_state(state), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert "Defend" in plan  # block reserved for the end-of-turn tick
    assert d.scores["hp_loss"] == 0.0  # 6 end-damage fully soaked by the 8 block


def test_sleeper_damage_is_a_complete_sim_noop() -> None:
    # The partial deny leaked reward through _score's focus term (live: Volley/Tremble woke
    # Lagavulin round 1, batch bnyka47dn) -- a non-killing hit on a sleeper must leave the
    # sim enemy UNTOUCHED so no downstream term (focus, stun crossing) sees progress.
    out = _apply_attack(_state(_enemy(asleep=True)), 0, _attack(30))
    assert out.enemies[0].hp == 100  # no hp progress at all
    assert out.damage_dealt == 0


def _fysh_with_potion(enemy_hp: int, hand: list, potions: list) -> dict:
    st = _beckon_state(3, hand, enemy_hp=enemy_hp, hp=50, incoming="15")
    st["player"]["potions"] = potions
    st["player"]["max_potion_slots"] = 3
    return st


def test_damage_potion_joins_a_lethal_plan() -> None:
    # Owner question 2 (2026-07-09): cards alone aren't lethal (6 dmg vs 25 HP) but
    # Strike + Fire Potion (20) is -- the planner must find the combined lethal instead of
    # settling into a block pattern.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 8 Block.", "Skill", "None")]
    pots = [{"id": "FIRE_POTION", "name": "Fire Potion", "description": "Deal 20 damage.",
             "slot": 0, "can_use_in_combat": True, "target_type": "AnyEnemy", "keywords": []}]
    d = plan_combat_turn(parse_state(_fysh_with_potion(25, hand, pots)), w)
    assert "LETHAL" in d.rationale and "(potion)" in d.rationale


def test_damage_potion_held_outside_lethal() -> None:
    # Reluctance: same belt, un-killable enemy -- the potion must NOT appear in the plan.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 8 Block.", "Skill", "None")]
    pots = [{"id": "FIRE_POTION", "name": "Fire Potion", "description": "Deal 20 damage.",
             "slot": 0, "can_use_in_combat": True, "target_type": "AnyEnemy", "keywords": []}]
    d = plan_combat_turn(parse_state(_fysh_with_potion(200, hand, pots)), w)
    assert "(potion)" not in d.rationale


def test_used_potion_slots_excluded_from_planning() -> None:
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    pots = [{"id": "FIRE_POTION", "name": "Fire Potion", "description": "Deal 20 damage.",
             "slot": 0, "can_use_in_combat": True, "target_type": "AnyEnemy", "keywords": []}]
    d = plan_combat_turn(parse_state(_fysh_with_potion(25, hand, pots)), w,
                         used_potion_slots=(0,))
    assert "(potion)" not in d.rationale  # already drunk this round: not re-planned


def test_killing_a_death_spawner_is_not_lethal() -> None:
    # Phrog Parasite (Infested: "Upon dying, summons... something") splits into 4 stunned
    # Wrigglers mid-turn -- killing it must NOT read as LETHAL, so survival checks and
    # stranded-card tallies stay live on the kill turn (owner question 2026-07-09).
    w = load_policy_config().combat
    infested = [{"id": "INFESTED_POWER", "name": "Infested", "amount": 1,
                 "description": "Upon dying, summons... something."}]
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(
        parse_state(_beckon_state(3, hand, enemy_hp=5, hp=50, enemy_status=infested)), w)
    assert d.action.payload()["card_index"] == 0  # still takes the kill
    assert "LETHAL" not in d.rationale  # but the fight is not declared over


def test_normality_in_hand_caps_the_plan() -> None:
    # Curses pass (owner 2026-07-09): Normality in HAND ("cannot play more than 3 cards this
    # turn") caps the DFS -- with 5 affordable cards the plan holds to <=3 plays.
    w = load_policy_config().combat
    hand = [_bcard(0, "NORMALITY", "Normality", 0,
                   "Unplayable. You cannot play more than 3 cards this turn.", "Curse",
                   "None", can_play=False)]
    hand += [_bcard(i, f"S{i}", f"Strike{i}", 1, "Deal 6 damage.", "Attack", "AnyEnemy")
             for i in range(1, 6)]
    d = plan_combat_turn(parse_state(_beckon_state(5, hand, enemy_hp=300, hp=70)), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert len(plan.split(" > ")) <= 3


def test_decay_curse_counts_as_blockable_stranded_damage() -> None:
    # Decay ("At the end of your turn, if this is in your Hand, take 2 damage") rides the
    # existing stranded-Toxic machinery: blockable, unclearable (Unplayable).
    w = load_policy_config().combat
    hand = [_bcard(0, "DECAY", "Decay", 0,
                   "Unplayable. At the end of your turn, if this is in your Hand, take 2 "
                   "damage.", "Curse", "None", can_play=False)]
    hand.append(_bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 8 Block.", "Skill", "None"))
    st = _beckon_state(3, hand, enemy_hp=100, hp=40, incoming="0")
    st["battle"]["enemies"][0]["intents"] = [{"type": "buff", "label": ""}]
    d = plan_combat_turn(parse_state(st), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert "Defend" in plan  # block reserved specifically for Decay's end-of-turn tick
    assert d.scores["hp_loss"] == 0.0


def test_c_tranche_bully_scales_with_target_vulnerable() -> None:
    # Bully: "Deal 4 damage. Deals 2 additional damage for each Vulnerable on the enemy."
    from sts2bot.policy.combat import _to_planned

    class C:
        index = 0
        id = "BULLY"
        name = "Bully"
        type = "Attack"
        cost = "0"
        can_play = True
        target_type = "AnyEnemy"
        is_upgraded = False
        description = "Deal 4 damage. Deals 2 additional damage for each Vulnerable on the enemy."
    from dataclasses import replace as dc_replace
    card = _to_planned(C(), 3)
    out = _apply_attack(_state(dc_replace(_enemy(), vulnerable=3)), 0, card)
    # per-hit = 4 + 2*3 = 10, then VULN_MULT 1.5 -> 15
    assert out.damage_dealt == 15


_VULN_POWER = {"id": "VULNERABLE_POWER", "name": "Vulnerable", "amount": 4,
               "description": "Receive 50% more damage from Attacks for 4 turns."}
_RINGING_POWER = {"id": "RINGING_POWER", "name": "Ringing", "amount": 1,
                  "description": "You can only play 1 card this turn."}


def test_power_suffix_colossus_ringing_regression() -> None:
    # Owner live-caught (2026-07-12, Ceremonial Beast boss): on a Ringing turn (1-card cap)
    # with the beast Vulnerable(4) and a 15 attack telegraphed, the bot cast Defend over
    # Colossus. Root cause: live status ids carry a _POWER suffix (VULNERABLE_POWER) and the
    # sim matched `== "VULNERABLE"`, so pre-existing stacks were invisible and Colossus'
    # halving never fired. This test uses the exact live id shapes.
    w = load_policy_config().combat
    hand = [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block. Ringing.",
                   "Skill", "None"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage. Ringing.",
                   "Attack", "AnyEnemy"),
            _bcard(2, "COLOSSUS", "Colossus", 1,
                   "Gain 5 Block. You receive 50% less damage from Vulnerable enemies "
                   "this turn. Ringing.", "Skill", "None")]
    st = _beckon_state(5, hand, enemy_hp=100, hp=57,
                       enemy_status=[dict(_VULN_POWER)], incoming="15")
    st["player"]["status"] = [dict(_RINGING_POWER)]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 2  # Colossus, not Defend
    assert d.scores["hp_loss"] == 2.0  # 15 halved to 7, minus 5 block


def test_strength_is_prebaked_in_card_text_not_double_counted() -> None:
    """CRITICAL (2026-07-14, trace-verified): the mod's card text is a RESOLVED preview —
    at Strength 4 a Strike already READS "Deal 10 damage". Adding my_strength on top
    double-counts (the _POWER fix of 07-13 introduced this; the old exact-match bug had
    masked it). The sim must use the text as-is, adding only MID-PLAN strength gains."""
    w = load_policy_config().combat
    # live-shaped: Str 4, and the text already shows the boosted 10
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=10, hp=40, incoming="5")
    st["player"]["status"] = [{"id": "STRENGTH_POWER", "name": "Strength", "amount": 4,
                               "description": "Increases attack damage by 4."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0  # 10 kills 10 — exactly, no phantom +4
    # ...and it must NOT claim lethal on a 13-HP enemy (the old double-count made it 14)
    st2 = _beckon_state(3, hand, enemy_hp=13, hp=40, incoming="5")
    st2["player"]["status"] = list(st["player"]["status"])
    d2 = plan_combat_turn(parse_state(st2), w)
    assert d2.scores["lethal"] == 0.0


def test_midplan_strength_gain_is_added() -> None:
    """The other half: strength gained DURING the plan (Inflame) is NOT in the text
    preview of cards drawn/held this turn, so it MUST be added to later attacks."""
    w = load_policy_config().combat
    hand = [_bcard(0, "INFLAME", "Inflame", 1, "Gain 2 Strength.", "Power", "Self"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=8, hp=40, incoming="5")
    d = plan_combat_turn(parse_state(st), w)
    # Inflame first (+2 Str), then Strike hits for 6+2=8 -> lethal on 8 HP
    assert d.action.payload()["card_index"] == 0
    assert d.scores["lethal"] == 1.0


def test_dexterity_is_prebaked_in_block_text() -> None:
    # Same pre-bake for Dexterity: at Dex 2 a Defend already reads "Gain 7 Block".
    w = load_policy_config().combat
    hand = [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 7 Block.", "Skill", "None")]
    st = _beckon_state(3, hand, enemy_hp=100, hp=40, incoming="7")
    st["player"]["status"] = [{"id": "DEXTERITY_POWER", "name": "Dexterity", "amount": 2,
                               "description": "Gain 2 additional Block from cards."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["hp_loss"] == 0.0  # 7 block vs 7 incoming — not 9 vs 7


def test_preexisting_vulnerable_power_credited() -> None:
    # Cross-turn Vulnerable (applied a previous turn, arriving as VULNERABLE_POWER in the
    # payload) must grant the 1.5x credit: "Deal 6 damage." into Vulnerable = 9 -> lethal.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=9, hp=40,
                       enemy_status=[dict(_VULN_POWER)], incoming="5")
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0


def _with_relics(st: dict, *relics) -> dict:
    st["player"]["relics"] = [
        {"id": rid, "name": rid.title().replace("_", " "),
         "description": desc, "counter": counter}
        for rid, desc, counter in relics
    ]
    return st


def test_eot_relic_orichalcum_and_cloak_clasp() -> None:
    # R2: Orichalcum ("If you end your turn without Block, gain 6 Block") makes an
    # all-attack turn safer — with 6 incoming, the planner should NOT burn its only
    # Defend when Orichalcum covers the hit for free; it attacks instead.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    st = _beckon_state(1, hand, enemy_hp=100, hp=50, incoming="6")  # 1 energy: pick one
    _with_relics(st, ("ORICHALCUM",
                      "If you end your turn without Block, gain 6 Block.", None))
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("card_index") == 0  # attack; Orichalcum blocks free
    st["player"]["relics"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.action.payload().get("card_index") == 1  # without it, Defend wins


def test_eot_relic_ice_cream_banks_energy() -> None:
    # R2: Ice Cream ("Energy is now conserved between turns") removes the waste penalty
    # on unspent energy — a marginal chip attack should no longer be forced just to
    # spend down (zero-threat enemy, tiny Strike into a huge pool).
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 2 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=300, hp=60, incoming="0")
    st["battle"]["enemies"][0]["intents"] = []
    base = plan_combat_turn(parse_state(st), w)
    _with_relics(st, ("ICE_CREAM", "Energy is now conserved between turns.", None))
    banked = plan_combat_turn(parse_state(st), w)
    # with Ice Cream, ending the turn (banking 3 energy) must score no worse than
    # before relative to chipping; concretely the end-turn option should now win
    assert banked.scores["plan_score"] >= base.scores["plan_score"] \
        or banked.action.payload()["action"] == "end_turn"


def test_relic_trigger_letter_opener_lethal() -> None:
    # Relic pass R1: "Every time you play 3 Skills in a single turn, deal 5 damage to
    # ALL enemies." Three Defends into a 5-HP enemy IS lethal with Letter Opener.
    w = load_policy_config().combat
    hand = [_bcard(i, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")
            for i in range(3)]
    st = _beckon_state(3, hand, enemy_hp=5, hp=60, incoming="10")
    _with_relics(st, ("LETTER_OPENER",
                      "Every time you play 3 Skills in a single turn, deal 5 damage "
                      "to ALL enemies.", None))
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0
    # without the relic the same hand cannot kill
    st["player"]["relics"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores["lethal"] == 0.0


def test_relic_trigger_nunchaku_lifetime_counter() -> None:
    # Nunchaku ("Every time you play 10 Attacks, gain [E]") banks its counter across
    # combats like Pen Nib: at counter 9, the FIRST attack this turn pays the energy —
    # here it funds a second Strike that completes lethal on a 20-HP enemy.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(1, hand, enemy_hp=20, hp=60, incoming="10")  # 1 energy!
    _with_relics(st, ("NUNCHAKU", "Every time you play 10 Attacks, gain [energy].", 9))
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0
    # at counter 3 no trigger fires: only one Strike is affordable -> not lethal
    st["player"]["relics"][0]["counter"] = 3
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores["lethal"] == 0.0


def test_paper_phrog_boosts_vuln_multiplier() -> None:
    # "Enemies with Vulnerable take 75% more damage rather than 50%." — rides the
    # Cruelty lane: 10 dmg into Vulnerable = 17 (1.75x), lethal on a 17-HP enemy.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=17, hp=40,
                       enemy_status=[dict(_VULN_POWER)], incoming="5")
    _with_relics(st, ("PAPER_PHROG",
                      "Enemies with Vulnerable take 75% more damage rather than 50%.",
                      None))
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0
    st["player"]["relics"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores["lethal"] == 0.0  # int(10*1.5)=15 < 17


def test_velvet_choker_card_cap_from_relic() -> None:
    # "Gain [E] at the start of each turn. You cannot play more than 6 cards per turn."
    # The cap half must join the card-cap machinery from RELIC text.
    from sts2bot.policy.combat import _RELIC_TRIGGERS  # noqa: F401 (import sanity)
    w = load_policy_config().combat
    hand = [_bcard(i, "STRIKE_IRONCLAD", "Strike", 0, "Deal 2 damage.",
                   "Attack", "AnyEnemy") for i in range(8)]
    st = _beckon_state(3, hand, enemy_hp=100, hp=60, incoming="0")
    _with_relics(st, ("VELVET_CHOKER",
                      "Gain [energy] at the start of each turn. You cannot play more "
                      "than 6 cards per turn.", None))
    d = plan_combat_turn(parse_state(st), w)
    plan_part = d.rationale.split("]")[0].split("[", 1)[1]
    assert len(plan_part.split(" > ")) <= 6  # plan never exceeds the cap


def test_self_lethal_hp_cost_vetoed() -> None:
    # Owner-caught (2026-07-13): at 3 HP the bot played Bloodletting (Lose 3 HP) — both
    # branches sat on the projected-death wall, so the energy bonus broke the tie into
    # suicide. Self-lethal HP costs are an absolute veto, not a scored preference.
    w = load_policy_config().combat
    hand = [_bcard(0, "BLOODLETTING", "Bloodletting", 0,
                   "Lose 3 HP. Gain [ironclad_energy_icon.png][ironclad_energy_icon.png].",
                   "Skill", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=50, hp=3,
                                                   incoming="20")), w)
    assert d.action.payload()["action"] == "end_turn"  # never the suicide play
    # at 4 HP the same card is legal again (floor pricing governs, not the veto)
    d2 = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=50, hp=4,
                                                    incoming="20")), w)
    assert d2 is not None  # merely must not crash; the veto no longer filters it


def test_guard_redirect_machinery(monkeypatch) -> None:
    # Guard-pair redirect machinery (traced 2026-07-13 vs Bowlbugs, PINNED pending seed
    # verification — the table ships empty; this test injects a pair). Attacks aimed at
    # the guarded enemy hit the living guard; once the guard dies, the target is real.
    from dataclasses import replace as dc_replace

    import sts2bot.policy.combat as combat_mod
    from sts2bot.policy.combat import _to_planned
    monkeypatch.setattr(combat_mod, "_GUARD_PAIRS", {"BOWLBUG_NECTAR": "BOWLBUG_ROCK"})

    class C:
        index = 0
        id = "STRIKE_IRONCLAD"
        name = "Strike"
        type = "Attack"
        cost = "1"
        can_play = True
        target_type = "AnyEnemy"
        is_upgraded = False
        description = "Deal 6 damage."
    card = _to_planned(C(), 3)
    rock = dc_replace(_enemy(), entity_id="BOWLBUG_ROCK_0", hp=17)
    nectar = dc_replace(_enemy(), entity_id="BOWLBUG_NECTAR_0", hp=2)
    st = SimState(energy=3, enemies=(rock, nectar), my_block=0, my_strength=0)
    out = _apply_attack(st, 1, card)  # aim at Nectar
    assert out.enemies[0].hp == 11 and out.enemies[1].hp == 2  # Rock took it
    dead_rock = dc_replace(rock, hp=0)
    st2 = SimState(energy=3, enemies=(dead_rock, nectar), my_block=0, my_strength=0)
    out2 = _apply_attack(st2, 1, card)
    assert out2.enemies[1].hp == 0  # guard down -> Nectar dies for real


def test_armaments_plus_played_for_the_upgrade_rider() -> None:
    # Owner-caught (2026-07-13): Armaments+ ("Gain 5 Block. Upgrade ALL cards in your
    # hand.") sat unplayed when block wasn't needed — the rider was invisible. With
    # unupgraded cards in hand it must now be worth playing; with none, it stays a
    # plain block card (no phantom credit).
    w = load_policy_config().combat
    hand = [_bcard(0, "ARMAMENTS", "Armaments+", 1,
                   "Gain 5 Block. Upgrade ALL cards in your hand.", "Skill", "None"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy"),
            _bcard(2, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=100, hp=70, incoming="0")
    st["battle"]["enemies"][0]["intents"] = []  # no threat: block itself is worthless
    d = plan_combat_turn(parse_state(st), w)
    assert "Armaments+" in d.rationale  # the rider earns it a place in the plan
    # all-upgraded hand: the rider is worthless, so nothing forces a play
    st["player"]["hand"] = [dict(hand[0]), dict(hand[1])]
    st["player"]["hand"][0]["is_upgraded"] = True
    st["player"]["hand"][1]["is_upgraded"] = True
    d2 = plan_combat_turn(parse_state(st), w)
    assert "Armaments+" not in (d2.rationale or "") or "end turn" in d2.rationale


def test_splash_aoe_omnislice_gets_a_target() -> None:
    # C5 halt (2026-07-13, Louse Progenitor f29): Omnislice is aoe in the sim ("Damage
    # ALL other enemies...") but target_type=AnyEnemy in the game — the planner submitted
    # it targetless and the game rejected it 8 times. The action must carry a target.
    w = load_policy_config().combat
    hand = [_bcard(0, "OMNISLICE", "Omnislice", 0,
                   "Deal 8 damage. Damage ALL other enemies equal to the damage dealt.",
                   "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=50, hp=40)), w)
    payload = d.action.payload()
    assert payload["action"] == "play_card" and payload["card_index"] == 0
    assert payload.get("target") == "s0"  # the click-target is REQUIRED


_BURROWED = {"id": "BURROWED_POWER", "name": "Burrowed", "amount": 1,
             "description": "Block is not removed at the start of Tunneler's turn. "
                            "Stunned if all Block is removed."}
_RAVENOUS = {"id": "RAVENOUS_POWER", "name": "Ravenous", "amount": 4,
             "description": "When an enemy dies, Corpse Slug immediately eats it, "
                            "becoming Stunned and gaining 4 Strength."}


def test_ramp_stall_penalty_forces_the_race() -> None:
    # Damp Cultist turtle-death (2026-07-16): vs a +5/turn Ritual ramper, four straight
    # all-block turns each looked locally optimal (take 1 now vs take 6 now). The
    # ramp-stall penalty prices the stalled turn's future cost: the Strike line must win.
    w = load_policy_config().combat
    hand = [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(3, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=53, hp=40, incoming="16")
    st["battle"]["enemies"][0]["status"] = [
        {"id": "RITUAL_POWER", "name": "Ritual", "amount": 5,
         "description": "At the end of its turn, gains 5 Strength."},
        {"id": "STRENGTH_POWER", "name": "Strength", "amount": 15,
         "description": "Increases attack damage by 15."}]
    d = plan_combat_turn(parse_state(st), w)
    plan_part = d.rationale.split("]")[0]
    assert "Strike" in plan_part  # the race line, not triple-Defend


def test_burrowed_block_strip_stuns_tunneler() -> None:
    # Harness-found (2026-07-16): stripping a Burrowed Tunneler's block to 0 STUNS it —
    # its telegraphed 23-attack never lands. The planner should prefer breaking the
    # block over plain defending when that cancels the hit.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=60, hp=30, incoming="23",
                       enemy_status=[dict(_BURROWED)])
    st["battle"]["enemies"][0]["block"] = 5  # one Strike strips it
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 0  # attack to break the block
    assert d.scores["hp_loss"] == 0.0  # the 23 is cancelled by the stun


def test_ravenous_pack_kill_cancels_their_turn() -> None:
    # Corpse Slugs: killing ONE makes the survivors eat it (self-stun) — the whole
    # pack's attacks cancel. Killing the 5-HP slug beats defending against the pack.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=5, hp=30, incoming="6",
                       enemy_status=[dict(_RAVENOUS)])
    st["battle"]["enemies"].append(
        {"entity_id": "s1", "name": "Corpse Slug", "hp": 26, "max_hp": 30, "block": 0,
         "status": [dict(_RAVENOUS)],
         "intents": [{"type": "attack", "label": "14"}]})
    d = plan_combat_turn(parse_state(st), w)
    p = d.action.payload()
    assert p["card_index"] == 0 and p.get("target") == "s0"  # kill the weak slug
    assert d.scores["hp_loss"] == 0.0  # survivor eats -> its 14 never lands


def test_plating_end_of_turn_block_soaks_incoming() -> None:
    # Harness signature n=31 (2026-07-16): Plating's end-of-turn block lands BEFORE the
    # enemy turn, so hp_loss must count it — the planner over-predicted its own losses
    # by ~Plating every turn it was up (and over-blocked in response).
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=100, hp=50, incoming="4")
    st["player"]["status"] = [
        {"id": "PLATING_POWER", "name": "Plating", "amount": 5,
         "description": "At the end of your turn, gain 4 Block. Plating is reduced "
                        "by 1 at the start of your turn."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["hp_loss"] == 0.0  # 4 incoming vs 4 Plating block — fully soaked
    st["player"]["status"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores["hp_loss"] == 4.0  # without Plating the 4 lands


def test_cruelty_boosts_vulnerable_multiplier() -> None:
    # Cruelty (power): "Vulnerable enemies take an additional 25% damage" — additive with
    # Vulnerable's 50% (owner 2026-07-12; hover preview shows it). 10 dmg -> 17, not 15:
    # enough to flip lethal on a 16-HP Vulnerable enemy.
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=16, hp=40,
                       enemy_status=[dict(_VULN_POWER)], incoming="5")
    st["player"]["status"] = [
        {"id": "CRUELTY_POWER", "name": "Cruelty", "amount": 25,
         "description": "Vulnerable enemies take an additional 25% damage."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["lethal"] == 1.0  # int(10 * 1.75) = 17 >= 16
    # without Cruelty the same swing is int(10 * 1.5) = 15 -> not lethal
    st["player"]["status"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores["lethal"] == 0.0


def test_feed_preferred_for_the_killing_blow() -> None:
    # Feed's "If Fatal, raise your Max HP by 3" was invisible: with two ways to kill,
    # the planner never preferred landing Feed (step-1 audit, owner-confirmed 07-12).
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 10 damage.",
                   "Attack", "AnyEnemy"),
            _bcard(1, "FEED", "Feed", 1,
                   "Deal 10 damage. If Fatal, raise your Max HP by 3. Exhaust.",
                   "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=8, hp=40)), w)
    assert d.action.payload()["card_index"] == 1  # Feed lands the kill, not Strike
    assert d.scores["lethal"] == 1.0


def test_gambit_death_rider_never_planned() -> None:
    # The Gambit: "Gain 50 Block. If you take unblocked attack damage this combat, die."
    # A one-turn planner can't certify combat-long perfect blocking -> strictly unplayable.
    from sts2bot.policy.combat import _to_planned

    class C:
        index = 0
        id = "THE_GAMBIT"
        name = "The Gambit"
        type = "Skill"
        cost = "0"
        can_play = True
        target_type = "None"
        is_upgraded = False
        description = "Gain 50 Block. If you take unblocked attack damage this combat, die."
    assert _to_planned(C(), 3) is None


def test_c_tranche_dominate_strength_per_vuln() -> None:
    # Dominate: "Apply 1 Vulnerable. Gain 1 Strength for each Vulnerable on the enemy."
    w = load_policy_config().combat
    hand = [_bcard(0, "DOMINATE", "Dominate", 1,
                   "Apply 1 Vulnerable. Gain 1 Strength for each Vulnerable on the enemy. "
                   "Exhaust.", "Skill", "AnyEnemy")]
    st = _beckon_state(3, hand, enemy_hp=100, hp=70)
    st["battle"]["enemies"][0]["status"] = [
        {"id": "VULNERABLE", "name": "Vulnerable", "amount": 2,
         "description": "Receive 50% more damage from Attacks."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 0  # worth playing: 3 Str after its own vuln


def test_c_tranche_dark_shackles_reduces_incoming() -> None:
    # Dark Shackles: "Enemy loses 9 Strength this turn." -> incoming drops, hp_loss falls.
    from sts2bot.policy.combat import _to_planned

    class C:
        index = 0
        id = "DARK_SHACKLES"
        name = "Dark Shackles"
        type = "Skill"
        cost = "0"
        can_play = True
        target_type = "AnyEnemy"
        is_upgraded = False
        description = "Enemy loses 9 Strength this turn. Exhaust."
    from dataclasses import replace as dc_replace
    card = _to_planned(C(), 3)
    out = _apply_card(_state(dc_replace(_enemy(), incoming=14)), card, 0)
    assert out.enemies[0].incoming == 5  # 14 - 9


def test_c_tranche_exhaust_gate_evil_eye_and_ritual() -> None:
    # Evil Eye's second 8 Block and Forgotten Ritual's energy fire only AFTER something
    # was Exhausted this turn; the DFS orders an exhauster first to unlock them.
    from dataclasses import replace as dc_replace

    from sts2bot.policy.combat import _to_planned

    class EE:
        index = 0
        id = "EVIL_EYE"
        name = "Evil Eye"
        type = "Skill"
        cost = "1"
        can_play = True
        target_type = "None"
        is_upgraded = False
        description = "Gain 8 Block. Gain another 8 Block if you have Exhausted a card this turn."
    ee = _to_planned(EE(), 3)
    cold = _apply_card(_state(_enemy()), ee, None)
    assert cold.my_block == 8  # gate closed
    hot = _apply_card(dc_replace(_state(_enemy()), exhausted_this_turn=True), ee, None)
    assert hot.my_block == 16  # gate open

    class FR:
        index = 1
        id = "FORGOTTEN_RITUAL"
        name = "Forgotten Ritual"
        type = "Skill"
        cost = "1"
        can_play = True
        target_type = "None"
        is_upgraded = False
        description = ("If you Exhausted a card this turn, gain [ironclad_energy_icon.png]"
                       "[ironclad_energy_icon.png][ironclad_energy_icon.png]. Exhaust.")
    fr = _to_planned(FR(), 3)
    cold = _apply_card(_state(_enemy()), fr, None)
    assert cold.energy == 2  # paid 1, gained 0 (gate closed)
    hot = _apply_card(dc_replace(_state(_enemy()), exhausted_this_turn=True), fr, None)
    assert hot.energy == 5  # paid 1, gained 3


def test_c_tranche_expect_a_fight_scales_with_hand_attacks() -> None:
    # Expect a Fight: "Gain [energy] for each Attack in your Hand."
    w = load_policy_config().combat
    hand = [_bcard(0, "EXPECT_A_FIGHT", "Expect a Fight", 2,
                   "Gain [ironclad_energy_icon.png] for each Attack in your Hand. You cannot "
                   "gain additional [ironclad_energy_icon.png] this turn.", "Skill", "None")]
    hand += [_bcard(i, f"S{i}", f"Strike{i}", 1, "Deal 6 damage.", "Attack", "AnyEnemy")
             for i in range(1, 5)]
    d = plan_combat_turn(parse_state(_beckon_state(2, hand, enemy_hp=300, hp=70)), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert "Expect a Fight" in plan  # 4 attacks in hand: nets +2, enabling more plays


def test_infernal_blade_credit_actually_lands() -> None:
    # Delta audit (2026-07-12) harness-confirmed the 07-09 IB fix never landed: a
    # non-targeting Skill's synthetic damage was dropped by _apply_card (no target, no AoE).
    # The generator credit is now targetable, so 0-cost IB+ gets played.
    w = load_policy_config().combat
    hand = [_bcard(0, "INFERNAL_BLADE", "Infernal Blade+", 0,
                   "Add a random Attack into your Hand. It's free to play this turn. Exhaust.",
                   "Skill", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=100, hp=60)), w)
    assert isinstance(d.action, type(d.action)) and d.action.payload().get("card_index") == 0


def test_apotheosis_flagged_power_like_and_played() -> None:
    # Apotheosis (2e Skill, "Upgrade ALL your cards for the rest of combat") had no parseable
    # effect and was never played; now it rides the power-horizon term (filed 2026-06-26,
    # implemented via the delta audit 2026-07-12).
    w = load_policy_config().combat
    hand = [_bcard(0, "APOTHEOSIS", "Apotheosis", 2,
                   "Upgrade ALL your cards for the rest of combat. Exhaust.", "Skill", "None"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=200, hp=70)), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert "Apotheosis" in plan  # banked early like a Power, not stranded


def _two_enemy_fight(target_hp: int = 40) -> dict:
    """Shrinker Beetle + a twin bystander, identical stats: only the carrier lane
    should break the targeting tie."""
    enemy = {"hp": target_hp, "max_hp": 40, "block": 0, "status": [],
             "intents": [{"type": "attack", "label": "8"}]}
    return {"state_type": "monster", "run": {"act": 1, "floor": 6, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                       "energy": 1, "status": [],
                       "hand": [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1,
                                       "Deal 6 damage.", "Attack", "AnyEnemy")]},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                       "enemies": [
                           dict(enemy, entity_id="b0", name="Bowlbug"),
                           dict(enemy, entity_id="SHRINKER_BEETLE_0",
                                name="Shrinker Beetle"),
                       ]}}


def test_carrier_damage_accrues_only_with_bystanders() -> None:
    # accumulator: damage to a carrier counts while another enemy lives...
    carrier = _enemy(debuff_carrier=True)
    other = EnemySim(entity_id="o", hp=50, max_hp=50, block=0, vulnerable=0, incoming=0)
    st = SimState(energy=3, enemies=(carrier, other), my_block=0, my_strength=0)
    out = _apply_attack(st, 0, _attack(10))
    assert out.carrier_damage == 10
    # ...but not when the carrier is the LAST enemy (killing it ends the fight anyway)
    alone = SimState(energy=3, enemies=(_enemy(debuff_carrier=True),),
                     my_block=0, my_strength=0)
    assert _apply_attack(alone, 0, _attack(10)).carrier_damage == 0
    # ...and never for a non-carrier
    st2 = SimState(energy=3, enemies=(other, carrier), my_block=0, my_strength=0)
    assert _apply_attack(st2, 0, _attack(10)).carrier_damage == 0


def test_planner_prioritizes_shrinker_beetle_in_multi_enemy_fight() -> None:
    """Owner 2026-07-17: Shrinker Beetle's big player-debuff is removed by its death, so
    with a bystander present the planner must aim at the beetle over an identical twin."""
    w = load_policy_config().combat
    d = plan_combat_turn(parse_state(_two_enemy_fight()), w)
    assert d.action.payload()["target"] == "SHRINKER_BEETLE_0"


def test_normality_live_remainder_caps_the_plan() -> None:
    """Owner-caught live (b1i49b9k0 f45): STS2 Normality text carries '(N cards left)' —
    a 3-card lethal was planned with 1 play left, Bloodletting spent it, the gate ate the
    actual kill. The planner must trust the live remainder over the static cap."""
    w = load_policy_config().combat
    norm = "Unplayable. You cannot play more than 3 cards this turn. (1 card left)"
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(3, "NORMALITY", "Normality", 0, norm, "Curse", "None", can_play=False)]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=100, hp=70)), w)
    plan = d.rationale.split("[")[1].split("]")[0]
    assert plan.count(">") + 1 == 1  # exactly one play planned, not three

    # full remainder: the static cap still allows 3
    hand[3]["description"] = ("Unplayable. You cannot play more than 3 cards "
                              "this turn. (3 cards left)")
    d3 = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=100, hp=70)), w)
    plan3 = d3.rationale.split("[")[1].split("]")[0]
    assert plan3.count(">") + 1 == 3


def test_primal_force_protects_keeper_attacks() -> None:
    """Owner 2026-07-18 ('very finicky card'): Primal Force's transform is a PERMANENT
    deck rewrite — Strikes upgrade into 16-dmg Giant Rocks, but keeper attacks (riders,
    big hits) get destroyed. The keeper penalty makes the DFS discover the right
    ordering on its own: keepers BEFORE Primal Force, Strikes after."""
    w = load_policy_config().combat
    pf = _bcard(0, "PRIMAL_FORCE", "Primal Force", 1,
                "Transform ALL Attacks you play this combat into Giant Rocks.",
                "Power", "None")
    strike = _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                    "AnyEnemy")
    upper = _bcard(2, "UPPERCUT", "Uppercut", 1,
                   "Deal 13 damage. Apply 1 Weak. Apply 1 Vulnerable.", "Attack",
                   "AnyEnemy")
    state = _beckon_state(3, [pf, strike, upper], enemy_hp=200, hp=70)
    d = plan_combat_turn(parse_state(state), w)
    plan = d.rationale.split("[")[1].split("]")[0].split(" > ")
    # all three played, keeper never after Primal Force
    assert set(plan) == {"Primal Force", "Strike", "Uppercut"}
    assert plan.index("Uppercut") < plan.index("Primal Force")
    assert plan.index("Strike") > plan.index("Primal Force")  # strike takes the upgrade


def test_planner_focuses_rocket_in_kaiser_fight() -> None:
    """Kaiser Crab forensics (2026-07-18): Rocket's escalating 27/33/49 nukes killed
    all four f33 runs while the bot burst the tamer Crusher. Rocket is now a
    kill-priority target — identical stats, the planner aims at ROCKET_0."""
    w = load_policy_config().combat
    enemy = {"hp": 60, "max_hp": 199, "block": 0, "status": [],
             "intents": [{"type": "attack", "label": "10"}]}
    state = {"state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
             "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                        "block": 0, "energy": 1, "status": [],
                        "hand": [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1,
                                        "Deal 6 damage.", "Attack", "AnyEnemy")]},
             "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                        "enemies": [dict(enemy, entity_id="CRUSHER_0", name="Crusher"),
                                    dict(enemy, entity_id="ROCKET_0", name="Rocket")]}}
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["target"] == "ROCKET_0"


def test_kaiser_boss_rule_exists() -> None:
    from sts2bot.policy.standard import _boss_draft_rule

    rule = _boss_draft_rule("Kaiser Crab")
    assert rule and rule["min_block"] == 9 and rule["rest_loss_bonus"] > 0


def test_intangible_enemy_reduces_every_instance_to_one() -> None:
    """Soul Fysh forensics (2026-07-18): his periodic Intangible turns reduce every
    damage instance to 1 — the sim was blind and planned two Strikes into one for 2
    total damage while Beckons piled up. Attacks into Intangible now score ~nothing,
    so the planner spends those turns blocking / clearing Beckons instead."""
    out = _apply_attack(_state(_enemy(intangible=True)), 0, _attack(30))
    assert out.damage_dealt == 1
    out2 = _apply_attack(_state(_enemy(intangible=True)), 0, _attack(8, hits=3))
    assert out2.damage_dealt == 3  # 1 per instance

    # plan level: enemy Intangible + a Beckon in hand -> clear the Beckon, don't attack
    w = load_policy_config().combat
    intang = [{"id": "INTANGIBLE_POWER", "name": "Intangible", "amount": 1,
               "description": "Reduce all damage taken and HP loss to 1."}]
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                   "AnyEnemy"),
            _bcard(1, "BECKON", "Beckon", 1, _BECKON_DESC, "Status", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(1, hand, enemy_hp=100,
                                                   enemy_status=intang)), w)
    assert d.action.payload()["card_index"] == 1  # the Beckon clear wins the energy


def test_soul_fysh_boss_rule_exists() -> None:
    from sts2bot.policy.standard import _boss_draft_rule

    rule = _boss_draft_rule("Soul Fysh")
    assert rule and rule["min_block"] == 9
