"""Rollout engine (PLAN §5.2 P1): sanity + determinism. Calibration against the
n=292 corpus lives in scripts/calibrate_capability.py, not here."""
from types import SimpleNamespace as NS

from sts2bot.policy.capability import FightEnemy
from sts2bot.policy.rollout import rollout_fight

FX = {
    "STRIKE_IRONCLAD|0": "Deal 6 damage.",
    "STRIKE_IRONCLAD|1": "Deal 9 damage.",
    "DEFEND_IRONCLAD|0": "Gain 5 Block.",
    "BASH|0": "Deal 8 damage. Apply 2 Vulnerable.",
    "BLUDGEON|0": "Deal 32 damage.",
    "SHRUG_IT_OFF|0": "Gain 8 Block. Draw 1 card.",
}


def card(cid, typ="Attack", cost="1", up=False, name=None, desc=None):
    return NS(id=cid, name=name or cid.title(), type=typ, cost=cost,
              is_upgraded=up, description=desc)


def starter():
    return ([card("STRIKE_IRONCLAD")] * 5
            + [card("DEFEND_IRONCLAD", typ="Skill")] * 4
            + [card("BASH", cost="2")])


def test_deterministic_for_same_inputs() -> None:
    deck = starter()
    foe = [FightEnemy(hp=140, dps=17, str_ramp=1)]
    a = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    b = rollout_fight(deck, foe, 70, 80, card_effects=FX)
    assert a == b


def test_starter_loses_to_big_elite_and_built_deck_does_better() -> None:
    foe = [FightEnemy(hp=140, dps=17, str_ramp=1)]
    weak = rollout_fight(starter(), foe, 70, 80, card_effects=FX)
    built = rollout_fight(
        [*starter(), *([card("BLUDGEON", cost="3")] * 3),
         *([card("SHRUG_IT_OFF", typ="Skill")] * 3)],
        foe, 70, 80, card_effects=FX)
    assert built.win_rate >= weak.win_rate
    assert built.exp_end_hp >= weak.exp_end_hp


def test_hand_curse_bleeds_the_rollout() -> None:
    bad_luck = card("BAD_LUCK", typ="Curse", cost="0", name="Bad Luck",
                    desc="Unplayable. At the end of your turn, if this is in your "
                         "Hand, lose 13 HP. Eternal.")
    foe = [FightEnemy(hp=60, dps=8)]
    clean = rollout_fight(starter(), foe, 60, 80, card_effects=FX)
    cursed = rollout_fight([*starter(), bad_luck], foe, 60, 80, card_effects=FX)
    assert cursed.exp_end_hp < clean.exp_end_hp


# ---- phased spawns (Phrog phase 2, 2026-07-30: wrigglers arrive AFTER the parasite dies) ----

def test_dormant_wave_does_not_attack_or_soak_damage_before_spawning() -> None:
    # leader hits for 0; wave-1 bodies hit for 12 each. If waves were concurrent the
    # starter would bleed out; dormant wave means turn-N damage starts only post-kill.
    leader = FightEnemy(hp=1, dps=0)
    wave = [FightEnemy(hp=200, dps=12, wave=1) for _ in range(4)]
    r = rollout_fight(starter(), [leader, *wave], 70, 80, card_effects=FX, max_turns=3)
    # leader dies turn 1, wave spawns with 800 HP nobody can clear in 3 turns -> losses,
    # but the fight must NOT be scored a win at leader-kill (kill-HP includes the wave)
    assert r.win_rate == 0.0


def test_killing_leader_activates_wave_instead_of_winning() -> None:
    leader = FightEnemy(hp=1, dps=0)
    wave = [FightEnemy(hp=4, dps=0, wave=1)]
    r = rollout_fight(starter(), [leader, *wave], 70, 80, card_effects=FX)
    # harmless 5-HP total fight: always a win, but only after clearing BOTH waves
    assert r.win_rate == 1.0


def test_wave_split_prices_phrog_hotter_than_concurrent_split() -> None:
    from sts2bot.policy.capability import elite_fight_members
    bestiary = {"Phrog Parasite": {"hp": [40, 46], "statuses": {}},
                "Wriggler": {"hp": [10, 12], "statuses": {}}}
    members = elite_fight_members(
        "Phrog Parasite", bestiary["Phrog Parasite"], bestiary, dps=12)
    parasite = [m for m in members if m.wave == 0]
    wrigglers = [m for m in members if m.wave == 1]
    assert len(parasite) == 1 and len(wrigglers) == 4
    # phase 1: the parasite alone carries the FULL act estimate (was 12//5 = 2)
    assert parasite[0].dps == 12
    # phase 2: the wave splits the act estimate among its own 4 bodies
    assert all(w.dps == 3 for w in wrigglers)


def test_composition_members_use_their_own_realized_dps_when_harvested() -> None:
    from sts2bot.policy.capability import elite_fight_members
    bestiary = {"Phrog Parasite": {"hp": [40, 46], "statuses": {}},
                "Wriggler": {"hp": [10, 12], "statuses": {}}}
    table = {"Phrog Parasite": {"dps_early": 5.4, "dps_mean": 6.7},
             "Wriggler": {"dps_early": 3.7, "dps_mean": 4.1}}
    members = elite_fight_members("Phrog Parasite", bestiary["Phrog Parasite"],
                                  bestiary, dps=12, dps_table=table)
    # harvested per-body numbers win over the act-estimate split
    assert next(m for m in members if m.wave == 0).dps == 5
    assert all(w.dps == 4 for w in members if w.wave == 1)


# ---- synth bridge v2: Strength re-baked into planner-visible texts (2026-07-30) ----

def test_rebake_strength_adjusts_numeric_damage_only() -> None:
    from sts2bot.policy.rollout import _rebake_strength
    assert _rebake_strength("Deal 6 damage.", 3) == "Deal 9 damage."
    assert _rebake_strength("Deal 6 damage 2 times.", 3) == "Deal 9 damage 2 times."
    assert _rebake_strength("Deal damage equal to your Block.", 3) == \
        "Deal damage equal to your Block."
    assert _rebake_strength("Deal 6 damage.", 0) == "Deal 6 damage."
    # drained past the base: the game floors a hit at 0, so does the re-bake
    assert _rebake_strength("Deal 6 damage.", -9) == "Deal 0 damage."
    # 'Deals N additional...' riders are per-X scaling, NOT a hit — Strength must
    # only land on the primary 'Deal N damage' clause (8 such texts in the catalog)
    assert _rebake_strength(
        "Deal 6 damage. Deals 3 additional damage for each card in your Exhaust Pile.",
        5) == "Deal 11 damage. Deals 3 additional damage for each card in your Exhaust Pile."


def test_synth_state_shows_planner_strength_adjusted_attacks() -> None:
    import random

    from sts2bot.policy.rollout import _build_cards, _RolloutSim, _synth_state
    cards = _build_cards([card("STRIKE_IRONCLAD"), card("DEFEND_IRONCLAD", typ="Skill")],
                         FX)
    sim = _RolloutSim(cards, [FightEnemy(hp=30, dps=5)], 50, 80,
                      random.Random(1), [], {})
    sim.start_turn()
    sim.my_str = 3
    st = _synth_state(sim)
    texts = [c.description for c in st.player.hand]
    assert any("Deal 9 damage" in t for t in texts)      # Strike re-baked
    assert all("Gain 8" not in t or "damage" not in t for t in texts)  # skills untouched


def test_loss_gradient_survives_unwinnable_fights() -> None:
    # KD audit 2026-07-30: on a forecast-lost boss every option used to score end_hp
    # 0 -- exp_enemy_hp_left restores the 'got closer to the kill' gradient drafting
    # needs. A deck with Bludgeons leaves less boss standing than the bare starter.
    boss = [FightEnemy(hp=400, dps=30)]
    weak = rollout_fight(starter(), boss, 60, 80, card_effects=FX)
    strong = rollout_fight([*starter(), *([card("BLUDGEON", cost="3")] * 3)],
                           boss, 60, 80, card_effects=FX)
    assert weak.win_rate == 0.0 and strong.win_rate == 0.0
    assert strong.exp_enemy_hp_left < weak.exp_enemy_hp_left


def test_artifact_charges_eat_vulnerable_in_the_sim() -> None:
    # Aeonglass tape (4 fights, 2026-07-30): she opens with Artifact 3, so early
    # Vulnerable-based plans fizzle -- the +581-peak-then-collapse signature. The
    # live planner already knew; the sim let vuln land turn 1 (optimistic exactly
    # where the fight is hardest). Bash x many vs artifact=1: first vuln eaten.
    from sts2bot.policy.capability import detect_mechanics
    flags = detect_mechanics([{"name": "Artifact", "description": "Negates 3 debuffs."}])
    assert flags.get("artifact") == 3
    # sim: same deck, same boss, artifact 3 vs 0 -- charges must cost win equity
    boss = dict(hp=300, dps=18, str_ramp=2)
    plain = rollout_fight([*starter(), *([card("BASH", cost="2")] * 3)],
                          [FightEnemy(**boss)], 75, 80, card_effects=FX)
    shielded = rollout_fight([*starter(), *([card("BASH", cost="2")] * 3)],
                             [FightEnemy(**boss, artifact=3)], 75, 80, card_effects=FX)
    assert (shielded.win_rate, shielded.exp_end_hp - shielded.exp_enemy_hp_left) <= \
        (plain.win_rate, plain.exp_end_hp - plain.exp_enemy_hp_left)


def test_target_order_changes_outcomes_in_leader_plus_ramp_fights() -> None:
    # Kin shape: big leader + small ramping bodies. "sweep" clears the ramps
    # (shedding their growing dps); "focus" races the big body while they scale.
    # For a low-burst deck the orders are night and day (probe: 1.00 vs 0.00) --
    # which is exactly the signal _fight_plan selects on.
    leader = FightEnemy(hp=90, dps=5)
    ramps = [FightEnemy(hp=12, dps=4, str_ramp=5) for _ in range(2)]
    deck = starter()
    sweep = rollout_fight(deck, [leader, *ramps], 60, 80, card_effects=FX,
                          target_order="sweep")
    focus = rollout_fight(deck, [leader, *ramps], 60, 80, card_effects=FX,
                          target_order="focus")
    assert sweep.win_rate > focus.win_rate + 0.5
