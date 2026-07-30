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
