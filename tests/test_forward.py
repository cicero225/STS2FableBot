"""Multiturn feasibility oracle (P3) -- primitives + mode selection against
the wiki-verified Matriarch and Kaiser scripts."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

from sts2bot.policy.forward import (
    FIGHT_MODE_TABLE,
    canonical_enemy_name,
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


def test_canonical_enemy_name_strips_specimen_suffix() -> None:
    """Test Subject rolls a flavor specimen number per encounter ('#C137'), which
    fragmented the harvest into 113 one-fight keys and broke live script lookup."""
    assert canonical_enemy_name("Test Subject #C137") == "Test Subject"
    assert canonical_enemy_name("Test Subject") == "Test Subject"
    assert canonical_enemy_name("Rocket") == "Rocket"  # no false trims
    assert canonical_enemy_name(None) == ""
    # the rebuilt corpus must be consolidated: one entry, no fragments
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    assert "Test Subject" in scripts
    assert scripts["Test Subject"]["n_fights"] > 100
    assert not any("#C" in k for k in scripts)


def test_mode_table_tbd_rows_flagged() -> None:
    # The table is fully wiki-verified as of 2026-08-18 (Ceremonial Beast was
    # the last TBD). Any FUTURE unverified row must carry "TBD" in its notes
    # AND be whitelisted here so owner review catches it.
    known_tbd: set[str] = set()
    for k, rule in FIGHT_MODE_TABLE.items():
        if "TBD" in (rule.get("notes") or ""):
            assert k in known_tbd, f"unreviewed TBD row {k} not whitelisted"


def test_choose_mode_test_subject_burst_window() -> None:
    """Owner green-lit 2026-08-18: P3 intangible turns are block/setup turns, open
    turns unload. The live Intangible status is the ONLY parity source (the
    period-2 intangible drifts under the 3-move cycle). Specimen suffix on the
    live name must not break table matching."""
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    hand = [STRIKE] * 5
    ts = NS(name="Test Subject #C42", entity_id="TS_0", hp=280, block=0,
            intangible=False)
    plan = choose_mode([ts], _player(hand=hand), scripts)
    assert plan.mode == "burst_window" and plan.detail["attack_now"] is True
    assert plan.detail["staged"] and plan.detail["wipe_hp"] > 0

    ts_wall = NS(name="Test Subject #C42", entity_id="TS_0", hp=280, block=0,
                 intangible=True)
    plan2 = choose_mode([ts_wall], _player(hand=hand), scripts)
    assert plan2.mode == "burst_window" and plan2.detail["attack_now"] is False


def test_setup_then_burst_banks_early_and_flips_late() -> None:
    """Owner answers 2026-08-18: KD (setup_burst row) banks a cheap early turn
    (big HP, kill far) as mode=setup_turn, flips to race once the hand can dent
    half the remaining HP within 2 ETA turns, and never banks below 15 hp."""
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    kd_full = NS(name="Knowledge Demon", entity_id="KD_0", hp=379, block=0)
    # early: full boss, REAL throughput (clears KD's net-of-Ponder clock),
    # kill still far -> bank the turn
    early = _player(hand=[BLUDGEON] * 2 + [STRIKE, DEFEND, DEFEND],
                    draw=[BLUDGEON] * 3 + [STRIKE] * 2, hp=70, energy=5)
    plan = choose_mode([kd_full], early, scripts)
    assert plan.mode == "setup_turn", plan.rationale

    # late: boss nearly dead, hand dents half of what remains -> burst-flip
    kd_low = NS(name="Knowledge Demon", entity_id="KD_0", hp=30, block=0)
    burst = _player(hand=[BLUDGEON, STRIKE, STRIKE],
                    draw=[STRIKE, DEFEND] * 3, hp=70, energy=5)
    plan2 = choose_mode([kd_low], burst, scripts)
    assert plan2.mode == "race" and "burst-flip" in plan2.rationale

    # low player HP: never bank a turn below the absolute floor
    desperate = _player(hand=[BLUDGEON] * 2 + [STRIKE, DEFEND, DEFEND],
                        draw=[BLUDGEON] * 3 + [STRIKE] * 2, hp=12, energy=5)
    plan3 = choose_mode([kd_full], desperate, scripts)
    assert plan3.mode == "race" and "unsafe" in plan3.rationale

    # scope (owner Q2): Matriarch awake has NO setup_burst flag -> plain race
    mat = NS(name="Lagavulin Matriarch", entity_id="M_0", hp=300, block=0,
             asleep=False)
    plan4 = choose_mode([mat], early, scripts)
    assert plan4.mode == "race" and "table default" in plan4.rationale


def test_setup_gate_trusts_live_intent_over_script() -> None:
    """Queen f48 (2026-08-19, sentinel catch): the harvested script blends
    unbuffed turns, so her awakened 75-damage beat read as coverable at 58 hp
    and a 'setup' turn went 58->3. The live intent is ground truth for THIS
    turn and must override the forecast."""
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    hand = [STRIKE] * 3 + [DEFEND] * 2
    p = _player(hand=hand, draw=[STRIKE, DEFEND] * 3, hp=58)
    quiet = NS(name="Queen", entity_id="QUEEN_0", hp=383, block=0, incoming=6)
    plan = choose_mode([quiet], p, scripts)
    assert plan.mode == "setup_turn", plan.rationale
    buffed = NS(name="Queen", entity_id="QUEEN_0", hp=383, block=0, incoming=75)
    plan2 = choose_mode([buffed], p, scripts)
    assert plan2.mode == "race" and "unsafe" in plan2.rationale, plan2.rationale


def test_hopeless_bank_races_when_heals_outrun_throughput() -> None:
    """Owner GO 2026-08-20 (sentinel 11/12 KD): the setup ETA runs NET of the
    boss's heal rate. A deck Ponder out-heals must race the kill tail, never
    bank; a deck that clears the net clock still banks early turns."""
    scripts = json.loads(Path("data/move_scripts.json").read_text(encoding="utf-8"))
    kd = NS(name="Knowledge Demon", entity_id="KD_0", hp=379, block=0)
    # weak deck: p25 throughput barely above (or under) the 7.5/turn heal
    weak = _player(hand=[STRIKE] * 2 + [DEFEND] * 3,
                   draw=[DEFEND] * 5 + [STRIKE], hp=70)
    plan = choose_mode([kd], weak, scripts)
    assert plan.mode == "race" and "hopeless bank" in plan.rationale, plan.rationale
    # strong deck: net clock fine -> still a setup turn early
    strong = _player(hand=[BLUDGEON] * 2 + [STRIKE, DEFEND, DEFEND],
                     draw=[BLUDGEON] * 3 + [STRIKE] * 2, hp=70, energy=5)
    plan2 = choose_mode([kd], strong, scripts)
    assert plan2.mode == "setup_turn", plan2.rationale
