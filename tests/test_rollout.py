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
