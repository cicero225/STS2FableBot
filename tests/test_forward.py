"""Multiturn feasibility oracle (P3) -- primitives + mode selection against
the wiki-verified Matriarch and Kaiser scripts."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

from sts2bot.policy.forward import (
    FIGHT_MODE_TABLE,
    choose_mode,
    hp_at,
    incoming_by_turn,
    kill_eta,
    throughput,
)


def _card(cid, cost, desc):
    return NS(id=cid, cost=cost, description=desc, is_upgraded=False)


def _player(hand=(), draw=(), discard=(), hp=70, block=0, energy=3):
    return NS(hand=list(hand), draw_pile=list(draw), discard_pile=list(discard),
              hp=hp, block=block, energy=energy, max_energy=energy)


STRIKE = _card("STRIKE_IRONCLAD", "1", "Deal 6 damage.")
BLUDGEON = _card("BLUDGEON", "3", "Deal 32 damage.")
DEFEND = _card("DEFEND_IRONCLAD", "1", "Gain 5 Block.")


def test_throughput_uses_real_pile_and_flags_exact_tail() -> None:
    p = _player(hand=[STRIKE] * 2, draw=[BLUDGEON, DEFEND], discard=[STRIKE] * 3)
    tp = throughput(p)
    assert tp.dmg_mean > 0 and tp.blk_mean > 0
    assert tp.dmg_p25 < tp.dmg_mean
    assert tp.exact_tail  # 2-card draw pile: owner's <6 exact-hand regime


def test_kill_eta_scales_with_hp() -> None:
    tp = throughput(_player(hand=[BLUDGEON], draw=[STRIKE] * 4))
    m1, p1 = kill_eta(30, tp)
    m2, p2 = kill_eta(90, tp)
    assert m2 > m1 and p2 > p1 and p1 >= m1


def test_incoming_matches_wiki_verified_rocket_script() -> None:
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    inc = incoming_by_turn(scripts["Rocket"], current_round=0, horizon=5)
    # T1 Reticle 3, T2 Beam 18, T3 Buff (0), T4 LASER 33, T5 Recharge (0)
    assert inc[0] == 3 and inc[1] == 18
    assert inc[2] == 0.0
    assert inc[3] >= 31  # the Laser
    assert inc[4] == 0.0


def test_hp_trajectory_race_vs_defend() -> None:
    inc = [3, 18, 0, 33]
    race = hp_at(70, 0, inc, block_per_turn=12, defend_frac=0.0)
    turtle = hp_at(70, 0, inc, block_per_turn=12, defend_frac=1.0)
    assert race[-1] < turtle[-1]
    assert race[-1] == 70 - 3 - 18 - 33


def test_choose_mode_matriarch_sleep_window() -> None:
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    boss = NS(name="Lagavulin Matriarch", entity_id="LM_0", hp=320, block=0, asleep=True)
    plan = choose_mode([boss], _player(hand=[STRIKE] * 5), scripts, current_round=1)
    assert plan.mode == "setup_window"
    assert plan.window_turns == 3


def test_choose_mode_kaiser_feasibility_flip() -> None:
    """The owner's Kaiser rule end to end: a burst deck races Rocket by T4; a
    starter deck reads infeasible and defends the Laser deadline instead."""
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    # REAL fight shape: two claws only, no body named Kaiser (wiki-verified)
    rocket = NS(name="Rocket", entity_id="ROCKET_0", hp=60, block=0)
    crusher = NS(name="Crusher", entity_id="CRUSHER_0", hp=209, block=0)
    burst = _player(hand=[BLUDGEON] * 3, draw=[BLUDGEON] * 3, hp=75)
    plan = choose_mode([crusher, rocket], burst, scripts)
    assert plan.mode == "race" and plan.target == "ROCKET_0"
    weak = _player(hand=[STRIKE] * 3, draw=[STRIKE, DEFEND, DEFEND], hp=75)
    rocket_fat = NS(name="Rocket", entity_id="ROCKET_0", hp=199, block=0)
    plan2 = choose_mode([crusher, rocket_fat], weak, scripts)
    assert plan2.mode == "defend_deadline" and plan2.deadline_turn == 4
    assert plan2.detail.get("cycle") == 5  # Laser recurs T4/T9/T14


def test_choose_mode_queen_guard_break() -> None:
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    queen = NS(name="Queen", entity_id="QUEEN_0", hp=391, block=0)
    torch = NS(name="Torch Head Amalgam", entity_id="TORCH_0", hp=190, block=0)
    plan = choose_mode([queen, torch], _player(hand=[STRIKE] * 5), scripts)
    assert plan.mode == "guard_break" and plan.target == "TORCH_0"


def test_mode_table_tbd_rows_flagged() -> None:
    # anything not wiki-verified must say TBD so the owner review catches it
    for k in ("KNOWLEDGE DEMON", "TEST SUBJECT", "CEREMONIAL BEAST", "AEONGLASS"):
        assert "TBD" in FIGHT_MODE_TABLE[k]["notes"]
