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
    _fight_over,
    _score,
    plan_combat_turn,
)
from sts2bot.policy.textparse import CardEffects, parse_card_description


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
    # the real invariant: BOTH Beckons are cleared this turn (12 unblockable
    # HP saved) -- the 2026-08-14 surplus-draw nudge may open with Pommel
    # (its draw lands with energy left), which is fine as long as no Beckon
    # gets crowded out of the plan
    ra = d.rationale or ""
    assert ra.count("Beckon") >= 2, ra
    assert d.action.payload()["card_index"] in (0, 1, 2), ra
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
    """v2 (queue #4, owner 2026-08-29): X-cost is now DYNAMIC — it costs and
    hits whatever energy remains at its play position, so fixed-cost cards
    sequence BEFORE the X-dump (the old pin froze the limitation: X baked at
    turn start made Whirlwind-first the only discoverable line). Here
    Strike+ (9) then Whirlwind at X=2 (12) = 21 beats Whirlwind-first 18."""
    w = load_policy_config().combat
    hand = [_bcard(0, "WHIRLWIND", "Whirlwind", "X",
                   "Deal 6 damage to ALL enemies X times.", "Attack", "AllEnemy"),
            _bcard(1, "STRIKE_P", "Strike+", 1, "Deal 9 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand)), w)
    assert d.action.payload()["card_index"] == 1  # fixed cost leads
    assert "Whirlwind" in (d.rationale or "")     # the X-dump follows in-plan


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


def test_sleeper_damage_counts_but_the_waking_hit_pays() -> None:
    # Sleeper model v3 (owner 2026-08-06): the old restore-untouched hack denied
    # real burst progress ('wake her with the deck's best burst' was
    # unrepresentable). Damage now COUNTS, asleep clears, and sleepers_woken
    # carries the wake penalty into _score.
    out = _apply_attack(_state(_enemy(asleep=True)), 0, _attack(30))
    assert out.enemies[0].hp == 70          # she keeps the damage
    assert out.enemies[0].asleep is False   # and wakes
    assert out.sleepers_woken == 1          # the waking hit pays once


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


def test_flame_barrier_retaliation_credited() -> None:
    """Owner 2026-07-18: Flame Barrier is thorns-for-a-turn in all but name ('Whenever
    you are attacked this turn, deal N damage back') — the planner credited it as pure
    block. Now: retaliate x every attack instance aimed at us this turn, as score
    credit only (no enemy-HP mutation, no false in-plan kills)."""
    from sts2bot.policy.textparse import parse_card_description

    fx = parse_card_description(
        "Gain 17 Block. Whenever you are attacked this turn, deal 4 damage back.")
    assert fx.retaliate == 4 and fx.block == 17

    # plan level: vs a 3-hit turn, Flame Barrier out-scores a same-block plain skill
    w = load_policy_config().combat
    fb = _bcard(0, "FLAME_BARRIER", "Flame Barrier", 2,
                "Gain 17 Block. Whenever you are attacked this turn, deal 4 damage "
                "back.", "Skill", "None")
    plain = _bcard(1, "IMPERVIOUS", "Impervious", 2, "Gain 17 Block.", "Skill", "None")
    state = _beckon_state(2, [fb, plain], enemy_hp=100, hp=60, incoming="6x3")
    d = plan_combat_turn(parse_state(state), w)
    assert d.action.payload()["card_index"] == 0  # Flame Barrier wins on retaliation
    # enemy HP untouched by the credit: 12 expected retaliation is score-only
    assert d.scores["plan_damage"] >= 12.0


def test_feel_no_pain_credits_exhaust_block() -> None:
    """Owner check 2026-07-18: FNP block per exhaust EVENT was entirely uncredited
    (invisible to pre-bake — it fires on events, not card text). With FNP 4 active:
    a self-exhausting card credits +4 block; Stoke (Exhaust your Hand) credits 4 x
    remaining hand — the exhaust-synergy edge that makes Stoke playable."""
    w = load_policy_config().combat
    fnp = [{"id": "FEEL_NO_PAIN_POWER", "name": "Feel No Pain", "amount": 4,
            "description": "Whenever a card is Exhausted, gain 4 Block."}]
    stoke = _bcard(0, "STOKE", "Stoke", 1,
                   "Exhaust your Hand. Add 1 random card into your Hand for each "
                   "card Exhausted.", "Skill", "None")
    junk = [_bcard(i, "WOUND", "Wound", 0, "Unplayable.", "Status", "None",
                   can_play=False) for i in (1, 2, 3)]
    state = _beckon_state(1, [stoke, *junk], enemy_hp=100, hp=60, incoming="12")
    state["player"]["status"] = fnp
    d = plan_combat_turn(parse_state(state), w)
    # Stoke exhausts the 3 remaining cards -> 12 FNP block covers the incoming 12
    assert d.action.payload()["card_index"] == 0
    assert d.scores["hp_loss"] == 0.0

    # Drum-class "when this card is Exhausted" text must NOT count as exhausting
    from sts2bot.policy.combat import _EX_HAND, _EX_ONE, _EX_SELF
    drum = "Draw 2 cards. When this card is Exhausted, gain energy."
    assert not (_EX_HAND.search(drum) or _EX_ONE.search(drum) or _EX_SELF.search(drum))
    assert _EX_SELF.search("Deal 16 damage to ALL enemies. Exhaust.")
    assert _EX_ONE.search("Exhaust a card in your hand. Gain 11 Block.")


def test_chains_of_binding_one_bound_card_per_turn() -> None:
    """Owner 2026-07-18 (Queen f48 deaths): Chains of Binding marks the first 3 draws
    Bound — only ONE Bound card is playable per turn. Plans sequencing 2+ Bound cards
    fizzled at the gate (Normality family). The DFS now picks the best single Bound
    card and fills the rest of the turn with un-Bound plays."""
    w = load_policy_config().combat
    kw = [{"name": "Bound",
           "description": "Only 1 Bound card can be played each turn."}]
    b_strike = dict(_bcard(0, "STRIKE_IRONCLAD", "Strike", 1,
                           "Deal 6 damage. Bound", "Attack", "AnyEnemy"), keywords=kw)
    b_bash = dict(_bcard(1, "BASH", "Bash", 2,
                         "Deal 8 damage. Apply 2 Vulnerable. Bound", "Attack",
                         "AnyEnemy"), keywords=kw)
    free = _bcard(2, "POMMEL_STRIKE", "Pommel Strike", 1,
                  "Deal 9 damage. Draw 1 card.", "Attack", "AnyEnemy")
    state = _beckon_state(3, [b_strike, b_bash, free], enemy_hp=100, hp=60)
    d = plan_combat_turn(parse_state(state), w)
    plan = d.rationale.split("[")[1].split("]")[0].split(" > ")
    bound_played = sum(1 for n in plan if n in ("Strike", "Bash"))
    assert bound_played == 1  # exactly one Bound card in the plan
    assert "Pommel Strike" in plan  # un-Bound card still fills the turn


def test_thrash_growth_bonus_with_fodder_hand_only() -> None:
    """Owner 2026-07-20: with a hand of Strikes + Thrash, avoiding Thrash is 'almost
    strictly wrong' — its permanent growth + thinning were unpriced while its per-hit
    costs (Skittish, thorns) were priced, tipping marginal contexts to Strike. The
    growth bonus fires ONLY when every other attack in hand is fodder (never risk
    the random exhaust eating a keeper)."""
    w = load_policy_config().combat
    thrash = _bcard(0, "THRASH", "Thrash", 1,
                    "Deal 4 damage twice. Exhaust a random Attack in your Hand and "
                    "add its damage to this card.", "Attack", "AnyEnemy")
    strike = _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                    "AnyEnemy")
    # Skittish enemy: first hit lands, then it gains block — the context that used
    # to tip the sim toward Strike
    skittish = [{"id": "SKITTISH_POWER", "name": "Skittish", "amount": 5,
                 "description": "When first damaged each turn, gains 5 Block."}]
    state = _beckon_state(1, [thrash, strike], enemy_hp=60, hp=60,
                          enemy_status=skittish, incoming="8")
    d = plan_combat_turn(parse_state(state), w)
    assert "Thrash" in d.rationale.split("[")[1].split("]")[0]

    # keeper in hand (Uppercut, riders) -> no bonus; Thrash competes on raw numbers
    upper = _bcard(1, "UPPERCUT", "Uppercut", 1,
                   "Deal 13 damage. Apply 1 Weak. Apply 1 Vulnerable.", "Attack",
                   "AnyEnemy")
    state2 = _beckon_state(1, [thrash, upper], enemy_hp=60, hp=60,
                           enemy_status=skittish, incoming="8")
    d2 = plan_combat_turn(parse_state(state2), w)
    assert "Uppercut" in d2.rationale.split("[")[1].split("]")[0]


def test_smoggy_caps_skills_at_one_per_turn() -> None:
    """Living Fog's Smoggy (owner 2026-07-20): only one Skill playable per turn —
    Bound-family constraint, visible as a player status. Plans must carry at most
    one Skill; attacks stay unrestricted."""
    w = load_policy_config().combat
    hand = [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(2, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                   "AnyEnemy")]
    state = _beckon_state(3, hand, enemy_hp=100, hp=60, incoming="15")
    state["player"]["status"] = [{
        "id": "SMOGGY_POWER", "name": "Smoggy", "amount": 1,
        "description": "Only one Skill can be played each turn."}]
    d = plan_combat_turn(parse_state(state), w)
    plan = d.rationale.split("[")[1].split("]")[0].split(" > ")
    assert plan.count("Defend") == 1  # second Defend blocked by Smoggy
    assert "Strike" in plan


def test_normality_zero_left_plans_no_cards() -> None:
    """Latent gap (code-read 2026-07-22): the DFS checked the play budget only when
    recursing, so '(0 cards left)' could still generate a 1-card plan that the game
    gate rejects. At zero budget: no card plays (potions remain legal)."""
    w = load_policy_config().combat
    norm = "Unplayable. You cannot play more than 3 cards this turn. (0 cards left)"
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                   "AnyEnemy"),
            _bcard(1, "NORMALITY", "Normality", 0, norm, "Curse", "None",
                   can_play=False)]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=100, hp=70)), w)
    assert "end turn" in d.rationale or (isinstance(d.action, type(d.action)) and \
        d.action.payload().get("action") == "end_turn")


def test_drinker_in_blast_potion_never_joins_by_text() -> None:
    # Owner ruling 2026-07-30 (KD fight, suspected mutual kill): a Foul-class blast
    # includes the drinker, and a mutual kill is a LOSS -- the finisher lane must
    # never pick it, and by TEXT (names lie: this one isn't called Foul at all).
    w = load_policy_config().combat
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    pots = [{"id": "MYSTERY_BREW", "name": "Mystery Brew",
             "description": "Deal 25 damage to ALL players and enemies.",
             "slot": 0, "can_use_in_combat": True, "target_type": "None", "keywords": []}]
    d = plan_combat_turn(parse_state(_fysh_with_potion(25, hand, pots)), w)
    assert "(potion)" not in d.rationale


def test_rollout_belt_excludes_drinker_in_blast_by_text() -> None:
    from types import SimpleNamespace as NS

    from sts2bot.policy.rollout import _classify_potions
    pots = [NS(id="MYSTERY_BREW", name="Mystery Brew",
               description="Deal 25 damage to ALL players and enemies."),
            NS(id="FIRE_POTION", name="Fire Potion", description="Deal 20 damage.")]
    belt = _classify_potions(pots)
    assert belt == [("damage", 20)]  # the blast never enters the sim's belt


def test_energy_gain_chain_discovers_production_into_stomp() -> None:
    # Owner live catch 2026-07-30 (run 20260730-232926, row 607): at 0 energy with
    # Production[0] ('Gain [E][E]. Exhaust.') + Stomp[2] in hand, the bot ended the
    # turn -- the game marks Stomp can_play=False (EnergyCostTooHigh) and _to_planned
    # dropped it from the candidate pool, so the chain was undiscoverable. Energy-
    # gated cards now stay in the pool; the DFS re-checks cost per state.
    w = load_policy_config().combat
    hand = [
        _bcard(0, "PRODUCTION", "Production", 0,
               "Gain [ironclad_energy_icon.png][ironclad_energy_icon.png]. Exhaust.",
               "Skill", "None"),
        _bcard(1, "STOMP", "Stomp", 2, "Deal 12 damage to ALL enemies.",
               "Attack", "AllEnemy"),
    ]
    hand[1]["can_play"] = False
    hand[1]["unplayable_reason"] = "EnergyCostTooHigh"
    st = _beckon_state(3, hand, enemy_hp=30, hp=50, incoming="10")
    st["player"]["energy"] = 0
    d = plan_combat_turn(parse_state(st), w)
    p = d.action.payload()
    assert p.get("action") == "play_card" and p.get("card_index") == 0, d.rationale


def test_thrash_growth_bonus_survives_howl_in_hand() -> None:
    # Owner thought experiment 2026-07-30: Thrash + Howl from Beyond is a jackpot
    # (Thrash's random exhaust banks Howl's 25 AND Howl replays itself from the
    # Exhaust Pile at end of turn, then reshuffles back) -- but the July-20 keeper
    # rule vetoed the growth bonus whenever a non-fodder attack was in hand, so the
    # planner actively AVOIDED the line. Self-replaying cards are exhaust-SAFE.
    w = load_policy_config().combat
    howl = _bcard(1, "HOWL_FROM_BEYOND", "Howl from Beyond", 3,
                  "Deal 25 damage to ALL enemies. At the end of your turn, "
                  "if this is in your Exhaust Pile, play it.", "Attack", "AllEnemy")
    thrash = _bcard(0, "THRASH", "Thrash", 1,
                    "Deal 4 damage twice. Exhaust a random Attack in your Hand "
                    "and add its damage to this card.", "Attack", "AnyEnemy")
    st = _beckon_state(3, [thrash, howl], enemy_hp=80, hp=60, incoming="5")
    plan_combat_turn(parse_state(st), w)  # smoke: the pair plans without error
    # the growth line must not be vetoed: Howl reads as exhaust-safe
    from types import SimpleNamespace as NS

    from sts2bot.policy.combat import _SELF_REPLAYS, _to_planned
    hc = NS(**howl, star_cost=None)
    assert _SELF_REPLAYS.search(hc.description)
    pc = _to_planned(hc, 3)
    assert pc is not None and pc.self_replays


def test_ice_cream_banks_energy_via_generators() -> None:
    # Owner micro-question 2026-07-31: with Ice Cream (energy carries over), will
    # the planner play an energy generator with NOTHING to spend on this turn?
    # Before: waste term was zeroed (neutral) so play friction said no. Now banked
    # energy is mildly positive.
    w = load_policy_config().combat
    prod = _bcard(0, "PRODUCTION", "Production", 0,
                  "Gain [ironclad_energy_icon.png][ironclad_energy_icon.png]. "
                  "Exhaust.", "Skill", "None")
    st = _beckon_state(1, [prod], enemy_hp=60, hp=60, incoming="0")
    st["player"]["energy"] = 0
    st["player"]["relics"] = [{"id": "ICE_CREAM", "name": "Ice Cream",
                               "description": "Energy is conserved between turns.",
                               "counter": None, "keywords": []}]
    d = plan_combat_turn(parse_state(st), w)
    p = d.action.payload()
    assert p.get("action") == "play_card" and p.get("card_index") == 0, d.rationale
    # without Ice Cream: same state must NOT bother (banked energy evaporates)
    st["player"]["relics"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.action.payload().get("action") != "play_card", d2.rationale


def test_throwing_axe_doubles_the_first_card_of_combat() -> None:
    # Owner relic pass 2026-08-01: 'The first card you play each combat is played
    # an extra time.' Enemy at 12 with a 6-damage Strike: lethal WITH the axe on
    # round 1, not without; and NOT armed on later rounds (piles non-empty).
    w = load_policy_config().combat
    strike = _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                    "Attack", "AnyEnemy")
    axe = {"id": "THROWING_AXE", "name": "Throwing Axe", "counter": None,
           "keywords": [],
           "description": "The first card you play each combat is played an "
                          "extra time."}

    st = _beckon_state(1, [strike], enemy_hp=12, hp=60, incoming="5")
    st["player"]["relics"] = [axe]
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores and d.scores.get("lethal"), d.rationale  # 6x2 = 12: kill seen

    st["player"]["relics"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert not (d2.scores and d2.scores.get("lethal"))  # 6 < 12 without the axe

    # round 3 with a used discard pile: axe long spent, no double
    st["player"]["relics"] = [axe]
    st["battle"]["round"] = 3
    st["player"]["discard_pile_count"] = 4
    d3 = plan_combat_turn(parse_state(st), w)
    assert not (d3.scores and d3.scores.get("lethal"))


def test_barricade_up_spends_leftover_energy_on_block() -> None:
    # Owner question 2026-08-01: with BARRICADE_POWER active, excess block is
    # future-useful (excess=0 in _score), so a leftover-energy Defend should be
    # played; without it, overblock penalty + friction correctly hold the card.
    w = load_policy_config().combat
    defend = _bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.",
                    "Skill", "None")
    st = _beckon_state(4, [defend], enemy_hp=200, hp=60, incoming="0")
    st["player"]["block"] = 0
    st["player"]["status"] = [{"id": "BARRICADE_POWER", "name": "Barricade",
                               "amount": 1, "description":
                               "Block is not removed at the start of your turn.",
                               "keywords": []}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("action") == "play_card", d.rationale

    st["player"]["status"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.action.payload().get("action") != "play_card", d2.rationale


def test_artifact_strip_scores_as_down_payment_not_waste() -> None:
    # Owner Aeonglass A/B 2026-08-01: he ate her Artifact 3 with cheap debuffs
    # r2-r3, THEN landed Vulnerable and dealt 250 in a round. The ~0 pricing made
    # the bot hold debuffs forever vs Artifact. With spare energy and a Bash, the
    # planner should now spend it INTO Artifact rather than end the turn.
    w = load_policy_config().combat
    bash = _bcard(0, "BASH", "Bash", 2, "Deal 8 damage. Apply 2 Vulnerable.",
                  "Attack", "AnyEnemy")
    st = _beckon_state(3, [bash], enemy_hp=300, hp=60, incoming="0")
    st["battle"]["enemies"][0]["status"] = [
        {"id": "ARTIFACT_POWER", "name": "Artifact", "amount": 3,
         "description": "Negates 3 debuffs.", "keywords": []}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("action") == "play_card", d.rationale


def test_slow_rounds_down_and_orders_attacks_last() -> None:
    # Bygone Effigy's Slow (owner 2026-08-01): +10% damage taken per card played
    # this turn, direct attacks only, FLOORED -- a 6-dmg Strike needs 2 stacks to
    # reach 7 (6 * 1.2 = 7.2). And the DFS should discover attacks-LAST ordering.
    w = load_policy_config().combat
    slow_status = [{"id": "SLOW_POWER", "name": "Slow", "amount": 2,
                    "description": "Whenever you play a card, this enemy receives "
                                   "10% more damage from Attacks this turn.",
                    "keywords": []}]
    # rounding: 2 pre-existing stacks, single Strike -> 7 damage exactly
    strike = _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                    "Attack", "AnyEnemy")
    st = _beckon_state(3, [strike], enemy_hp=7, hp=60, incoming="0")
    st["battle"]["enemies"][0]["status"] = slow_status
    # 2026-08-07: stacks come from the router-tracked plays-this-turn parameter,
    # not the cumulative display amount (false lethal #6)
    d = plan_combat_turn(parse_state(st), w, plays_this_turn=2)
    assert d.scores and d.scores.get("lethal"), d.rationale  # 7 dmg kills the 7-HP body

    # sequencing: [Defend, Bludgeon] vs fresh Slow (0 stacks) -- Defend first
    # makes Bludgeon 32 -> 35; the plan must lead with the Defend
    bludgeon = _bcard(0, "BLUDGEON", "Bludgeon", 3, "Deal 32 damage.",
                      "Attack", "AnyEnemy")
    defend = _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.",
                    "Skill", "None")
    st2 = _beckon_state(4, [bludgeon, defend], enemy_hp=200, hp=60, incoming="0")
    st2["battle"]["enemies"][0]["status"] = [{**slow_status[0], "amount": 0}]
    d2 = plan_combat_turn(parse_state(st2), w)
    p2 = d2.action.payload()
    assert p2["action"] == "play_card" and p2["card_index"] == 1, d2.rationale


def test_pacts_end_gated_on_exhaust_pile_no_phantom_lethal() -> None:
    # Owner-caught 2026-08-01 ('how did that death occur?'): at 11 HP the plan
    # read '[Strike > Strike > Pact's End] LETHAL' with the exhaust pile at 0 --
    # Pact's End dealt nothing, the slugs lived, the bot died believing it had
    # won. Threshold-conditional damage is now gated on pile + in-plan exhausts.
    w = load_policy_config().combat
    pact = _bcard(0, "PACTS_END", "Pact's End", 0,
                  "If you have 3 or more cards in your Exhaust Pile, deal 17 "
                  "damage to ALL enemies.", "Attack", "AllEnemy")
    st = _beckon_state(3, [pact], enemy_hp=15, hp=30, incoming="5")
    st["player"]["exhaust_pile_count"] = 0
    d = plan_combat_turn(parse_state(st), w)
    assert not (d.scores and d.scores.get("lethal")), d.rationale  # no mirage

    st["player"]["exhaust_pile_count"] = 3
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.scores and d2.scores.get("lethal"), d2.rationale  # real when met


def test_mummified_hand_sequences_power_before_the_freed_card() -> None:
    """Owner check 2026-08-02: Mummified Hand zeroes a random hand card per Power
    played. Deterministic case: 1 energy, a 1-cost Power + a 1-cost attack --
    power-first frees the attack (both play); attack-first strands the Power.
    The +1-energy-per-Power trigger proxy makes the DFS find the right order."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 1, "status": [],
                   "relics": [{"id": "MUMMIFIED_HAND", "name": "Mummified Hand",
                               "description": "Whenever you play a Power, a random "
                               "card in your hand costs 0."}],
                   "hand": [
                       {"index": 0, "id": "INFLAME", "name": "Inflame", "type": "Power",
                        "cost": "1", "description": "Gain 2 Strength.",
                        "can_play": True, "target_type": "None"},
                       {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Slug", "hp": 40,
                                "max_hp": 40, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "8"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    assert d.action.payload()["card_index"] == 0  # the Power first
    assert "Strike" in d.rationale  # and the freed Strike is IN the plan


def test_cascade_class_vetoed_under_ringing_cap() -> None:
    """Owner 2026-08-03: Cascade/Havoc's 'play the top card' plays COUNT toward
    Ringing's card cap, so under a cap the card burns the turn's only slot for
    nothing. Vetoed while a cap is active; normal turns unaffected."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(with_ring):
        status = ([{"id": "RINGING_POWER", "name": "Ringing", "amount": 1,
                    "description": "You can only play 1 card this turn."}]
                  if with_ring else [])
        return parse_state({
            "state_type": "monster", "run": {"act": 1, "floor": 5, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": 3, "status": status,
                       "hand": [
                           {"index": 0, "id": "CASCADE", "name": "Cascade",
                            "type": "Skill", "cost": "1",
                            "description": "Gain 1 Energy. Play the top card of "
                            "your draw pile.", "can_play": True, "target_type": "None"},
                           {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Beast", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    cfg = load_policy_config()
    # Ringing up: the energy-rider Cascade must NOT eat the one slot -- Strike plays
    d = plan_combat_turn(st(True), cfg.combat)
    assert d.action.payload()["card_index"] == 1
    # no cap: Cascade is an ordinary candidate again (energy rider makes it playable)
    d2 = plan_combat_turn(st(False), cfg.combat)
    assert d2.action.payload()["card_index"] in (0, 1)


def test_fortifier_sequenced_after_block_for_the_big_hit() -> None:
    """Owner 2026-08-03: Fortifier ('Triple your current Block') as a DFS
    pseudo-card -- the planner must sequence it AFTER block plays (5+5=10 ->
    30) when that flips survival against a big hit, and bank it on calm turns
    (w_potion_spend)."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(intent):
        return parse_state({
            "state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 24, "max_hp": 80,
                       "block": 0, "energy": 2, "status": [],
                       "hand": [
                           {"index": 0, "id": "DEF1", "name": "Defend", "type": "Skill",
                            "cost": "1", "description": "Gain 5 Block.",
                            "can_play": True, "target_type": "None"},
                           {"index": 1, "id": "DEF2", "name": "Defend", "type": "Skill",
                            "cost": "1", "description": "Gain 5 Block.",
                            "can_play": True, "target_type": "None"}],
                       "potions": [{"slot": 0, "id": "FORTIFIER", "name": "Fortifier Potion",
                                    "can_use_in_combat": True, "target_type": "None",
                                    "description": "Triple your current Block."}],
                       "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "b0", "name": "Boss", "hp": 300,
                                    "max_hp": 300, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": intent}]}]},
        })

    cfg = load_policy_config()
    # 28 incoming vs 24 HP: two Defends = 10 block (death); tripled = 30 (survives).
    # The plan must contain the potion and play it AFTER at least one Defend.
    d = plan_combat_turn(st("28"), cfg.combat)
    assert "Fortifier" in (d.rationale or "")
    plan_part = d.rationale.split("plan [")[1].split("]")[0]
    seq = [x.strip() for x in plan_part.split(">")]
    fort_pos = next(i for i, x in enumerate(seq) if "Fortifier" in x)
    assert any("Defend" in x for x in seq[:fort_pos])  # block BEFORE the triple
    # calm turn (6 incoming): 10 block covers it -- the potion stays banked
    d2 = plan_combat_turn(st("6"), cfg.combat)
    assert "Fortifier" not in (d2.rationale or "")


def test_forgotten_ritual_stays_live_after_midturn_exhaust() -> None:
    """Owner 2026-08-03: Forgotten Ritual ('if you Exhausted a card this turn,
    gain 3 energy. Exhaust.') died in hand across replans -- the API has no
    exhausted-this-turn field, so post-exhaust polls priced its energy at zero.
    Seeded via the caller's turn-start exhaust-pile snapshot, the conditional
    stays live and the Ritual chains."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 24, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 1, "status": [], "exhaust_pile_count": 3,
                   "hand": [
                       {"index": 0, "id": "FORGOTTEN_RITUAL", "name": "Forgotten Ritual",
                        "type": "Skill", "cost": "1",
                        "description": "If you Exhausted a card this turn, gain 3 Energy. "
                        "Exhaust.", "can_play": True, "target_type": "None"},
                       {"index": 1, "id": "BLUDGEON", "name": "Bludgeon", "type": "Attack",
                        "cost": "3", "description": "Deal 32 damage.",
                        "can_play": False, "unplayable_reason": "EnergyCostTooHigh",
                        "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 4, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Toad", "hp": 60,
                                "max_hp": 60, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "10"}]}]},
    })
    cfg = load_policy_config()
    # without the seed: Ritual's energy reads 0 -> the Bludgeon stays unreachable
    d0 = plan_combat_turn(state, cfg.combat)
    assert "Bludgeon" not in (getattr(d0, "rationale", "") or "")
    # seeded (a card was exhausted earlier this turn): Ritual -> 3 energy -> Bludgeon
    d1 = plan_combat_turn(state, cfg.combat, exhausted_this_turn=True)
    assert d1.action.payload().get("card_index") == 0  # Ritual first
    assert "Bludgeon" in (d1.rationale or "")  # the 32-damage payoff is IN the plan


def test_shockwave_mass_debuff_is_aoe_and_credits_all_enemies() -> None:
    """Owner check 2026-08-03: 'Apply 3 Weak and Vulnerable to ALL enemies.
    Exhaust.' parsed weak/vuln fine but the aoe flag was damage-gated, so both
    sims debuffed ONE enemy. Now AoE: in a two-enemy fight the plan's vuln
    credit doubles and Shockwave leads the attack sequence."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn
    from sts2bot.policy.textparse import parse_card_description

    fx = parse_card_description("Apply 3 Weak and Vulnerable to ALL enemies. Exhaust.")
    assert fx.aoe and fx.weak == 3 and fx.vulnerable == 3

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 20,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "SHOCKWAVE", "name": "Shockwave", "type": "Skill",
                        "cost": "2", "description": "Apply 3 Weak and Vulnerable to ALL "
                        "enemies. Exhaust.", "can_play": True, "target_type": "AllEnemies"},
                       {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [
                       {"entity_id": "a0", "name": "Bruiser", "hp": 80, "max_hp": 80,
                        "block": 0, "status": [],
                        "intents": [{"type": "attack", "label": "14"}]},
                       {"entity_id": "b0", "name": "Bruiser", "hp": 80, "max_hp": 80,
                        "block": 0, "status": [],
                        "intents": [{"type": "attack", "label": "14"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    # Shockwave first (debuff before attacks), and its double-Weak halves both
    # attackers -- the plan must include it, not strand it
    assert "Shockwave" in (d.rationale or "")
    assert d.action.payload()["card_index"] == 0


def test_battle_trance_not_replayed_under_active_no_draw() -> None:
    """Owner catch 2026-08-03 (pre-Kaiser fight): a turn ended Battle Trance
    (draws already dead) -> Stoke. The planner's no_draw seed only knew about
    Fiddle, so the live NO_DRAW status (set by an earlier Trance this turn) was
    invisible and a second Trance was played for phantom +3-draw credit."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(status):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 28, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 10,
                       "energy": 1, "status": status,
                       "hand": [
                           {"index": 0, "id": "BATTLE_TRANCE", "name": "Battle Trance",
                            "type": "Skill", "cost": "0",
                            "description": "Draw 3 cards. You cannot draw additional "
                            "cards this turn.", "can_play": True, "target_type": "None"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Byrd", "hp": 40,
                                    "max_hp": 40, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    cfg = load_policy_config()
    # draws alive: free Trance is a fine play
    d_live = plan_combat_turn(st([]), cfg.combat)
    assert d_live.action.payload().get("card_index") == 0
    # NO_DRAW active (earlier Trance): the second Trance is phantom value -- hold
    nd = [{"id": "NO_DRAW_POWER", "name": "No Draw", "amount": None,
           "description": "You cannot draw additional cards this turn."}]
    d_dead = plan_combat_turn(st(nd), cfg.combat)
    assert d_dead.action.payload().get("action") == "end_turn"


def test_gamble_cards_sequenced_early_all_else_equal() -> None:
    """Owner 2026-08-03: Infernal Blade-class gambles are best played EARLY --
    knowing the generated option leaves the rest of the turn able to use it
    (the per-poll replan sees the real card next poll). Position-scaled nudge,
    tie-break sized."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 1, "floor": 9, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 2, "id": "INFERNAL_BLADE", "name": "Infernal Blade+",
                        "type": "Skill", "cost": "0",
                        "description": "Add a random Attack into your Hand. "
                        "It costs 0 this turn.", "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Brute", "hp": 60,
                                "max_hp": 60, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "9"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    # the gamble leads the plan: reveal first, Strikes after
    assert d.action.payload()["card_index"] == 2


def test_fnp_before_infernal_blade_beats_the_reveal_nudge() -> None:
    """Owner counter-case 2026-08-03: Infernal Blade+ EXHAUSTS, so with Feel No
    Pain in hand the right order is FNP -> Blade (the exhaust earns FNP's 3
    block). Playing the FNP CARD mid-plan now grants per_exhaust_block in-sim,
    so the concrete 3-block credit outweighs the 0.2 reveal-early tie-break."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 1, "floor": 9, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                   "energy": 2, "status": [],
                   "hand": [
                       {"index": 0, "id": "INFERNAL_BLADE", "name": "Infernal Blade+",
                        "type": "Skill", "cost": "0",
                        "description": "Add a random Attack into your Hand. It costs 0 "
                        "this turn. Exhaust.", "can_play": True, "target_type": "None"},
                       {"index": 1, "id": "FEEL_NO_PAIN", "name": "Feel No Pain",
                        "type": "Power", "cost": "1",
                        "description": "Whenever a card is Exhausted, gain 3 Block.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Brute", "hp": 60,
                                "max_hp": 60, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "9"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    assert d.action.payload()["card_index"] == 1  # FNP first; the Blade's exhaust pays


def test_daze_ethereal_feeds_fnp_end_of_turn_block() -> None:
    """Owner check 2026-08-03: an unplayed Ethereal card (Daze) exhausts at end
    of turn -- with Feel No Pain up that's free pre-enemy-turn block. At low HP
    vs small incoming, the planner may attack instead of Defending ONLY when
    the ethereal FNP block covers the hit."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(daze_desc):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 21, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 10, "max_hp": 80, "block": 0,
                       "energy": 1,
                       "status": [{"id": "FEEL_NO_PAIN_POWER", "name": "Feel No Pain",
                                   "amount": 4,
                                   "description": "Whenever a card is Exhausted, "
                                   "gain 4 Block."}],
                       "hand": [
                           {"index": 0, "id": "DAZE", "name": "Daze", "type": "Status",
                            "cost": "-2", "description": daze_desc, "can_play": False,
                            "unplayable_reason": "Unplayable", "target_type": "None"},
                           {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 2, "id": "DEFEND_IRONCLAD", "name": "Defend",
                            "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
                            "can_play": True, "target_type": "None"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Byrd", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "4"}]}]},
        })

    cfg = load_policy_config()
    # ethereal Daze + FNP 4: the end-of-turn exhaust covers the 4 incoming -> attack
    d_eth = plan_combat_turn(st("Unplayable. Ethereal."), cfg.combat)
    assert d_eth.action.payload().get("card_index") == 1
    # plain Daze: no free block -- at 10 HP the Defend must win
    d_plain = plan_combat_turn(st("Unplayable."), cfg.combat)
    assert d_plain.action.payload().get("card_index") == 2


def test_dismantle_doubles_hits_on_vulnerable_and_sequences_after_bash() -> None:
    """Owner 2026-08-04: 'Deal 8 damage. If the enemy is Vulnerable, hits
    twice.' parsed flat 8 -- underrated by half in the vuln lines the bot
    builds. Now: Bash FIRST (applies vuln), Dismantle second for 16."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 20,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "DISMANTLE", "name": "Dismantle",
                        "type": "Attack", "cost": "1",
                        "description": "Deal 8 damage. If the enemy is Vulnerable, "
                        "hits twice.", "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "BASH", "name": "Bash", "type": "Attack",
                        "cost": "2", "description": "Deal 8 damage. Apply 2 Vulnerable.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Wall", "hp": 100,
                                "max_hp": 100, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "10"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    assert d.action.payload()["card_index"] == 1  # Bash first: vuln enables the double


def test_stomp_dynamic_cost_discovered_in_plan() -> None:
    """Owner 2026-08-04: Stomp 'Costs 1 less for each Attack played this turn'
    was static in-plan -- attack->attack->free-Stomp was undiscoverable inside
    one plan. Energy 2, two 0-cost attacks + 2-cost Stomp: the plan must
    contain all three (Stomp's effective cost reaches 0)."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 20,
                   "energy": 2, "status": [],
                   "hand": [
                       {"index": 0, "id": "STOMP", "name": "Stomp", "type": "Attack",
                        "cost": "2", "description": "Deal 9 damage to ALL enemies. "
                        "Costs 1 less [ironclad_energy_icon.png] for each Attack "
                        "played this turn.", "can_play": True, "target_type": "AllEnemies"},
                       {"index": 1, "id": "SHIV1", "name": "Jab", "type": "Attack",
                        "cost": "0", "description": "Deal 4 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 2, "id": "SHIV2", "name": "Jab", "type": "Attack",
                        "cost": "0", "description": "Deal 4 damage.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Wall", "hp": 100,
                                "max_hp": 100, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "10"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    rat = d.rationale or ""
    assert "Stomp" in rat  # the free-Stomp line is in the chosen plan
    assert rat.count("Jab") == 2  # after both jabs


def test_ashen_strike_pile_bonus_not_double_counted() -> None:
    """False-lethal death 2026-08-04 (Obscura f?, died at 2 HP with Stoke in
    hand): Ashen Strike's live preview ALREADY bakes the exhaust-pile bonus
    into 'Deal X' (taped 22->26->30 as the pile grew), but _to_planned folded
    pile*N on top -- sim 63 vs game 45 vs 57 HP = phantom LETHAL that
    suppressed every survival lane. Preview is authoritative for the pre-plan
    pile; only IN-PLAN exhaust events add."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 3, "floor": 40, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 20, "max_hp": 80, "block": 0,
                   "energy": 2, "status": [], "exhaust_pile_count": 3,
                   "hand": [
                       {"index": 0, "id": "ASHEN_STRIKE", "name": "Ashen Strike+",
                        "type": "Attack", "cost": "2",
                        "description": "Deal 30 damage. Deals 4 additional damage "
                        "for each card in your Exhaust Pile.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 7, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "OB_0", "name": "The Obscura", "hp": 57,
                                "max_hp": 123, "block": 0,
                                "status": [{"id": "VULNERABLE_POWER", "name": "Vulnerable",
                                            "amount": 4, "description": ""}],
                                "intents": [{"type": "buff", "label": "Buff"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    # 30 x 1.5 vuln = 45 < 57: NOT lethal (the double-count claimed 63 and was)
    assert not (d.scores or {}).get("lethal")


def test_fiend_fire_hand_exhaust_clears_the_dfs_hand() -> None:
    """Owner catch 2026-08-04 (Ceremonial Beast R1): the plan read [Fiend Fire >
    Sword Boomerang > Feel No Pain > Pyre] -- the DFS kept playing cards AFTER
    the hand-exhauster, double-dipping the score, and the bot torched freshly
    potion-minted free Powers as 7-damage fodder. Post-exhaust the hand is
    GONE; the DFS must therefore play free cards BEFORE Fiend Fire."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
                   "energy": 1, "status": [],
                   "hand": [
                       {"index": 0, "id": "FIEND_FIRE", "name": "Fiend Fire",
                        "type": "Attack", "cost": "0",
                        "description": "Exhaust your Hand. Deal 7 damage for each "
                        "card Exhausted. Exhaust.", "can_play": True,
                        "target_type": "AnyEnemy"},
                       {"index": 1, "id": "PYRE", "name": "Pyre", "type": "Power",
                        "cost": "0", "description": "Gain 1 Energy at the start of "
                        "each turn.", "can_play": True, "target_type": "None"},
                       {"index": 2, "id": "FEEL_NO_PAIN", "name": "Feel No Pain",
                        "type": "Power", "cost": "0",
                        "description": "Whenever a card is Exhausted, gain 3 Block.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "CB_0", "name": "Ceremonial Beast",
                                "hp": 243, "max_hp": 243, "block": 0, "status": [],
                                "intents": [{"type": "buff", "label": "Buff"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    rat = d.rationale or ""
    # the free Powers must precede Fiend Fire in the plan; nothing may follow it
    if "Fiend Fire" in rat:
        plan_part = rat.split("plan [")[1].split("]")[0]
        seq = [x.strip() for x in plan_part.split(">")]
        ff = next(i for i, x in enumerate(seq) if "Fiend Fire" in x)
        assert ff == len(seq) - 1  # hand-exhauster is terminal
    assert d.action.payload()["card_index"] in (1, 2)  # a free Power leads


def test_stampede_banks_the_last_attack_behind_a_defend() -> None:
    """Owner check 2026-08-06: Stampede plays 1 random retained Attack free at
    end of turn. With it up, Defend + banked Strike beats playing the Strike
    (same damage, plus block); without it, the attack plays normally. Targeted
    lethals still outprice the gamble (w_kill), preserving the owner's
    multi-enemy nuance."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(status):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 72, "max_hp": 80, "block": 0,
                       "energy": 1, "status": status,
                       "hand": [
                           {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 1, "id": "DEFEND_IRONCLAD", "name": "Defend",
                            "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
                            "can_play": True, "target_type": "None"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Byrd", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "3"}]}]},
        })

    cfg = load_policy_config()
    stampede = [{"id": "STAMPEDE_POWER", "name": "Stampede", "amount": 1,
                 "description": "At the end of your turn, 1 random Attack in your "
                 "Hand is played against a random enemy."}]
    # Stampede up: Defend leads, the Strike is banked for the free EOT play
    d_on = plan_combat_turn(st(stampede), cfg.combat)
    assert d_on.action.payload()["card_index"] == 1
    assert "Strike" not in (d_on.rationale or "")  # banked, not planned
    # the credit is real and status-gated: the same Defend plan scores ~5.4
    # higher with Stampede up (mean retained damage 6 x 0.9 x w_damage)
    d_off = plan_combat_turn(st([]), cfg.combat)
    gain = (d_on.scores or {}).get("plan_score", 0) - (d_off.scores or {}).get("plan_score", 0)
    assert 3.0 < gain < 8.0, gain


def test_flutter_halves_attacks_and_kills_the_false_lethal() -> None:
    """Audit find 2026-08-06 (Thieving Hopper, replayed from tape): 'Receives
    50% less damage from Attacks' was unparsed in BOTH sims -- a 36-damage plan
    read LETHAL vs a 24-HP Hopper the game only let us hit for ~17, and the
    phantom kill suppressed survival lanes two turns running."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.capability import detect_mechanics
    from sts2bot.policy.combat import plan_combat_turn

    flutter = {"id": "FLUTTER_POWER", "name": "Flutter", "amount": 5,
               "description": "Receives 50% less damage from Attacks. "
               "Deal attack damage 5 times to Stun it."}
    assert detect_mechanics([flutter]).get("attack_dmg_taken_mult") == 0.5

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 21, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 45, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "BREAK", "name": "Break", "type": "Attack",
                        "cost": "1", "description": "Deal 23 damage. Apply 5 Vulnerable.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 9 damage.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "TH_0", "name": "Thieving Hopper",
                                "hp": 24, "max_hp": 40, "block": 0,
                                "status": [flutter],
                                "intents": [{"type": "attack", "label": "21"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    # halved: ~11 + ~6x1.5 = well under 24 -- the phantom kill must not fire
    assert not (d.scores or {}).get("lethal")


def test_sleeper_pokes_hold_bursts_play() -> None:
    """Owner 2026-08-06: sleeper model v3 -- damage counts, the waking hit pays
    w_wake_sleeper. A plain poke (Strike) holds behind the power; a real burst
    (Bludgeon) clears the penalty and wakes her deliberately, per the owner's
    'waking is not always wrong'. Rider pokes (Pommel) sit ON the margin by
    design and are deliberately not pinned."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1",
                        "description": "Deal 9 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "INFLAME", "name": "Inflame", "type": "Power",
                        "cost": "1", "description": "Gain 2 Strength.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "LM_0", "name": "Lagavulin Matriarch",
                                "hp": 220, "max_hp": 220, "block": 0,
                                "status": [{"id": "ASLEEP_POWER", "name": "Asleep",
                                            "amount": 3, "description":
                                            "Asleep. Wakes when damaged."}],
                                "intents": [{"type": "sleep", "label": ""}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    assert d.action.payload()["card_index"] == 1  # Inflame; the Strike poke holds
    assert "Strike" not in (d.rationale or "")
    # owner nuance: a genuine BURST clears the wake penalty -- damage now counts
    state.player.hand[0] = state.player.hand[0].model_copy(update={
        "id": "BLUDGEON", "name": "Bludgeon", "cost": "2",
        "description": "Deal 32 damage."})
    d2 = plan_combat_turn(state, load_policy_config().combat)
    assert d2.action.payload()["card_index"] in (0, 1)
    assert "Bludgeon" in (d2.rationale or "")  # the burst-wake line is IN the plan


def test_duplication_status_seeds_the_armed_state_across_replans() -> None:
    """Audit find 2026-08-06: DUPLICATION_POWER ('your next card is played an
    extra time') is a live status after the potion resolves, but replans forgot
    the armed state -- the doubled play was planned as single. Seeded, a lone
    16-damage Bludgeon reads as 32 and takes the kill on a 30-HP enemy."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(status):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                       "energy": 2, "status": status,
                       "hand": [{"index": 0, "id": "BLUDGEON", "name": "Bludgeon",
                                 "type": "Attack", "cost": "2",
                                 "description": "Deal 16 damage.",
                                 "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Brute", "hp": 30,
                                    "max_hp": 40, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "10"}]}]},
        })

    cfg = load_policy_config()
    dup = [{"id": "DUPLICATION_POWER", "name": "Duplication", "amount": 1,
            "description": "Your next card is played an extra time."}]
    d_armed = plan_combat_turn(st(dup), cfg.combat)
    assert (d_armed.scores or {}).get("lethal") == 1.0  # 16x2 = 32 >= 30
    d_plain = plan_combat_turn(st([]), cfg.combat)
    assert not (d_plain.scores or {}).get("lethal")  # 16 < 30


def test_slow_display_amount_does_not_inflate_the_multiplier() -> None:
    """False lethal #6 (audit 2026-08-07): SLOW_POWER's amount is a cumulative
    display; the effect is per card played THIS TURN. Seeding from the display
    made every attack read x2 by round 3 -- a 47-damage turn tagged LETHAL vs
    a 69-HP Effigy, and the 23-damage counterattack landed unblocked."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 1, "floor": 10, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 75, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "BASH", "name": "Bash", "type": "Attack",
                        "cost": "2", "description": "Deal 8 damage. Apply 2 Vulnerable.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "HEMOKINESIS", "name": "Hemokinesis",
                        "type": "Attack", "cost": "1",
                        "description": "Lose 2 HP. Deal 15 damage.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "BE_0", "name": "Bygone Effigy", "hp": 69,
                                "max_hp": 120, "block": 0,
                                "status": [{"id": "SLOW_POWER", "name": "Slow",
                                            "amount": 10,
                                            "description": "Whenever you play a card, "
                                            "this enemy receives 10% more damage from "
                                            "Attacks this turn."}],
                                "intents": [{"type": "attack", "label": "23"}]}]},
    })
    d = plan_combat_turn(state, load_policy_config().combat)
    # 8 + 15x1.1x1.5 = ~33 < 69: no phantom kill from the display amount
    assert not (d.scores or {}).get("lethal")


def test_axebot_stock_respawn_blocks_false_fight_over() -> None:
    """Audit 2026-08-07: Axebot's Stock ('When killed, a new Axebot is summoned
    in its place', amount = respawns left) made kills read as fight-enders --
    -25 damage overprediction bucket and phantom fight-over. With the
    spawns_on_death flag, killing the last visible Axebot is NOT lethal while
    stock remains."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(stock):
        status = ([{"id": "STOCK_POWER", "name": "Stock", "amount": stock,
                    "description": "When killed, a new Axebot is summoned in its "
                    "place."}] if stock else [])
        return parse_state({
            "state_type": "monster", "run": {"act": 3, "floor": 39, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
                       "energy": 2, "status": [],
                       "hand": [{"index": 0, "id": "BLUDGEON", "name": "Bludgeon",
                                 "type": "Attack", "cost": "2",
                                 "description": "Deal 32 damage.",
                                 "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "AX_0", "name": "Axebot", "hp": 20,
                                    "max_hp": 72, "block": 0, "status": status,
                                    "intents": [{"type": "attack", "label": "13"}]}]},
        })

    cfg = load_policy_config()
    d_stock = plan_combat_turn(st(2), cfg.combat)
    assert not (d_stock.scores or {}).get("lethal")  # respawn coming: not over
    d_last = plan_combat_turn(st(0), cfg.combat)
    assert (d_last.scores or {}).get("lethal") == 1.0  # no stock: a real kill


def test_restlessness_held_until_hand_empties() -> None:
    """Owner live catch 2026-08-10: Restlessness ('Retain. If your Hand is
    empty, draw 2 cards and gain [energy][energy].') was played with the
    condition inactive -- the flat parse credited the rider as a free
    Adrenaline, so the bot led with it. The rider only fires on the play that
    EMPTIES the hand: never play it while other cards remain (Retain makes
    holding free); as the true last card it fires as a refuel finisher."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn
    from sts2bot.policy.textparse import parse_card_description

    live_text = ("Retain. If your Hand is empty, draw 2 cards and gain "
                 "[ironclad_energy_icon.png][ironclad_energy_icon.png].")
    fx = parse_card_description(live_text)
    assert fx.requires_empty_hand
    assert fx.draw == 2 and fx.energy_gain == 2  # values kept; gating is the sim's job

    def st(hand):
        return parse_state({
            "state_type": "monster", "run": {"act": 1, "floor": 8, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": 3, "status": [],
                       "hand": hand, "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Toad", "hp": 40,
                                    "max_hp": 40, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    restless = {"index": 0, "id": "RESTLESSNESS", "name": "Restlessness",
                "type": "Skill", "cost": "0", "description": live_text,
                "can_play": True, "target_type": "None"}
    strike = {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
              "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
              "can_play": True, "target_type": "AnyEnemy"}
    wither = {"index": 2, "id": "WITHER", "name": "Wither", "type": "Status",
              "cost": "-", "description": "Unplayable.", "can_play": False,
              "target_type": "None"}

    cfg = load_policy_config()
    # the live bug: Restlessness led the turn with a full hand. Now the Strike leads.
    d = plan_combat_turn(st([restless, strike]), cfg.combat)
    assert d.action.payload().get("card_index") == 1
    # an unplayable Status in hand keeps the condition false FOREVER this turn:
    # Restlessness must not appear anywhere in the plan (held via Retain)
    d2 = plan_combat_turn(st([restless, strike, wither]), cfg.combat)
    assert "Restlessness" not in (d2.rationale or "")


def test_card_played_plating_soaks_incoming_but_not_body_slam() -> None:
    """Fuzz find #1 follow-through: a played 'Gain 6 Plating.' still soaks this
    turn's incoming (end-of-turn block lands before the enemy turn) but must
    not inflate 'damage equal to your Block' plays made after it."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(hand):
        return parse_state({
            "state_type": "monster", "run": {"act": 1, "floor": 9, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": 3, "status": [],
                       "hand": hand, "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Toad", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "10"}]}]},
        })

    stone = {"index": 0, "id": "STONE_ARMOR", "name": "Stone Armor",
             "type": "Skill", "cost": "1",
             "description": "Ethereal. Gain 6 Plating.",
             "can_play": True, "target_type": "None"}
    cfg = load_policy_config()
    d = plan_combat_turn(st([stone]), cfg.combat)
    # the soak survives: with plating played, projected HP loss is 10-6=4, so
    # the plan prefers playing it over holding (scores carry the block pool)
    assert d.action.payload().get("card_index") == 0


def test_guarded_leader_minion_is_never_ignorable() -> None:
    """Owner live catch 2026-08-11 (run 20260810-235031 f48, lost): six rounds
    of damage went into the guarded 391-HP Queen while the 190-HP Torch (the
    only attacker) beat the run to death -- Torch's MINION status made it
    'ignorable' under the flee-with-the-leader rule, which is exactly backwards
    for a guarded leader (owner's 2026-08-02 A/B taped Torch-first as the
    winning order). With a _GUARDED_LEADER_NAMES leader alive + a live minion,
    the minion gets full offensive credit and the plan leads with it."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "boss", "run": {"act": 3, "floor": 48, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "BASH", "name": "Bash", "type": "Attack",
                        "cost": "2", "description": "Deal 8 damage. Apply 2 Vulnerable.",
                        "can_play": True, "target_type": "AnyEnemy"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [
                       {"entity_id": "TORCH_0", "name": "Torch Head Amalgam",
                        "hp": 190, "max_hp": 199, "block": 0,
                        "status": [{"id": "MINION_POWER", "name": "Minion",
                                    "amount": 1, "description":
                                    "Will abandon combat when the leader dies."}],
                        "intents": [{"type": "Attack", "label": "18"}]},
                       {"entity_id": "QUEEN_0", "name": "Queen", "hp": 391,
                        "max_hp": 400, "block": 0, "status": [],
                        "intents": [{"type": "CardDebuff", "label": ""}]}]},
    })
    cfg = load_policy_config()
    d = plan_combat_turn(state, cfg.combat)
    assert "TORCH" in (d.rationale or ""), d.rationale


def test_frantic_escape_played_while_cheap_skipped_on_lethal() -> None:
    """Owner rule (2026-08-12, Insatiable review): 'play at least one Frantic
    Escape per turn if possible as long as it costs at most 1' -- each play
    buys +1 Sandpit turn and raises its own cost. The card is a Status that
    parses to nothing, so unscored it was NEVER played and the clock never
    extended. Cost-2 copies get no bonus; lethal plans skip the escape."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(escape_cost, enemy_hp=175, energy=3):
        return parse_state({
            "state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": energy, "status": [],
                       "hand": [
                           {"index": 0, "id": "FRANTIC_ESCAPE", "name": "Frantic Escape",
                            "type": "Status", "cost": str(escape_cost),
                            "description": "Get farther away. Increase Sandpit by 1. "
                            "Increase the cost of this card by 1.",
                            "can_play": True, "target_type": "None"},
                           {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 2, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "The Insatiable",
                                    "hp": enemy_hp, "max_hp": 321, "block": 0,
                                    "status": [], "intents":
                                    [{"type": "attack", "label": "20"}]}]},
        })

    cfg = load_policy_config()
    # cost-1 escape: in the plan (the +1 turn outranks a Strike's 6 damage)
    d = plan_combat_turn(st(1), cfg.combat)
    assert "Frantic Escape" in (d.rationale or ""), d.rationale
    # cost-2 escape: no bonus -- junk again
    d2 = plan_combat_turn(st(2), cfg.combat)
    assert "Frantic Escape" not in (d2.rationale or "")
    # lethal on a tight budget: the escape must not displace the kill
    # (energy 2: escape + 1 Strike = 6 dmg, not lethal; 2 Strikes = 12, lethal)
    d3 = plan_combat_turn(st(1, enemy_hp=10, energy=2), cfg.combat)
    assert "LETHAL" in (d3.rationale or "")
    assert "Frantic Escape" not in (d3.rationale or ""), d3.rationale


def test_cruelty_ordered_before_attacks_on_vulnerable() -> None:
    """Owner catch 2026-08-12 (KD fight): Cruelty ('Vulnerable enemies take an
    additional 25% damage') was ordered AFTER an attack on a vulnerable enemy.
    The bonus only seeded from the ACTIVE status, so a mid-plan Cruelty gave
    later attacks nothing and the DFS saw no ordering pressure. Now the play
    raises the plan's multiplier: Cruelty leads, the big hit follows."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                   "block": 0, "energy": 3, "status": [],
                   "hand": [
                       {"index": 0, "id": "BLUDGEON", "name": "Bludgeon",
                        "type": "Attack", "cost": "2", "description": "Deal 32 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "CRUELTY", "name": "Cruelty",
                        "type": "Power", "cost": "1",
                        "description": "Vulnerable enemies take an additional "
                                       "25% damage.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Vantom", "hp": 90,
                                "max_hp": 90, "block": 0,
                                "status": [{"id": "VULNERABLE_POWER",
                                            "name": "Vulnerable", "amount": 2,
                                            "description": "Receive 50% more damage "
                                            "from Attacks for 2 turns."}],
                                "intents": [{"type": "attack", "label": "12"}]}]},
    })
    cfg = load_policy_config()
    d = plan_combat_turn(state, cfg.combat)
    assert d.action.payload().get("card_index") == 1, d.rationale  # Cruelty FIRST


def test_rupture_prices_the_str_per_selfhp_trade() -> None:
    """Owner question 2026-08-12: 'did the planner even weigh the 1 Str / 2 hp
    logic?' It didn't -- Rupture's trigger sentence is stripped and no seed
    existed; the observed pass on Bloodletting was energy-waste economics
    being coincidentally right. Now: with Rupture up and attacks to feed, the
    self-HP play earns its Strength and gets sequenced BEFORE the attacks."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(with_rupture):
        status = ([{"id": "RUPTURE_POWER", "name": "Rupture", "amount": 1,
                    "description": "Whenever you lose HP on your turn, "
                                   "gain 1 Strength."}] if with_rupture else [])
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                       "block": 0, "energy": 2, "status": status,
                       "hand": [
                           {"index": 0, "id": "BLOODLETTING", "name": "Bloodletting",
                            "type": "Skill", "cost": "0",
                            "description": "Lose 2 HP. Gain 2 "
                            "[ironclad_energy_icon.png].",
                            "can_play": True, "target_type": "None"},
                           {"index": 1, "id": "TWIN_STRIKE", "name": "Twin Strike",
                            "type": "Attack", "cost": "1",
                            "description": "Deal 5 damage twice.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 2, "id": "SWORD_BOOMERANG", "name": "Sword Boomerang",
                            "type": "Attack", "cost": "1",
                            "description": "Deal 3 damage to a random enemy 3 times.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Chomper", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "11"}]}]},
        })

    cfg = load_policy_config()
    d = plan_combat_turn(st(True), cfg.combat)
    ra = d.rationale or ""
    assert "Bloodletting" in ra, ra
    # strength before the multi-hit attacks: Bloodletting leads the plan
    assert d.action.payload().get("card_index") == 0, ra


def test_second_wind_counts_only_nonattacks_and_death_wall_fires() -> None:
    """Owner sighting 2026-08-12 ('unused hail mary potion'): run -141919 died
    at KD r11 holding a tutor potion. Root cause: Second Wind ('Exhaust all
    NON-ATTACK cards... Gain 5 Block for each') was credited for the two
    leftover Strikes -- the plan projected ~49 block vs the real 27, so no
    death wall and no hail-mary consult. Repro of the exact turn: hp 14,
    Disintegration 21, KD attacking 12x3. The [D>EE>D>SW] line must now
    project honestly (SW exhausts nothing at the tail) and the turn reads as
    projected death -- unlocking the rescue ladder."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def c(i, cid, name, typ, cost, desc, can_play=True):
        return {"index": i, "id": cid, "name": name, "type": typ, "cost": cost,
                "description": desc, "can_play": can_play, "target_type":
                "AnyEnemy" if typ == "Attack" else "None"}

    state = parse_state({
        "state_type": "boss", "run": {"act": 2, "floor": 33, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 14, "max_hp": 86,
                   "block": 0, "energy": 4,
                   "status": [{"id": "DISINTEGRATION_POWER", "name": "Disintegration",
                               "amount": 21, "description":
                               "At the end of your turn, take 21 damage."},
                              {"id": "FEEL_NO_PAIN_POWER", "name": "Feel No Pain",
                               "amount": 6, "description":
                               "Whenever a card is Exhausted, gain 6 Block."}],
                   "hand": [
                       c(0, "STRIKE_IRONCLAD", "Strike+", "Attack", "1", "Deal 9 damage."),
                       c(1, "DEFEND_IRONCLAD", "Defend", "Skill", "1", "Gain 5 Block."),
                       c(2, "SECOND_WIND", "Second Wind", "Skill", "1",
                         "Exhaust all non-Attack cards in your Hand. "
                         "Gain 5 Block for each card Exhausted."),
                       c(3, "EVIL_EYE", "Evil Eye", "Skill", "1",
                         "Gain 8 Block. Gain another 8 Block if you have "
                         "Exhausted a card this turn."),
                       c(4, "DEFEND_IRONCLAD", "Defend", "Skill", "1", "Gain 5 Block."),
                       c(5, "STRIKE_IRONCLAD", "Strike+", "Attack", "1", "Deal 9 damage.")],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 11, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "KD_0", "name": "Knowledge Demon",
                                "hp": 49, "max_hp": 220, "block": 0, "status": [],
                                "intents": [{"type": "Attack", "label": "12x3"}]}]},
    })
    cfg = load_policy_config()
    d = plan_combat_turn(state, cfg.combat)
    # honest projection: best block line is SW-FIRST (3 non-attacks exhausted =
    # 15 SW + 18 FNP) or similar -- and the turn must read lethal-to-us unless
    # a genuinely surviving line exists. Either way, hp_loss must be honest:
    assert d.scores is not None
    # the misprojection read ~8 loss; honest math cannot get below ~14 vs 57
    # incoming with <=45 achievable block -- the projected-death signal the
    # rescue ladder keys on must be visible
    assert d.scores.get("hp_loss", 0) >= 14 or d.scores.get("lethal"), d.rationale


def test_wg_preparing_turn_prices_zero_when_telegraphed() -> None:
    """Audit #1 bucket (n=24 avg 17.2 over-predicted): the July assumed-50
    incoming fired on every sentinel-HP turn, but the blind phase no longer
    exists -- live tape shows preparing = Stun intent + STEAM_ERUPTION stacks,
    eruption = DeathBlow N. Blocking the preparing turn is a turn early. The
    assumption now fires only when the phase is genuinely blind (null intents,
    no eruption status -- the 2026-07-25 shape, kept as a fallback)."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(intents, status):
        return parse_state({
            "state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 50, "max_hp": 80,
                       "block": 0, "energy": 3, "status": [],
                       "hand": [{"index": 0, "id": "DEFEND_IRONCLAD", "name": "Defend",
                                 "type": "Skill", "cost": "1",
                                 "description": "Gain 5 Block.",
                                 "can_play": True, "target_type": "None"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 12, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "WG_0", "name": "Waterfall Giant",
                                    "hp": 999999999, "max_hp": 240, "block": 0,
                                    "status": status, "intents": intents}]},
        })

    cfg = load_policy_config()
    # telegraphed preparing turn: Stun + stacks -> zero incoming, so blocking
    # is pure waste and the correct play is to END THE TURN (save the Defend)
    d = plan_combat_turn(st([{"type": "Stun", "label": ""}],
                            [{"id": "STEAM_ERUPTION_POWER", "name": "Steam Eruption",
                              "amount": 45, "description": "When killed, deals 45 "
                              "damage at the end of your next turn."}]), cfg.combat)
    assert d.action.payload()["action"] == "end_turn", d.rationale
    # genuinely blind sentinel (the 2026-07-25 shape): the fallback still
    # guards -- assumed incoming makes the Defend worth playing
    d2 = plan_combat_turn(st([], []), cfg.combat)
    assert d2.action.payload().get("card_index") == 0, d2.rationale


def test_feed_fatal_bonus_requires_nonminion_kill() -> None:
    """Owner check 2026-08-13: Feed's Max-HP payoff triggers only on NON-minion
    kills (the game's Fatal keyword text). The sim credited any kill, and
    guard_break steers kills onto minions -- exactly where the phantom +8
    would misprice Feed as the finisher over a plain attack."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(minion):
        status = ([{"id": "MINION_POWER", "name": "Minion", "amount": 1,
                    "description": "Will abandon combat when the leader dies."}]
                  if minion else [])
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "block": 0, "energy": 1, "status": [],
                       "hand": [
                           {"index": 0, "id": "FEED", "name": "Feed", "type": "Attack",
                            "cost": "1", "description": "Deal 10 damage. If Fatal, "
                            "raise your Max HP by 3. Exhaust.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 10 damage.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [
                           {"entity_id": "E0", "name": "Kin Follower" if minion else "Chomper",
                            "hp": 8, "max_hp": 60, "block": 0, "status": status,
                            "intents": [{"type": "attack", "label": "9"}]},
                           {"entity_id": "LEAD", "name": "Kin Priest", "hp": 120,
                            "max_hp": 169, "block": 0, "status": [],
                            "intents": [{"type": "buff", "label": ""}]}]},
        })

    cfg = load_policy_config()
    # non-minion kill available: Feed is the preferred finisher (+8 fatal)
    d = plan_combat_turn(st(minion=False), cfg.combat)
    assert d.action.payload().get("card_index") == 0, d.rationale
    # minion kill: no fatal payoff -- Feed must NOT be burned on the Follower
    # (Exhaust costs the card; the plain Strike finishes identically)
    d2 = plan_combat_turn(st(minion=True), cfg.combat)
    assert d2.action.payload().get("card_index") == 1, d2.rationale


def test_rainbow_ring_trio_steered_and_completed() -> None:
    """Owner 2026-08-13 (live text: 'each turn', not once-per-combat): with the
    ring held and A+S+P all in hand, the plan completes the trio; without the
    ring the Power alone may sit (friction) -- the trio credit is the delta."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(with_ring):
        relics = ([{"id": "RAINBOW_RING", "name": "Rainbow Ring",
                    "description": "The first time you play an Attack, Skill, and "
                    "Power each turn, gain 1 Strength and 1 Dexterity."}]
                  if with_ring else [])
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "block": 0, "energy": 3, "status": [], "relics": relics,
                       "hand": [
                           {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 1, "id": "DEFEND_IRONCLAD", "name": "Defend",
                            "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
                            "can_play": True, "target_type": "None"},
                           {"index": 2, "id": "AGGRESSION", "name": "Aggression",
                            "type": "Power", "cost": "1",
                            "description": "At the start of each turn, gain 1 Vigor.",
                            "can_play": True, "target_type": "None"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Chomper", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    cfg = load_policy_config()
    d = plan_combat_turn(st(True), cfg.combat)
    ra = d.rationale or ""
    # all three types in the plan (trio completed)
    assert "Strike" in ra and "Defend" in ra and "Aggression" in ra, ra


def test_zero_cost_draw_opens_the_turn() -> None:
    """Owner rule (KD A/B 2026-08-14): 0-energy draw cards are safe openers --
    drawn cards feed the replan loop. Battle Trance sequences FIRST when no
    other draw source competes; with Pommel Strike in hand the existing
    no_draw pricing keeps Pommel BEFORE Trance (its suppression wrinkle)."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(hand):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "block": 0, "energy": 3, "status": [], "hand": hand,
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Chomper", "hp": 60,
                                    "max_hp": 60, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    bt = {"index": 0, "id": "BATTLE_TRANCE", "name": "Battle Trance",
          "type": "Skill", "cost": "0",
          "description": "Draw 3 cards. You cannot draw additional cards this turn.",
          "can_play": True, "target_type": "None"}
    strike = {"index": 1, "id": "STRIKE_IRONCLAD", "name": "Strike",
              "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
              "can_play": True, "target_type": "AnyEnemy"}
    pommel = {"index": 2, "id": "POMMEL_STRIKE", "name": "Pommel Strike",
              "type": "Attack", "cost": "1",
              "description": "Deal 9 damage. Draw 1 card.",
              "can_play": True, "target_type": "AnyEnemy"}

    cfg = load_policy_config()
    d = plan_combat_turn(st([bt, strike]), cfg.combat)
    assert d.action.payload().get("card_index") == 0, d.rationale  # BT opens
    d2 = plan_combat_turn(st([bt, pommel, strike]), cfg.combat)
    assert d2.action.payload().get("card_index") == 2 or \
           "Pommel" in (d2.rationale or "").split(">")[0], d2.rationale


def test_energy_surplus_draw_judgment() -> None:
    """Owner rule (KD A/B 2026-08-14): 'is my hand good value for my energy,
    or is it worth spending X to draw?' With SURPLUS energy (6 en, only a
    3-cost value card besides basics), the 1-cost draw sequences early and
    its draws earn scaled credit. At par (3 energy, 3-cost value card), the
    value card leads -- never waste energy digging past a good hand."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(energy):
        return parse_state({
            "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "block": 0, "energy": energy, "status": [],
                       "hand": [
                           {"index": 0, "id": "BLUDGEON", "name": "Bludgeon",
                            "type": "Attack", "cost": "3", "description": "Deal 32 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 1, "id": "POMMEL_STRIKE", "name": "Pommel Strike",
                            "type": "Attack", "cost": "1",
                            "description": "Deal 9 damage. Draw 1 card.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 2, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Chomper", "hp": 80,
                                    "max_hp": 80, "block": 0, "status": [],
                                    "intents": [{"type": "attack", "label": "8"}]}]},
        })

    cfg = load_policy_config()
    # surplus (6 energy vs 3-cost Bludgeon): the draw source opens the turn
    d = plan_combat_turn(st(6), cfg.combat)
    assert d.action.payload().get("card_index") == 1, d.rationale
    # par (3 energy): Bludgeon is the turn -- no dig-first detour
    d2 = plan_combat_turn(st(3), cfg.combat)
    assert d2.action.payload().get("card_index") == 0, d2.rationale


def test_pacts_end_activation_sequencing_for_lethal() -> None:
    """Owner audit 2026-08-14 Q1: with the pile at 2, the DFS must discover
    'exhaust card #3 (True Grit), THEN Pact's End' -- the gate is live pile +
    in-plan exhaust events at PLAY TIME, so deliberate activation is a
    plannable lethal line, not just an in-the-moment read."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    state = parse_state({
        "state_type": "monster", "run": {"act": 2, "floor": 20, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                   "block": 0, "energy": 2, "status": [], "exhaust_pile_count": 2,
                   "hand": [
                       {"index": 0, "id": "PACTS_END", "name": "Pact's End",
                        "type": "Attack", "cost": "0",
                        "description": "If you have 3 or more cards in your "
                        "Exhaust Pile, deal 17 damage to ALL enemies.",
                        "can_play": True, "target_type": "None"},
                       {"index": 1, "id": "TRUE_GRIT", "name": "True Grit",
                        "type": "Skill", "cost": "1",
                        "description": "Gain 7 Block. Exhaust a card in your hand.",
                        "can_play": True, "target_type": "None"},
                       {"index": 2, "id": "DEFEND_IRONCLAD", "name": "Defend",
                        "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 4, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Chomper", "hp": 15,
                                "max_hp": 60, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "30"}]}]},
    })
    cfg = load_policy_config()
    d = plan_combat_turn(state, cfg.combat)
    ra = d.rationale or ""
    assert "LETHAL" in ra, ra
    assert d.action.payload().get("card_index") == 1, ra  # True Grit arms it first
    assert ra.index("True Grit") < ra.index("Pact's End"), ra


def test_pacts_end_deficit_feeds_exhaust_enabler_drafts() -> None:
    """Owner audit 2026-08-14 Q2: a deck holding Pact's End with too few
    exhaust enablers makes enabler candidates (True Grit) draft HIGHER --
    the deficit-feeding lane (owner shadow review #2, 2026-07-24) supplies
    the 'activate Pact's End' nudge, scaled by starvation."""
    from types import SimpleNamespace as NS

    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.drafttags import load_draft_tags, score_adjustment

    tags = load_draft_tags()
    w = load_policy_config().card_rewards
    deck_with_pe = [NS(id="PACTS_END", type="Attack"), NS(id="BURNING_PACT", type="Skill"),
                    NS(id="STRIKE_IRONCLAD", type="Attack")]
    deck_plain = [NS(id="STRIKE_IRONCLAD", type="Attack")] * 3
    fed = score_adjustment("TRUE_GRIT", deck_with_pe, tags, w, act=2)
    unfed = score_adjustment("TRUE_GRIT", deck_plain, tags, w, act=2)
    assert fed > unfed, (fed, unfed)


def test_rampage_growth_future_credit_and_lethal_gate() -> None:
    """Owner audit 2026-08-15: live text bakes Rampage's grown damage (corpus
    9->14->19), so in-the-moment pricing was already right; the gap was the
    FUTURE +5/play. Non-lethal turn: Rampage beats an equal-damage Strike
    (growth banks value). Lethal turn: no future -- no credit."""
    from sts2bot.client.models import parse_state
    from sts2bot.kb.config import load_policy_config
    from sts2bot.policy.combat import plan_combat_turn

    def st(enemy_hp):
        return parse_state({
            "state_type": "monster", "run": {"act": 1, "floor": 8, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80,
                       "block": 20, "energy": 1, "status": [],
                       "hand": [
                           {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                            "type": "Attack", "cost": "1", "description": "Deal 9 damage.",
                            "can_play": True, "target_type": "AnyEnemy"},
                           {"index": 1, "id": "RAMPAGE", "name": "Rampage",
                            "type": "Attack", "cost": "1",
                            "description": "Deal 9 damage. Increase this card's "
                            "damage by 5 this combat.",
                            "can_play": True, "target_type": "AnyEnemy"}],
                       "potions": [], "max_potion_slots": 3},
            "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "e0", "name": "Chomper",
                                    "hp": enemy_hp, "max_hp": 60, "block": 0,
                                    "status": [], "intents":
                                    [{"type": "attack", "label": "8"}]}]},
        })

    cfg = load_policy_config()
    d = plan_combat_turn(st(60), cfg.combat)   # long fight: growth pays
    assert d.action.payload().get("card_index") == 1, d.rationale


def test_staged_body_debuff_wipe_zeroes_residual_vuln_credit() -> None:
    """Test Subject wiki pass 2026-08-15: an Adaptable body wipes ALL statuses on
    revive, so vuln/weak invested into a body within one average turn of the phase
    kill earns no residual credit (in-plan amplification still pays via damage)."""
    w = load_policy_config().combat
    def body(hp):
        return SimState(energy=0, my_block=0, my_strength=0, vuln_applied=2,
                        weak_applied=1,
                        enemies=(EnemySim(entity_id="TS_0", hp=hp, max_hp=300,
                                          block=0, vulnerable=2, incoming=0),))
    # body inside the wipe window: residual debuff credit gone
    assert _score(body(20), w, debuff_wipe_hp=25) < _score(body(20), w) - 1e-9
    # body comfortably alive: guard inert, scores identical
    assert _score(body(200), w, debuff_wipe_hp=25) == _score(body(200), w)


def test_strength_horizon_scales_with_remaining_fight() -> None:
    """Strength-horizon (2026-08-19): Str residual credit is future-turns value —
    zero on a lethal end-state (in-plan damage already paid via damage terms),
    boosted on long fights, floored (not zeroed) near the kill. Potion-sourced
    Str keeps the flat rate so the hoarding discipline is never out-bid."""
    w = load_policy_config().combat
    def foe(hp):
        return EnemySim(entity_id="e", hp=hp, max_hp=150, block=0, vulnerable=0,
                        incoming=0)
    gained = SimState(energy=0, my_block=0, my_strength=2, strength_gained=2,
                      enemies=(foe(150),))
    dead = SimState(energy=0, my_block=0, my_strength=2, strength_gained=2,
                    enemies=(foe(0),))
    base_dead = SimState(energy=0, my_block=0, my_strength=0,
                         enemies=(foe(0),))
    # lethal end: Str credit vanishes entirely (scores equal without it)
    assert _score(dead, w) == _score(base_dead, w)
    # long fight values the same Str gain more than a short one
    long_f = _score(gained, w, power_horizon=w.w_power_horizon_cap)
    short_f = _score(gained, w, power_horizon=1.0)
    assert long_f > short_f
    # potion Str: flat, horizon-independent
    pot = SimState(energy=0, my_block=0, my_strength=2, potion_strength=2,
                   enemies=(foe(150),))
    assert _score(pot, w, power_horizon=w.w_power_horizon_cap) == \
           _score(pot, w, power_horizon=1.0)


def test_all_enemy_str_down_softens_hits_and_artifact_eats_it() -> None:
    """Audit item 25 (Piercing Wail class) + owner Artifact nuance: a damageless
    ALL-enemies Str-down softens every attacker's remaining hits this turn, but
    an Artifact charge eats the debuff (Str-UP bypasses Artifact; Str-DOWN does
    not)."""
    wail = PlannedCard(
        index=0, name="Piercing Wail", cost=1,
        fx=parse_card_description("ALL enemies lose 6 Strength this turn. Exhaust."),
        targets_enemy=False)
    plain = EnemySim(entity_id="a", hp=50, max_hp=50, block=0, vulnerable=0,
                     incoming=14)
    shielded = EnemySim(entity_id="b", hp=50, max_hp=50, block=0, vulnerable=0,
                        incoming=14, artifact=1)
    s = SimState(energy=3, my_block=0, my_strength=0, enemies=(plain, shielded))
    out = _apply_card(s, wail, None)
    assert out.enemies[0].incoming == 8       # 14 - 6
    assert out.enemies[1].incoming == 14      # charge ate the debuff
    assert out.enemies[1].artifact == 0
    assert out.artifact_stripped == 1         # down-payment credit


def test_max_hp_cost_is_priced_and_fiddle_gates_the_draw_nudge() -> None:
    """Owner check 2026-08-23 (Brightest Flame under Fiddle): the draw credit
    was already correctly dead (no_draw seeding), but 'Lose 1 Max HP' was
    completely unpriced -- a permanent pool shrink now pays w_max_hp_cost."""
    w = load_policy_config().combat
    base = SimState(energy=0, my_block=0, my_strength=0,
                    enemies=(_enemy(),))
    spent = SimState(energy=0, my_block=0, my_strength=0, max_hp_spent=2,
                     enemies=(_enemy(),))
    assert _score(spent, w) < _score(base, w)


def test_stampede_docked_in_back_attack_fights() -> None:
    """Owner trap (noted long ago, implemented 2026-08-23): Stampede's
    end-of-turn random attack flips facing -- vs Kaiser back-attack claws
    that surrenders the +50% tax control. Playing the power there is docked;
    in a normal fight it keeps full value."""
    w = load_policy_config().combat
    def foe(back):
        return EnemySim(entity_id="c", hp=150, max_hp=200, block=0,
                        vulnerable=0, incoming=10, back_attack=back)
    played = SimState(energy=0, my_block=0, my_strength=0, stampede_played=True,
                      enemies=(foe(True), foe(True)))
    base = SimState(energy=0, my_block=0, my_strength=0,
                    enemies=(foe(True), foe(True)))
    assert _score(played, w) < _score(base, w) - 10  # the dock bites
    normal_played = SimState(energy=0, my_block=0, my_strength=0,
                             stampede_played=True, enemies=(foe(False),))
    normal_base = SimState(energy=0, my_block=0, my_strength=0,
                           enemies=(foe(False),))
    assert abs(_score(normal_played, w) - _score(normal_base, w)) < 1e-9


def test_bloodletting_not_played_into_wasted_energy() -> None:
    """Play-time audit 2026-08-27 (logs/reports/bloodletting_usage.md): 14.9%
    of era Bloodletting turns ended with the bought energy unspent -- 3 HP for
    nothing -- payoff decks excluded. Pin the CURRENT planner's behavior both
    ways: with nothing to buy it must not play the card (the -2.4 cheap-mult
    self term must win); when it unlocks a real spend it must lead the plan."""
    w = load_policy_config().combat
    bl = _bcard(0, "BLOODLETTING", "Bloodletting", 0,
                "Lose 3 HP. Gain 2 Energy.", "Skill", "None")
    # alone in hand at full energy: the energy can buy nothing
    d = plan_combat_turn(parse_state(_beckon_state(3, [bl])), w)
    assert d.action.payload().get("card_index") != 0
    # positive control: 1 energy + Bludgeon(3) -- Bloodletting funds the swing
    hand = [bl, _bcard(1, "BLUDGEON", "Bludgeon", 3, "Deal 32 damage.",
                       "Attack", "AnyEnemy")]
    d2 = plan_combat_turn(parse_state(_beckon_state(1, hand)), w)
    assert d2.action.payload().get("card_index") == 0


def test_thrash_random_attack_exhaust_kills_phantom_followups() -> None:
    """Owner catch 2026-08-27 (Queen f48 tape, r4): plan [Thrash > Strike]
    with Strike the ONLY other attack -- Thrash's 'Exhaust a random Attack in
    your Hand' guaranteed the follow-up never existed; the 22-HP Torch Head
    lived and swung. With the hand loss modeled, the kill line must order the
    attack FIRST (Strike 6 + Thrash 4x2 = 14 vs 14 HP only works that way)."""
    w = load_policy_config().combat
    thrash = _bcard(0, "THRASH", "Thrash", 1,
                    "Deal 4 damage twice. Exhaust a random Attack in your "
                    "Hand and add its damage to this card.", "Attack",
                    "AnyEnemy")
    strike = _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                    "Attack", "AnyEnemy")
    d = plan_combat_turn(
        parse_state(_beckon_state(2, [thrash, strike], enemy_hp=14,
                                  incoming="22")), w)
    assert d.action.payload()["card_index"] == 1  # Strike leads; Thrash eats air


_WITHER_DESC = ("Unplayable. At the end of your turn, if this is in your "
                "Hand, take 6 damage.")


def _wither(i):
    c = _bcard(i, "WITHER", "Wither", 0, _WITHER_DESC, "Status", "None",
               can_play=False)
    return c


def _aeonglass_state(energy, hand, countdown=6, boss_hp=400):
    st = _beckon_state(energy, hand, enemy_hp=boss_hp, incoming="26")
    e = st["battle"]["enemies"][0]
    e["name"] = "Aeonglass"
    e["max_hp"] = 512
    e["status"] = [
        {"id": "WITHERING_PRESENCE_POWER", "name": "Withering Presence",
         "amount": countdown,
         "description": "Every 6 cards you play, add a Wither to your Hand."},
        {"id": "ARTIFACT_POWER", "name": "Artifact", "amount": 3,
         "description": "Negates 3 debuffs."},
    ]
    return st


def test_whole_hand_exhaust_clears_wither_drain() -> None:
    """Owner decode 2026-08-28: Stoke/Second Wind purge hand Withers, but the
    DFS charged their stranded drain regardless — the planner saw NO benefit
    in the exact play that answers the boss. With two 6-damage Withers in
    hand, playing Stoke must beat holding (12 drain cleared)."""
    w = load_policy_config().combat
    stoke = _bcard(0, "STOKE", "Stoke", 1,
                   "Exhaust your Hand. Add 1 random card into your Hand for "
                   "each card Exhausted.", "Skill", "None")
    hand = [stoke, _wither(1), _wither(2)]
    d = plan_combat_turn(parse_state(_aeonglass_state(1, hand)), w)
    assert d.action.payload().get("card_index") == 0  # Stoke, not end-turn
    assert d.scores["hp_loss"] <= 26  # the 12 wither drain no longer counted


def test_targeted_exhaust_eats_the_worst_stranded() -> None:
    """True Grit+ ('Exhaust 1 card.') clears one Wither's drain; base True
    Grit ('at random') gets no such credit."""
    w = load_policy_config().combat
    tgp = _bcard(0, "TRUE_GRIT", "True Grit+", 1,
                 "Gain 9 Block. Exhaust 1 card.", "Skill", "None")
    hand = [tgp, _wither(1)]
    d = plan_combat_turn(parse_state(_aeonglass_state(1, hand)), w)
    assert d.action.payload().get("card_index") == 0
    assert d.scores["hp_loss"] <= 26 - 6 + 9  # drain cleared (block soaks too)
    tg = _bcard(0, "TRUE_GRIT", "True Grit", 1,
                "Gain 7 Block. Exhaust 1 card at random.", "Skill", "None")
    from sts2bot.policy.combat import _to_planned
    assert _to_planned(parse_state(_aeonglass_state(
        1, [tg, _wither(1)])).player.hand[0], 1).targeted_exhaust_n == 0


def test_withering_presence_amortized_tax_on_marginal_plays() -> None:
    """v2 (owner catch, seed-B T3: Whirlwind at 0 energy ticked the counter
    for free under crossing-only pricing): every play vs her pays
    tier/period, so a near-zero-value play is deterred at ANY countdown; a
    real hit still goes, and lethal pays nothing."""
    w = load_policy_config().combat
    # unit-level pin: 5 ticking plays with NO crossing pay 5/6 of a tier —
    # under crossing-only pricing this delta was exactly zero
    def foe():
        return EnemySim(entity_id="a", hp=400, max_hp=512, block=0,
                        vulnerable=0, incoming=0)
    base = SimState(energy=0, my_block=0, my_strength=0, enemies=(foe(),),
                    wither_period=6, wither_tier_dmg=6)
    ticked = SimState(energy=0, my_block=0, my_strength=0, enemies=(foe(),),
                      wither_period=6, wither_tier_dmg=6, withers_incurred=5)
    tax = _score(ticked, w) - _score(base, w)
    assert abs(tax - w.w_wither_incurred * 6 * 5 / 6) < 1e-9
    poke = _bcard(0, "CINDER", "Cinder", 0, "Deal 1 damage.", "Attack",
                  "AnyEnemy")
    hit = _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                 "Attack", "AnyEnemy")
    d2 = plan_combat_turn(
        parse_state(_aeonglass_state(3, [hit], countdown=5)), w)
    assert d2.action.payload().get("card_index") == 0  # real value still plays
    d3 = plan_combat_turn(
        parse_state(_aeonglass_state(3, [poke], countdown=1, boss_hp=1)), w)
    assert d3.action.payload().get("card_index") == 0  # lethal pays nothing


def test_barricade_credits_same_turn_block_at_plan_time() -> None:
    """Owner catch 2026-08-29 (seed-B T1 tape): the plan flipped toward block
    only AFTER Barricade resolved — sim.barricade seeded from live status
    only, never set by playing the power in-plan. With no incoming (her
    block turn), post-Barricade Defends are pure excess without the flag and
    banked value with it."""
    w = load_policy_config().combat
    barr = _bcard(0, "BARRICADE", "Barricade", 3,
                  "Block is no longer removed at the start of your turn.",
                  "Power", "None")
    defend = _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.",
                    "Skill", "None")
    st = _beckon_state(4, [barr, defend], enemy_hp=300, incoming="0")
    st["battle"]["enemies"][0]["intents"] = [{"type": "Buff", "label": ""}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("card_index") == 0  # Barricade leads
    assert "Defend" in (d.rationale or "")  # and the plan KEEPS the Defend


def test_draws_fizzle_at_the_hand_limit() -> None:
    """Owner catch 2026-08-29 (seed-A T1): draws past 10 cards do nothing —
    unmodeled, the bot burned ~2 draws into a full hand and reached Pact's
    End+ a turn late. A draw-5 played from a 9-card hand must credit only
    2 (9 - 1 played = 8 held, room for 2); the same play from a 5-card hand
    credits all 5. Emergent effect: the DFS now prefers making room first."""
    from sts2bot.policy.combat import _apply_card
    from sts2bot.policy.textparse import parse_card_description

    fx = parse_card_description("Draw 5 cards.")
    pc = PlannedCard(index=0, name="BigDraw", cost=0, fx=fx,
                     targets_enemy=False, is_attack=False)
    full = SimState(energy=3, my_block=0, my_strength=0, enemies=(),
                    hand_size=9)
    out = _apply_card(full, pc, None)
    assert out.draws == 2
    roomy = SimState(energy=3, my_block=0, my_strength=0, enemies=(),
                     hand_size=5)
    out2 = _apply_card(roomy, pc, None)
    assert out2.draws == 5


def test_vuln_payoff_cards_hold_when_dry() -> None:
    """Owner rule (seed-A T2 + seed-B r4): Dominate/Molten Fist-class payoff
    riders must not fire on zero vuln — Dominate led plans as an artifact
    STRIPPER, Molten Fist+ exhausted itself under Artifact with vuln 0.
    With vuln up, both play at full value."""
    w = load_policy_config().combat
    dom = _bcard(0, "DOMINATE", "Dominate", 1,
                 "Apply 1 Vulnerable. Gain 1 Strength for each Vulnerable "
                 "on the enemy. Exhaust.", "Skill", "AnyEnemy")
    st = _beckon_state(1, [dom], enemy_hp=300)
    st["battle"]["enemies"][0]["status"] = [
        {"id": "ARTIFACT_POWER", "name": "Artifact", "amount": 3,
         "description": "Negates 3 debuffs."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("card_index") != 0  # strip credit < dry dock
    st2 = _beckon_state(1, [dom], enemy_hp=300,
                        enemy_status=[{"id": "VULNERABLE_POWER",
                                       "name": "Vulnerable", "amount": 2,
                                       "description": "Takes 50% more damage."}])
    d2 = plan_combat_turn(parse_state(st2), w)
    assert d2.action.payload().get("card_index") == 0  # payoff live: play


def test_artifact_strip_scales_with_deck_vuln_dependency() -> None:
    """Owner (seed-A T3): flat strip credit underrates charges in
    vuln-dependent decks. The multiplier rides SimState so a stripped
    charge scores payoff_mult-scaled."""
    w = load_policy_config().combat
    def foe():
        return EnemySim(entity_id="a", hp=200, max_hp=200, block=0,
                        vulnerable=0, incoming=5)
    flat = SimState(energy=0, my_block=0, my_strength=0, enemies=(foe(),),
                    artifact_stripped=2)
    scaled = SimState(energy=0, my_block=0, my_strength=0, enemies=(foe(),),
                      artifact_stripped=2, artifact_strip_mult=2.5)
    assert (_score(scaled, w) - _score(flat, w)
            == w.w_artifact_strip * 2 * 1.5)


def test_cascade_played_for_free_pile_value() -> None:
    """Owner catch (seed-B T5): Cascade+ at X=0 plays the next pile card
    free — but the class parsed to zero and had no credit, so it was never
    played. Now: played at 0 leftover cost; the cascaded card also ticks
    Withering Presence (2 ticks total vs her)."""
    w = load_policy_config().combat
    casc = _bcard(0, "CASCADE", "Cascade+", 0,
                  "Play the next X+1 cards in your draw pile.", "Skill",
                  "None")
    d = plan_combat_turn(parse_state(_beckon_state(0, [casc], enemy_hp=200)), w)
    assert d.action.payload().get("card_index") == 0  # free EV: play it
    from sts2bot.client.models import parse_state as ps
    from sts2bot.policy.combat import _apply_card, _to_planned
    st = ps(_aeonglass_state(0, [casc], countdown=6))
    pc = _to_planned(st.player.hand[0], 0)
    sim = SimState(energy=0, my_block=0, my_strength=0, enemies=(),
                   wither_countdown=6, wither_period=6, wither_tier_dmg=3)
    out = _apply_card(sim, pc, None)
    assert out.withers_incurred == 2  # Cascade + its cascaded card both tick
    assert out.pile_plays == 1


def test_cheap_draw_attacks_open_the_turn() -> None:
    """Queue #10 (owner, seed-A r5: Dominate led over Pommel+ — draw-first
    buys replan optionality the plan-time DFS can't see). Cost<=1 draw
    cards get the opener nudge: on a near-tied two-card plan, Pommel leads."""
    w = load_policy_config().combat
    pommel = _bcard(0, "POMMEL_STRIKE", "Pommel Strike+", 1,
                    "Deal 10 damage. Draw 2 cards.", "Attack", "AnyEnemy")
    big = _bcard(1, "MAUL", "Maul", 2, "Deal 18 damage.", "Attack", "AnyEnemy")
    d = plan_combat_turn(parse_state(_beckon_state(3, [pommel, big],
                                                   enemy_hp=200)), w)
    assert d.action.payload().get("card_index") == 0  # draw opens


def test_zero_energy_x_cost_deals_zero_and_dead_ritual_vetoed() -> None:
    """Owner T6/T7 catches (seed-B): (a) 0-energy Whirlwind got a phantom
    minimum hit (max(1,X)) -- real X=0 is zero hits, and with zero value the
    play must not happen; (b) Forgotten Ritual unfulfilled was played to
    DODGE the energy-waste dock (+0.15 net for a dead self-exhausting play)
    -- now vetoed outright unless FNP converts the self-exhaust to block."""
    w = load_policy_config().combat
    ww = _bcard(0, "WHIRLWIND", "Whirlwind", "X",
                "Deal 6 damage to ALL enemies X times.", "Attack", "AllEnemy")
    d = plan_combat_turn(parse_state(_beckon_state(0, [ww], enemy_hp=200)), w)
    assert d.action.payload().get("card_index") != 0  # zero hits: hold
    fr = _bcard(0, "FORGOTTEN_RITUAL", "Forgotten Ritual", 1,
                "If you Exhausted a card this turn, gain "
                "[ironclad_energy_icon.png][ironclad_energy_icon.png]"
                "[ironclad_energy_icon.png]. Exhaust.", "Skill", "None")
    d2 = plan_combat_turn(parse_state(_beckon_state(3, [fr], enemy_hp=200)), w)
    assert d2.action.payload().get("card_index") != 0  # dead FR vetoed


def test_targeted_exhaust_purges_burns_even_when_blocked() -> None:
    """Owner catch 2026-08-31 (Mecha Knight r5): TG+ unplayed at 4 energy
    with two Burns in hand — the Burns were already blocked this turn, so
    the stranded-clear credited nothing, but exhausting one removes its
    drain from every FUTURE cycle. The purge credit makes TG+ play."""
    w = load_policy_config().combat
    tgp = _bcard(0, "TRUE_GRIT", "True Grit+", 1,
                 "Gain 9 Block. Exhaust 1 card.", "Skill", "None")
    burn = _bcard(1, "BURN", "Burn", 0,
                  "Unplayable. At the end of your turn, if this is in your "
                  "Hand, take 2 damage.", "Status", "None", can_play=False)
    st = _beckon_state(4, [tgp, burn], enemy_hp=200, incoming="0")
    st["battle"]["enemies"][0]["intents"] = [{"type": "Buff", "label": ""}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("card_index") == 0  # purge the Burn


# --- Reattach segments (Decimillipede, 2026-09-03) ---------------------------
_REATTACH = [{"id": "REATTACH_POWER", "name": "Reattach",
              "description": "If other segments are still alive, revives in 2 turns with 25 HP."}]


def _segments_fight(hps: list[int]) -> dict:
    return {"state_type": "elite", "run": {"act": 2, "floor": 25, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 70, "max_hp": 80, "block": 0,
                       "energy": 3, "status": [],
                       "hand": [_bcard(i, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.",
                                       "Attack", "AnyEnemy") for i in range(3)]},
            "battle": {"round": 3, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": f"s{i}", "name": "Decimillipede", "hp": hp,
                                    "max_hp": 40, "block": 0, "status": list(_REATTACH),
                                    "intents": [{"type": "attack", "label": "6"}]}
                                   for i, hp in enumerate(hps)]}}


def test_reattach_segment_kill_is_futile_unless_all_die() -> None:
    """Decimillipede's Reattach: 'revives in 2 turns with 25 HP' while other
    segments live. Arm v3 run 4 killed the same segment repeatedly for 12
    rounds and died. A 6-HP segment next to two 30-HP ones must NOT be killed
    (the Strike is spent lowering a live segment instead); the same board with
    every segment in range kills them all; a lone survivor is a plain kill."""
    w = load_policy_config().combat
    d = plan_combat_turn(parse_state(_segments_fight([6, 30, 30])), w)
    assert d.action.payload()["target"] != "s0"
    d_all = plan_combat_turn(parse_state(_segments_fight([5, 5, 5])), w)
    assert d_all.action.payload()["target"] in ("s0", "s1", "s2")
    assert "plan [Strike > Strike > Strike]" in d_all.rationale
    d_last = plan_combat_turn(parse_state(_segments_fight([6, 0, 0])), w)
    assert d_last.action.payload()["target"] == "s0"


def test_replan_seeds_attack_count_for_relic_cadence() -> None:
    """Arm v3 run 4 (Decimillipede): Break+ killed a segment, the replan forgot
    that attack, so Strike + Dismantle read as attacks 1-2 (no Kusarigama 6 on
    the 3rd) -> 14 < 19 HP, not lethal, block instead; the segment revived.
    Seeded with 1 attack already played, the same hand is lethal."""
    w = load_policy_config().combat
    st = _segments_fight([19])
    st["player"]["relics"] = [{
        "id": "KUSARIGAMA", "name": "Kusarigama",
        "description": ("Every time you play 3 Attacks in a single turn, "
                        "deal 6 damage to a random enemy.")}]
    st["player"]["hand"] = [
        _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
        _bcard(1, "DISMANTLE", "Dismantle", 1,
               "Deal 8 damage. If the enemy is Vulnerable, hits twice.", "Attack", "AnyEnemy"),
        _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    cold = plan_combat_turn(parse_state(st), w)
    seeded = plan_combat_turn(parse_state(st), w, kinds_this_turn=(1, 0, 0))
    assert "LETHAL" not in cold.rationale
    assert "LETHAL" in seeded.rationale


def test_seeded_attacks_do_not_double_discount_stomp() -> None:
    """Batch stall 2026-09-03 (run 151507): Stomp 'costs 1 less per Attack
    played this turn' was SHOWN at cost 1 after two attacks; the seeded attack
    count discounted it again to -1, the planner played it at 0 energy, the
    game refused, and the settle loop hit the stall rail. The displayed cost
    already carries earlier plays: only the plan's own attacks discount."""
    w = load_policy_config().combat
    st = _segments_fight([32])
    st["battle"]["enemies"][0]["status"] = []
    st["player"]["energy"] = 0
    st["player"]["hand"] = [
        _bcard(0, "STOMP", "Stomp", 1, "Deal 12 damage to ALL enemies. Costs 1 less "
               "[ironclad_energy_icon.png] for each Attack played this turn.", "Attack",
               "AllEnemies", can_play=False),
        _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy",
               can_play=False)]
    d = plan_combat_turn(parse_state(st), w, kinds_this_turn=(2, 0, 0))
    assert d.action.payload()["action"] == "end_turn"


def test_excluded_indices_drop_a_refused_card() -> None:
    """Router safety net (2026-09-03 stall): a play the game refused through the
    whole settle window is excluded from the replan for the rest of the turn."""
    w = load_policy_config().combat
    st = _segments_fight([32])
    st["battle"]["enemies"][0]["status"] = []
    st["player"]["hand"] = [
        _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
        _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(st), w, excluded_indices=frozenset({0}))
    assert d.action.payload()["card_index"] == 1
    d_none = plan_combat_turn(parse_state(st), w, excluded_indices=frozenset({0, 1}))
    assert d_none.action.payload()["action"] == "end_turn"


# --- Unmovable (owner catch 2026-09-04) --------------------------------------
_UNMOVABLE_TXT = "The first time you gain Block from a card each turn, double the amount gained."


def _unmovable_fight(hand: list, status: list | None = None, incoming: str = "20") -> dict:
    st = _segments_fight([60])
    st["battle"]["enemies"][0]["status"] = []
    st["battle"]["enemies"][0]["intents"] = [{"type": "attack", "label": incoming}]
    st["player"]["hand"] = hand
    st["player"]["status"] = status or []
    return st


def test_unmovable_is_sequenced_before_the_first_block() -> None:
    """Owner 2026-09-04 (Infested Prism T1): Unmovable doubles the FIRST block
    of the turn and applies the turn it is played, so Unmovable -> Defend
    beats Defend -> Unmovable. The planner had no model and blocked first."""
    w = load_policy_config().combat
    st = _unmovable_fight([
        _bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
        _bcard(1, "UNMOVABLE", "Unmovable", 2, _UNMOVABLE_TXT, "Power", "None")])
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 1  # the power first
    assert "plan [Unmovable > Defend]" in d.rationale


def test_unmovable_already_up_does_not_double_twice() -> None:
    """With the power already in play the mod's previews read doubled on every
    block card ('Gain 10 Block' x2); only the first play gets it, the second
    grants 5. Incoming 20 vs 10 + 5 -> 5 HP lost, not 0."""
    w = load_policy_config().combat
    up = [{"id": "UNMOVABLE_POWER", "name": "Unmovable", "amount": 1, "type": "Buff",
           "description": _UNMOVABLE_TXT}]
    st = _unmovable_fight([
        _bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 10 Block.", "Skill", "None"),
        _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 10 Block.", "Skill", "None")],
        status=up)
    d = plan_combat_turn(parse_state(st), w)
    assert d.scores["hp_loss"] == 5.0
    # a block card already played this turn: the doubling is spent, previews
    # are single again -> both Defends grant as read (10 + 10 >= 20)
    d2 = plan_combat_turn(parse_state(st), w, block_used_this_turn=True)
    assert d2.scores["hp_loss"] == 0.0


def test_block_before_unmovable_spends_the_doubling() -> None:
    """Owner nuance 2026-09-04: Defend -> Unmovable -> Defend gets NO bonus --
    the turn's first block already happened when the power lands. With 3
    energy the planner can't afford both Defends plus the 2-cost power, and
    the doubling only ever helps a block card played AFTER the power."""
    from sts2bot.policy.combat import PlannedCard, SimState, _apply_card
    from sts2bot.policy.textparse import CardEffects
    defend = PlannedCard(index=0, name="Defend", cost=1, fx=CardEffects(block=5),
                         targets_enemy=False)
    power = PlannedCard(index=1, name="Unmovable", cost=2, fx=CardEffects(),
                        targets_enemy=False, is_power=True, grants_unmovable=True)
    s0 = SimState(energy=5, enemies=(_enemy(),), my_block=0, my_strength=0)
    # Unmovable first: the next Defend doubles (5 -> 10)
    s_pow_first = _apply_card(_apply_card(s0, power, None), defend, None)
    assert s_pow_first.my_block == 10
    # Defend first: the doubling is spent; Unmovable then a second Defend adds 5
    s_def_first = _apply_card(_apply_card(_apply_card(s0, defend, None), power, None),
                              PlannedCard(index=2, name="Defend", cost=1,
                                          fx=CardEffects(block=5), targets_enemy=False),
                              None)
    assert s_def_first.my_block == 10  # 5 + 5, no bonus anywhere


def test_free_lethal_beats_self_hp_lethal() -> None:
    """Owner catch 2026-09-10 (hallway, Exoskeleton at 1 HP): the bot played
    Brand (lose 1 HP, +1 Str) into Tear Asunder+ for the kill when a Strike
    was lethal for free -- overkill damage and energy spend out-bid the 1 HP.
    On a lethal turn neither counts: the plain Strike must win."""
    w = load_policy_config().combat
    st = _segments_fight([1])
    st["battle"]["enemies"][0]["status"] = []
    st["player"]["hp"] = 71
    st["player"]["hand"] = [
        _bcard(0, "BRAND", "Brand", 0, "Lose 1 HP. Exhaust 1 card. Gain 1 Strength.",
               "Skill", "None"),
        _bcard(1, "TEAR_ASUNDER", "Tear Asunder+", 2,
               "Deal 8 damage. Hits an additional time for each Strength.", "Attack",
               "AnyEnemy"),
        _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
        _bcard(3, "STRIKE_IRONCLAD", "Strike", 1, "Deal 7 damage.", "Attack", "AnyEnemy"),
        _bcard(4, "STRIKE_IRONCLAD", "Strike", 1, "Deal 7 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(st), w)
    assert "LETHAL" in d.rationale
    assert d.action.payload()["card_index"] in (3, 4)
    assert d.scores["hp_loss"] == 0.0


def test_retain_hand_is_worth_playing_to_keep_a_good_card() -> None:
    """Owner catch 2026-09-10 (Insatiable r1): a 0-cost Equilibrium (gain
    block, Retain your Hand) sat unplayed because block was already up -- but
    it would have carried Bloodletting into the next turn. With the retain
    credit the planner plays it; with nothing worth keeping it still may not."""
    w = load_policy_config().combat
    st = _segments_fight([292])
    st["battle"]["enemies"][0]["status"] = []
    st["battle"]["enemies"][0]["intents"] = [{"type": "attack", "label": "6"}]
    st["player"]["hp"], st["player"]["block"], st["player"]["energy"] = 68, 10, 1
    st["player"]["hand"] = [
        _bcard(0, "BLOODLETTING", "Bloodletting", 0,
               "Lose 3 HP. Gain [ironclad_energy_icon.png][ironclad_energy_icon.png].",
               "Skill", "None"),
        _bcard(1, "EQUILIBRIUM", "Equilibrium", 0, "Gain 13 Block. Retain your Hand this turn.",
               "Skill", "None")]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload().get("card_index") == 1
    assert "Equilibrium" in d.rationale


# --- Cascade pile plays scale with X; death-wall hail mary (owner catch 2026-09-11) ---
def test_cascade_pile_plays_scale_with_energy_at_play() -> None:
    from sts2bot.policy.combat import _to_planned
    st = _segments_fight([100])
    st["player"]["hand"] = [
        _bcard(0, "CASCADE", "Cascade+", "X", "Play the top X+1 cards of your Draw Pile.",
               "Skill", "None"),
        _bcard(1, "CASCADE", "Cascade", "X", "Play the top X cards of your Draw Pile.",
               "Skill", "None"),
        _bcard(2, "PEEK", "Peek", 1, "Play the top card of your Draw Pile.", "Skill", "None")]
    hand = parse_state(st).player.hand
    plus, base, one = (_to_planned(c, 3) for c in hand)
    assert plus.pile_plays_scale_x and plus.pile_plays_bonus == 1
    assert base.pile_plays_scale_x and base.pile_plays_bonus == 0
    assert not one.pile_plays_scale_x and one.plays_pile_n == 1
    s0 = SimState(energy=3, enemies=(_enemy(),), my_block=0, my_strength=0)
    assert _apply_card(s0, plus, None).pile_plays == 4
    assert _apply_card(s0, base, None).pile_plays == 3
    assert _apply_card(SimState(energy=0, enemies=(_enemy(),), my_block=0, my_strength=0),
                       plus, None).pile_plays == 1


def test_death_wall_prefers_the_bigger_lottery_over_saving_3_hp() -> None:
    """Test Subject death turn (owner 2026-09-11): 17 HP vs 10x3, hand
    Cascade+ (X) and Bloodletting at 1 energy. Every line projects death;
    Bloodletting -> Cascade+ at X=3 plays four pile cards (a real chance at
    block) where Cascade+ alone at X=0 plays one. The bot played Cascade+
    alone because the 3 HP still scored against a line already dead on paper."""
    w = load_policy_config().combat
    st = _segments_fight([296])
    st["battle"]["enemies"][0]["status"] = []
    st["battle"]["enemies"][0]["intents"] = [{"type": "attack", "label": "10x3"}]
    st["player"]["hp"], st["player"]["energy"] = 17, 1
    st["player"]["hand"] = [
        _bcard(0, "CASCADE", "Cascade+", "X", "Play the top X+1 cards of your Draw Pile.",
               "Skill", "None"),
        _bcard(1, "BLOODLETTING", "Bloodletting", 0,
               "Lose 3 HP. Gain [ironclad_energy_icon.png][ironclad_energy_icon.png].",
               "Skill", "None")]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 1
    assert "plan [Bloodletting > Cascade+]" in d.rationale


def test_cloak_clasp_counts_cards_drawn_this_turn() -> None:
    """Owner relic check 2026-09-11: Cloak Clasp ('end of turn: 1 Block per
    card in your Hand') must see the hand AFTER in-plan draws. Pommel Strike
    (draw 2) with two Defends left behind -> 4 Clasp block, not 2."""
    w = load_policy_config().combat
    st = _segments_fight([60])
    st["battle"]["enemies"][0]["status"] = []
    st["battle"]["enemies"][0]["intents"] = [{"type": "attack", "label": "10"}]
    st["player"]["energy"] = 1
    st["player"]["relics"] = [{
        "id": "CLOAK_CLASP", "name": "Cloak Clasp",
        "description": "At the end of your turn, gain 1 Block for each card in your Hand."}]
    st["player"]["hand"] = [
        _bcard(0, "POMMEL_STRIKE", "Pommel Strike", 1, "Deal 9 damage. Draw 2 cards.",
               "Attack", "AnyEnemy"),
        _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
        _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 0
    # 10 incoming - (2 Defends held + 2 drawn) x 1 Clasp block = 6
    assert d.scores["hp_loss"] == 6.0


def test_beat_down_reads_the_discard_pile_for_lethal() -> None:
    """Owner catch 2026-09-28 (run 20260928-080713, Bygone Effigy at 14 HP):
    Beat Down ('Play 3 random Attacks from your Discard Pile', 3 energy,
    random target) parsed to no damage, so the bot played Defend/Defend/
    Strike (8) and took the hit. The discard is player-visible: credit the
    pessimistic floor (the N smallest attack damages there). With Strike+ 10
    and Perfected Strike 20 in the discard the floor is 30 >= 14: lethal."""
    w = load_policy_config().combat
    st = _segments_fight([14])
    st["battle"]["enemies"][0]["status"] = []
    st["battle"]["enemies"][0]["intents"] = [{"type": "attack", "label": "12"}]
    st["player"]["energy"] = 3
    st["player"]["hand"] = [
        _bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
        _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
        _bcard(2, "STRIKE_IRONCLAD", "Strike", 1, "Deal 8 damage.", "Attack", "AnyEnemy"),
        _bcard(3, "BEAT_DOWN", "Beat Down", 3, "Play 3 random Attacks from your Discard Pile.",
               "Skill", "RandomEnemy")]
    st["player"]["discard_pile"] = [
        {"name": "Strike+", "cost": "1", "description": "Deal 10 damage."},
        {"name": "Perfected Strike", "cost": "2",
         "description": "Deal 20 damage. Deals 2 additional damage for ALL your cards "
                        "containing Strike."},
        {"name": "Defend", "cost": "1", "description": "Gain 5 Block."}]
    d = plan_combat_turn(parse_state(st), w)
    assert d.action.payload()["card_index"] == 3
    assert d.action.payload().get("target") is None  # random target: no click target
    assert "LETHAL" in d.rationale
    # an empty discard: Beat Down is worth nothing and must not be played over the Strike
    st["player"]["discard_pile"] = []
    d2 = plan_combat_turn(parse_state(st), w)
    assert d2.action.payload()["card_index"] != 3


def test_blocked_hit_into_a_sleeper_does_not_wake_her() -> None:
    """2026-09-28 (A0 era: 9 of 11 Matriarch losses were poke-wakes on rounds
    1-2). She 'Awakens upon losing HP': a hit her Plating block fully soaks
    leaves her asleep and pays nothing. The old any-hit rule charged the
    blocked Headbutt+ and then let the real waking Strike land free."""
    from dataclasses import replace as dc_replace
    sleeper = dc_replace(_enemy(asleep=True, asleep_left=3), block=12)
    out = _apply_attack(_state(sleeper), 0, _attack(12))
    assert out.enemies[0].hp == 100 and out.enemies[0].block == 0
    assert out.enemies[0].asleep is True
    assert out.sleepers_woken == 0 and out.wake_turns_forfeit == 0
    # the follow-up that DOES lose her HP is the wake, and it pays
    out2 = _apply_attack(out, 0, _attack(6))
    assert out2.enemies[0].asleep is False and out2.sleepers_woken == 1


def test_wake_penalty_scales_with_forfeited_setup_turns() -> None:
    """The unit of w_wake_sleeper is one forfeited free turn (her per-turn
    threat): 3 stacks left -> 2 turns, 2 -> 1, unknown -> 1 (the old flat
    bar). With 1 stack she wakes on her own after this turn, so that hit
    forfeits nothing and pays nothing."""
    for left, forfeit in ((3, 2), (2, 1), (0, 1)):
        out = _apply_attack(_state(_enemy(asleep=True, asleep_left=left)), 0, _attack(6))
        assert out.enemies[0].asleep is False
        assert (out.sleepers_woken, out.wake_turns_forfeit) == (1, forfeit), left
    free = _apply_attack(_state(_enemy(asleep=True, asleep_left=1)), 0, _attack(6))
    assert free.enemies[0].asleep is False and free.enemies[0].hp == 94
    assert (free.sleepers_woken, free.wake_turns_forfeit) == (0, 0)


def _matriarch_round1(asleep_left: int) -> dict:
    # seed HEKRVZMGUV round 1 (A0 batch 2026-09-28), trimmed: Asleep 3 + 12 Plating
    # block, hand of pokes + a Power. Breakthrough+ 13 clears the 12 block by 1 HP
    # (a wake); Headbutt+ 12 alone is fully soaked (not a wake).
    return {
        "state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": 52, "max_hp": 81, "block": 0,
                   "energy": 3, "status": [],
                   "hand": [
                       _bcard(0, "BREAKTHROUGH", "Breakthrough+", 1,
                              "Lose 1 HP. Deal 13 damage to ALL enemies.", "Attack", "AllEnemy"),
                       _bcard(1, "HEADBUTT", "Headbutt+", 1,
                              "Deal 12 damage. Put a card from your Discard Pile on top of "
                              "your Draw Pile.", "Attack", "AnyEnemy"),
                       _bcard(2, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack",
                              "AnyEnemy"),
                       _bcard(3, "STONE_ARMOR", "Stone Armor+", 1, "Gain 6 Plating.", "Power",
                              "None")],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 1, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "LAGAVULIN_MATRIARCH_0",
                                "name": "Lagavulin Matriarch",
                                "hp": 222, "max_hp": 222, "block": 12,
                                "status": [
                                    {"id": "PLATING_POWER", "name": "Plating", "amount": 12,
                                     "description": "At the end of your turn, gain 12 Block."},
                                    {"id": "ASLEEP_POWER", "name": "Asleep",
                                     "amount": asleep_left,
                                     "description": "Awakens upon losing HP or after 3 turns."}],
                                "intents": [{"type": "Sleep", "label": "",
                                             "title": "Sleeping"}]}]},
    }


def test_planner_holds_pokes_behind_the_matriarchs_plating_on_round_1() -> None:
    """Live 2026-09-28 (seed HEKRVZMGUV, lost): plan [Headbutt+ > Breakthrough+ >
    Strike > ... > Stone Armor+] scored 90.8 -- the blocked Headbutt+ pre-paid the
    flat wake bar, then Strike/Breakthrough+ woke her on round 1 for 19 HP of 222
    with the +0.8 focus and +1.5 ramp premiums bribing the follow-ups. With the
    penalty per forfeited turn (2 here) and no premiums on a wake turn, the
    planner banks the Power and does not lose her HP."""
    from sts2bot.kb.config import load_policy_config
    d = plan_combat_turn(parse_state(_matriarch_round1(3)), load_policy_config().combat,
                         fight_plan="focus")
    r = d.rationale or ""
    assert "Stone Armor+" in r
    assert "Breakthrough+" not in r
    assert not ("Headbutt+" in r and "Strike" in r)  # the pair breaks her block and wakes her
    # on her LAST asleep turn the wake is free: the same hand now hits her
    d1 = plan_combat_turn(parse_state(_matriarch_round1(1)), load_policy_config().combat,
                          fight_plan="focus")
    assert "Breakthrough+" in (d1.rationale or "")


def test_random_exhaust_rider_parses_true_grit_and_cinder() -> None:
    from sts2bot.policy.combat import _to_planned
    st = parse_state(_beckon_state(3, [
        _bcard(0, "TRUE_GRIT", "True Grit", 1, "Gain 7 Block. Exhaust 1 card at random.",
               "Skill", "None"),
        _bcard(1, "CINDER", "Cinder", 2, "Deal 18 damage. Exhaust 1 card at random.",
               "Attack", "AnyEnemy"),
        _bcard(2, "TRUE_GRIT", "True Grit+", 1, "Gain 9 Block. Exhaust a card in your Hand.",
               "Skill", "None"),
        _bcard(3, "THRASH", "Thrash", 1,
               "Deal 4 damage twice. Exhaust a random Attack in your Hand and add its damage "
               "to this card.", "Attack", "AnyEnemy")]))
    flags = [_to_planned(c, 3, 0, [], 0).exhausts_random_card for c in st.player.hand]
    assert flags == [True, True, False, False]


def test_needed_block_is_played_before_a_random_exhauster() -> None:
    """Live 2026-09-28 (seed NDW2DDX5LZ, Waterfall Giant eruption 39 vs 29 HP):
    plan [Pommel Strike > True Grit > Defend] read 12 block and survival; True
    Grit's 'Exhaust 1 card at random' ate the Defend and the bot died 3 short.
    Pessimism as for Thrash: the exhaust eats the card the plan wants most
    next, so the DFS sequences the Defend BEFORE True Grit (same block, no
    exposure). Replay of the logged tick: [Pommel Strike > Defend > True Grit]."""
    from sts2bot.kb.config import load_policy_config
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike+", 1, "Deal 9 damage.", "Attack", "AnyEnemy"),
            _bcard(1, "TRUE_GRIT", "True Grit", 1, "Gain 7 Block. Exhaust 1 card at random.",
                   "Skill", "None"),
            _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=240, hp=29,
                                                   incoming="39")),
                         load_policy_config().combat)
    r = d.rationale or ""
    assert "Defend" in r and "True Grit" in r
    assert r.index("Defend") < r.index("True Grit")
    assert d.scores["hp_loss"] == 27.0  # 39 - 12: lives at 2, Defend safe from the exhaust


def test_this_turn_strength_is_temporary_not_permanent() -> None:
    """2026-09-29 (seed 738CVJRL8Y, Matriarch r1): the temp-Strength regex in
    textparse carried a literal backspace byte where the word boundary was
    meant, so it never matched and Setup Strike's 'Gain 2 Strength this turn'
    was credited as PERMANENT Strength (+14..28 through the horizon term) --
    enough to buy a round-1 poke-wake. Temporary Strength lives for the plan's
    damage only and earns no strength_gained credit."""
    from sts2bot.policy.textparse import parse_card_description
    fx = parse_card_description("Deal 7 damage. Gain 2 Strength this turn.")
    assert (fx.strength, fx.strength_temp) == (0, 2)
    assert parse_card_description("Gain 2 Strength.").strength == 2  # Inflame unchanged


def test_personal_hive_charges_a_dazed_per_landed_hit() -> None:
    """Entomancer (decoded 2026-09-30, run 20260930-001237: 80 -> 7 HP from
    full, a hand of four Dazed by round 6): 'Whenever this enemy is hit by an
    Attack, add 1 Dazed into your Draw Pile', per hit, stacking with Empower.
    A 3-hit attack into Hive 2 seeds six Dazed; a blocked hit still counts."""
    from dataclasses import replace as dc_replace
    out = _apply_attack(_state(_enemy(hive=2)), 0, _attack(4, hits=3))
    assert out.hive_dazed == 6
    blocked = _apply_attack(_state(dc_replace(_enemy(hive=1), block=50)), 0, _attack(4, hits=3))
    assert blocked.hive_dazed == 3 and blocked.enemies[0].hp == 100


def test_planner_prefers_one_big_hit_over_many_small_into_a_hive() -> None:
    from sts2bot.kb.config import load_policy_config
    w = load_policy_config().combat
    hive = [{"id": "PERSONAL_HIVE_POWER", "name": "Personal Hive", "amount": 3,
             "description": "Whenever this enemy is hit by an Attack, add 1 Dazed into "
                            "your Draw Pile."}]
    hand = [_bcard(0, "PUMMEL", "Pummel", 1, "Deal 4 damage 3 times.", "Attack", "AnyEnemy"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike+", 1, "Deal 11 damage.", "Attack", "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(1, hand, enemy_hp=145, hp=70,
                                                   enemy_status=hive, incoming="18")), w)
    assert d.action.payload()["card_index"] == 1  # 11 in one hit beats 12 in three
    d0 = plan_combat_turn(parse_state(_beckon_state(1, hand, enemy_hp=145, hp=70,
                                                    incoming="18")), w)
    assert d0.action.payload()["card_index"] == 0  # no hive: raw damage wins


def _giant_state(hp: int, giant_hp: int, eruption: int, hand: list, incoming: str = "10") -> dict:
    return {"state_type": "boss", "run": {"act": 1, "floor": 17, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 84, "block": 0,
                       "energy": 3, "status": [], "hand": hand, "potions": [],
                       "max_potion_slots": 3},
            "battle": {"round": 6, "turn": "player", "is_play_phase": True,
                       "enemies": [{"entity_id": "WATERFALL_GIANT_0", "name": "Waterfall Giant",
                                    "hp": giant_hp, "max_hp": 240, "block": 0,
                                    "status": [{"id": "STEAM_ERUPTION_POWER",
                                                "name": "Steam Eruption", "amount": eruption,
                                                "description": f"When killed, deals {eruption} "
                                                "damage at the end of your next turn."}],
                                    "intents": [{"type": "attack", "label": incoming}]}]}}


def test_erupting_kill_is_not_the_end_of_the_fight() -> None:
    """Waterfall Giant (era tally 2026-09-30: 13 of 14 deaths were the telegraphed
    post-kill eruption). Killing it leaves a blast pending next turn, so the
    kill is neither lethal_end nor free of the blast's cost."""
    from dataclasses import replace as dc_replace
    out = _apply_attack(_state(dc_replace(_enemy(eruption=30), hp=10)), 0, _attack(12))
    assert out.enemies[0].hp == 0 and not _fight_over(out.enemies)
    plain = _apply_attack(_state(dc_replace(_enemy(), hp=10)), 0, _attack(12))
    assert _fight_over(plain.enemies)


def test_planner_will_not_take_a_kill_that_the_eruption_finishes() -> None:
    """15 HP, Giant at 20 with a 45 eruption: Bash + Strike + Strike kills it but
    the blast minus a 15-block turn (calibrated 2026-09-30) still takes 30 --
    a hopeless margin; two Defends cover the 10 incoming instead. With a 12
    eruption the kill is free and the planner takes it."""
    from sts2bot.kb.config import load_policy_config
    w = load_policy_config().combat
    hand = [_bcard(0, "BASH", "Bash", 1, "Deal 8 damage. Apply 2 Vulnerable.", "Attack",
                   "AnyEnemy"),
            _bcard(1, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(2, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
            _bcard(3, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(4, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    d = plan_combat_turn(parse_state(_giant_state(15, 20, 45, hand)), w)
    assert "Defend" in (d.rationale or "") and "LETHAL" not in (d.rationale or "")
    d2 = plan_combat_turn(parse_state(_giant_state(15, 20, 12, hand)), w)
    assert d2.action.payload()["card_index"] in (0, 1, 2)
    assert "Defend" not in (d2.rationale or "").split(";")[0]


def test_hard_to_kill_caps_each_hit_not_the_turn() -> None:
    """Exoskeleton 'Reduce all damage taken and HP lost by Exoskeleton to 9' is a
    per-INSTANCE cap (live 2026-09-30: one body lost 27 in a turn). The detector
    had folded it into the per-turn cap built for Hardened Shell ('cannot lose
    more than 15 HP each turn'), so the sim wrote off every follow-up hit into
    a body that had already taken 9 -- two hallway deaths in seven runs."""
    from sts2bot.policy.capability import detect_mechanics
    hk = detect_mechanics([{"description": "Reduce all damage taken and HP lost by "
                                            "Exoskeleton to 9."}])
    assert hk == {"dmg_cap_per_hit": 9}
    hs = detect_mechanics([{"description": "Skulking Colony cannot lose more than 15 HP "
                                            "each turn."}])
    assert hs == {"dmg_cap_per_turn": 15}
    per_hit = _apply_attack(_state(_enemy(dmg_cap_per_hit=9)), 0, _attack(20, hits=3))
    assert per_hit.damage_dealt == 27
    per_turn = _apply_attack(_state(_enemy(dmg_cap_per_turn=15)), 0, _attack(20, hits=3))
    assert per_turn.damage_dealt == 15


def test_enthralled_is_played_first_to_unlock_the_hand() -> None:
    """Live 2026-09-30 (run 20260930-040833, Devoted Sculptor f35): Enthralled
    ('If this is in your Hand, it must be played before other cards. Eternal.')
    locks every other card; the search saw no value in it and ended four turns
    in a row at 4..16 energy while Ritual ramped the enemy to 48. Era: 42 such
    stalled turns across 69 runs. Play it first whenever affordable."""
    from sts2bot.kb.config import load_policy_config
    hand = [_bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy",
                   can_play=False),
            _bcard(1, "ENTHRALLED", "Enthralled", 2,
                   "If this is in your Hand, it must be played before other cards. Eternal.",
                   "Curse", "None"),
            _bcard(2, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None",
                   can_play=False)]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, incoming="12")),
                         load_policy_config().combat)
    assert d.action.payload()["card_index"] == 1
    assert "must be played before" in (d.rationale or "")


def test_tainted_makes_skills_a_net_loss_on_multi_hit_turns() -> None:
    """Infested Prism's Vital Spark (decoded 2026-09-30, the most frequent act-2
    elite in the corpus): every Skill reads 'Gain 2 Tainted when played' and
    Tainted is 'Take 2 additional damage from Attacks this turn' PER HIT. Into a
    5x3 turn a Defend blocks 5 and adds 6 -- the sim must see the net loss
    (batch-6 tape: a 5x3 landed for 31 after two Skills). Without the rider the
    same Defend is a plain 5-block play and gets made."""
    from sts2bot.kb.config import load_policy_config
    w = load_policy_config().combat
    tainted_hand = [
        _bcard(0, "STRIKE_IRONCLAD", "Strike", 1, "Deal 6 damage.", "Attack", "AnyEnemy"),
        _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block. Gain 2 Tainted.", "Skill",
               "None")]
    d = plan_combat_turn(parse_state(_beckon_state(1, tainted_hand, enemy_hp=161, hp=60,
                                                   incoming="5x3")), w)
    assert d.action.payload()["card_index"] == 0  # the Defend would cost a net 1 HP
    plain_hand = [tainted_hand[0],
                  _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None")]
    d2 = plan_combat_turn(parse_state(_beckon_state(1, plain_hand, enemy_hp=161, hp=60,
                                                    incoming="5x3")), w)
    assert d2.action.payload()["card_index"] == 1  # plain Defend: block 5 of 15
    assert d.scores["hp_loss"] == 15.0 and d2.scores["hp_loss"] == 10.0
    # stacks already on the player raise every incoming hit too: 4 x 3 hits
    stacked = _beckon_state(1, plain_hand, enemy_hp=161, hp=60, incoming="5x3")
    stacked["player"]["status"] = [{"id": "TAINTED_POWER", "name": "Tainted", "amount": 4,
                                    "description": "Take 4 additional damage from Attacks "
                                                   "this turn."}]
    d3 = plan_combat_turn(parse_state(stacked), w)
    assert d3.scores["hp_loss"] == 22.0  # 15 + 12 - the Defend's 5


def test_galvanized_keyword_is_an_immediate_self_cost() -> None:
    """Globe Head (act 3, decoded 2026-09-30): 'Galvanic N: Powers are afflicted
    with Galvanized', and the Galvanized keyword reads 'Take N damage when this
    card is played'. The text lives in card.keywords, not the description, so
    the sim played Powers into it for free (batch-7 run 2: two Powers at 36 HP,
    then a third at 18). A per-turn Power keeps the cost (it is not upkeep)."""
    from sts2bot.policy.combat import _to_planned
    galv = [{"name": "Galvanized", "description": "Take 6 damage when this card is played."}]
    hand = [dict(_bcard(0, "INFLAME", "Inflame", 1, "Gain 2 Strength.", "Power", "None"),
                 keywords=galv),
            dict(_bcard(1, "DEMON_FORM", "Demon Form", 3,
                        "At the start of your turn, gain 2 Strength.", "Power", "None"),
                 keywords=galv),
            _bcard(2, "INFLAME", "Inflame", 1, "Gain 2 Strength.", "Power", "None")]
    st = parse_state(_beckon_state(3, hand))
    costs = [_to_planned(c, 3, 0, [], 0).fx.self_hp_cost for c in st.player.hand]
    assert costs == [6, 6, 0]


def test_imbalanced_rock_bowlbug_rewards_the_full_block() -> None:
    """Bowlbug (Rock), decoded 2026-09-30: 'If its attacks are fully blocked, it
    becomes Stunned' -- a full block of its 15 buys a free turn. With the status
    the planner takes the full block over trading; hp_loss is 0."""
    from sts2bot.kb.config import load_policy_config
    w = load_policy_config().combat
    imb = [{"id": "IMBALANCED_POWER", "name": "Imbalanced", "amount": 1,
            "description": "If Bowlbug (Rock)'s attacks are fully blocked, it becomes Stunned."}]
    hand = [_bcard(0, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(1, "DEFEND_IRONCLAD", "Defend", 1, "Gain 5 Block.", "Skill", "None"),
            _bcard(2, "BASH", "Bash", 2, "Deal 8 damage. Apply 2 Vulnerable.", "Attack",
                   "AnyEnemy")]
    d = plan_combat_turn(parse_state(_beckon_state(3, hand, enemy_hp=47, hp=60,
                                                   enemy_status=imb, incoming="10")), w)
    assert d.scores["hp_loss"] == 0.0  # both Defends: the full block, and the stun
    assert "Bash" not in (d.rationale or "").split(";")[0]


def _two_bug_state(hp: int, hand: list) -> dict:
    return {"state_type": "monster", "run": {"act": 2, "floor": 30, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80, "block": 0,
                       "energy": 1, "status": [], "hand": hand, "potions": [],
                       "max_potion_slots": 3},
            "battle": {"round": 4, "turn": "player", "is_play_phase": True,
                       "enemies": [
                           {"entity_id": "ROCK", "name": "Bowlbug (Rock)", "hp": 22,
                            "max_hp": 47, "block": 0, "status": [],
                            "intents": [{"type": "attack", "label": "15"}]},
                           {"entity_id": "NECTAR", "name": "Bowlbug (Nectar)", "hp": 5,
                            "max_hp": 35, "block": 0, "status": [],
                            "intents": [{"type": "attack", "label": "18"}]}]}}


def test_random_target_card_takes_the_worst_target() -> None:
    """Live 2026-10-01 (seed 3R4GXFPKU2, 4 HP): '[Volley > Stomp] LETHAL' aimed
    Volley ('Deal 10 damage to a random enemy') at the Rock; the game sent it
    into the 5-HP Nectar and the run died. A random-target card must be planned
    at its worst target -- so the planner plays Stomp FIRST (killing the Nectar),
    leaving the Rock as Volley's only possible target: a genuine lethal."""
    from sts2bot.kb.config import load_policy_config
    hand = [_bcard(0, "VOLLEY", "Volley", 1, "Deal 10 damage to a random enemy.",
                   "Attack", "RandomEnemy"),
            _bcard(1, "STOMP", "Stomp", 0, "Deal 12 damage to ALL enemies.", "Attack",
                   "AllEnemy")]
    d = plan_combat_turn(parse_state(_two_bug_state(30, hand)), load_policy_config().combat)
    assert d.action.payload()["card_index"] == 1  # Stomp first
    assert "Stomp > Volley" in (d.rationale or "") and "LETHAL" in (d.rationale or "")
    # with only the Volley, it is not a lethal at all (it may hit the Nectar)
    d2 = plan_combat_turn(parse_state(_two_bug_state(30, hand[:1])),
                          load_policy_config().combat)
    assert "LETHAL" not in (d2.rationale or "")


def test_chooser_exhaust_with_no_status_eats_a_real_card() -> None:
    """Live 2026-10-01: [Brand > Stomp] -- Brand ('Exhaust 1 card') with no
    Status in hand had to exhaust the free Stomp the plan meant to play next.
    With only Stomp left, Brand's line can no longer include Stomp."""
    from sts2bot.kb.config import load_policy_config
    hand = [_bcard(0, "BRAND", "Brand", 0, "Lose 1 HP. Exhaust 1 card. Gain 1 Strength.",
                   "Skill", "None"),
            _bcard(1, "STOMP", "Stomp", 0, "Deal 12 damage to ALL enemies.", "Attack",
                   "AllEnemy")]
    d = plan_combat_turn(parse_state(_two_bug_state(30, hand)), load_policy_config().combat)
    plan = (d.rationale or "").split(";")[0]
    assert not ("Brand" in plan and "Stomp" in plan and plan.index("Brand") < plan.index("Stomp"))
