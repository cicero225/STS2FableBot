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
