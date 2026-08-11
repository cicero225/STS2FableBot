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


def test_fuzz_rail_auto_savescums_and_hands_back_after_restart() -> None:
    """Owner design 2026-08-10: the rail sends save_and_quit ONCE (run persists,
    Continue restores the fight), holds during the menu transition, and after
    the restart the healthy state marks the fight fuzz-done for normal policy.
    The savescum only fires when this fight HAS fuzzed plays to rewind."""
    r = FuzzRouter()
    ctx = LoopContext()
    # a fuzzed play happens at healthy HP first (something to rewind)
    d0 = r.decide(_combat(hp=60), ctx)
    assert d0.rationale.startswith("FUZZ:")
    # low HP: exactly one save_and_quit, then holds
    d = r.decide(_combat(hp=20), ctx)
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "save_and_quit"
    assert "FUZZ-RAIL" in d.rationale
    w = r.decide(_combat(hp=20), ctx)
    assert isinstance(w, Wait) and "FUZZ-RAIL" in w.reason
    # post-Continue restart (HP restored): fight is fuzz-done -> normal policy
    d2 = r.decide(_combat(hp=60), ctx)
    assert isinstance(d2, (Decision, Wait))
    assert not (getattr(d2, "rationale", "") or "").startswith("FUZZ:")
    assert (getattr(d2, "action", None) is None
            or d2.action.payload()["action"] != "save_and_quit")


def test_fuzz_rail_savescums_when_fight_nearly_won() -> None:
    r = FuzzRouter()
    ctx = LoopContext()
    r.decide(_combat(enemy_hp=60), ctx)  # fuzzed play first
    d = r.decide(_combat(enemy_hp=8), ctx)
    assert isinstance(d, Decision)
    assert d.action.payload()["action"] == "save_and_quit"


def test_fuzz_rail_skips_pointless_savescum_at_fight_entry() -> None:
    """Live 2026-08-10 (run 20260810-201707): a bleeding run entered f38 at 6
    hp; the rail savescummed at r1 with ZERO fuzzed plays -- nothing to rewind
    -- and the pointless Continue hit a resume-load wedge that cost the run.
    Rail rule: no fuzzed plays this fight yet = mark fuzz-done, normal policy,
    NO savescum."""
    r = FuzzRouter()
    ctx = LoopContext()
    d = r.decide(_combat(hp=6), ctx)
    assert (getattr(d, "action", None) is None
            or d.action.payload()["action"] != "save_and_quit")
    assert not (getattr(d, "rationale", "") or "").startswith("FUZZ-RAIL")
    assert 12 in ctx.screen_mem.get("fuzz_done_floors", set())


def test_fuzz_is_deterministic_per_fight() -> None:
    a = FuzzRouter().decide(_combat(), LoopContext())
    b = FuzzRouter().decide(_combat(), LoopContext())
    assert a.action.payload() == b.action.payload()
