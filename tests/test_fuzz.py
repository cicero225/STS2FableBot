"""Prediction-fuzzing router (owner experiment, PLAN 2026-08-06): random legal
plays with logged predictions, a savescum-pause rail, and normal-policy
delegation everywhere else."""

from sts2bot.client.models import parse_state
from sts2bot.policy.base import Decision, LoopContext, Wait
from sts2bot.policy.fuzz import FuzzRouter


def _combat(hp=60, enemy_hp=60, energy=3, floor=12):
    return parse_state({
        "state_type": "monster", "run": {"act": 1, "floor": floor, "ascension": 0},
        "player": {"character": "The Ironclad", "hp": hp, "max_hp": 80, "block": 0,
                   "energy": energy, "status": [],
                   "hand": [
                       {"index": 0, "id": "STRIKE_IRONCLAD", "name": "Strike",
                        "type": "Attack", "cost": "1", "description": "Deal 6 damage.",
                        "can_play": True, "target_type": "AnyEnemy"},
                       {"index": 1, "id": "DEFEND_IRONCLAD", "name": "Defend",
                        "type": "Skill", "cost": "1", "description": "Gain 5 Block.",
                        "can_play": True, "target_type": "None"}],
                   "potions": [], "max_potion_slots": 3},
        "battle": {"round": 2, "turn": "player", "is_play_phase": True,
                   "enemies": [{"entity_id": "e0", "name": "Byrd", "hp": enemy_hp,
                                "max_hp": 60, "block": 0, "status": [],
                                "intents": [{"type": "attack", "label": "8"}]}]},
    })


def test_fuzz_plays_randomly_with_logged_prediction() -> None:
    d = FuzzRouter().decide(_combat(), LoopContext())
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "play_card"
    assert d.rationale.startswith("FUZZ:") and "PRED" in d.rationale


def test_fuzz_rail_pauses_at_low_hp_and_hands_back_after_savescum() -> None:
    r = FuzzRouter()
    ctx = LoopContext()
    # low HP: pause, MANUAL wait, never act
    w = r.decide(_combat(hp=20), ctx)
    assert isinstance(w, Wait) and w.reason.startswith("MANUAL: FUZZ-PAUSE")
    # savescum restored HP: this fight is fuzz-done -> normal policy acts
    d = r.decide(_combat(hp=60), ctx)
    assert isinstance(d, (Decision, Wait))
    assert not (getattr(d, "rationale", "") or "").startswith("FUZZ:")


def test_fuzz_rail_pauses_when_fight_nearly_won() -> None:
    w = FuzzRouter().decide(_combat(enemy_hp=8), LoopContext())
    assert isinstance(w, Wait) and "FUZZ-PAUSE" in w.reason


def test_fuzz_is_deterministic_per_fight() -> None:
    a = FuzzRouter().decide(_combat(), LoopContext())
    b = FuzzRouter().decide(_combat(), LoopContext())
    assert a.action.payload() == b.action.payload()
