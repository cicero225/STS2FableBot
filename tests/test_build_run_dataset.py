"""Stage 0 dataset builder (scripts/build_run_dataset.py) against synthetic runs.

Mock-first per CLAUDE.md: a hand-built run log exercising every table — draft,
event, rest, two fights (one survived with a rewards closer, one boss death at
end-of-log), map boss identity, combat wait records, and an outcome-less run
(killed mid-batch) that must yield outcome_valid=False rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_run_dataset import build, parse_run


def _rec(seq, stype, state=None, action=None, rationale="", scores=None):
    return {"seq": seq, "ts": "2026-08-27T00:00:00+00:00", "t": 1.0,
            "state_type": stype, "state": {"state_type": stype, **(state or {})},
            "action": action, "rationale": rationale, "scores": scores,
            "result": None}


def _player(hp, max_hp=80, floor=1, act=1, deck=None, gold=50):
    return {
        "run": {"act": act, "floor": floor, "ascension": 0},
        "player": {
            "character": "The Ironclad", "hp": hp, "max_hp": max_hp,
            "gold": gold, "status": [], "potions": [],
            "deck": deck or [
                {"id": "STRIKE_IRONCLAD", "is_upgraded": False},
                {"id": "BASH", "is_upgraded": True},
            ],
            "relics": [{"id": "BURNING_BLOOD"}],
        },
    }


def _battle(hp, floor, rnd, act=1, enemies=None):
    st = _player(hp, floor=floor, act=act)
    st["battle"] = {
        "round": rnd, "turn": 1, "is_play_phase": True,
        "enemies": enemies or [
            {"id": "SHRINKER_BEETLE_0", "name": "Shrinker Beetle",
             "hp": 30, "max_hp": 30},
        ],
    }
    return st


def _write_run(root: Path, name: str, meta: dict, records: list[dict]) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "decisions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return d


def _loss_run(root: Path) -> Path:
    map_state = _player(80, floor=0)
    map_state["map"] = {"boss": {"id": "VANTOM_BOSS", "name": "Vantom"},
                        "nodes": []}
    draft_state = _player(80, floor=1)
    draft_state["card_reward"] = {"can_skip": True, "cards": [
        {"id": "INFERNO", "index": 0, "is_upgraded": False,
         "type": "Power", "rarity": "Uncommon", "cost": "1"},
        {"id": "TRUE_GRIT", "index": 1, "is_upgraded": False,
         "type": "Skill", "rarity": "Common", "cost": "1"},
        {"id": "UPPERCUT", "index": 2, "is_upgraded": True,
         "type": "Attack", "rarity": "Uncommon", "cost": "2"},
    ]}
    event_state = _player(76, floor=3)
    event_state["event"] = {
        "event_id": "E1", "event_name": "Ancient of Blades", "is_ancient": True,
        "options": [
            {"index": 0, "title": "Blessing", "description": "Gain a relic.",
             "is_proceed": False},
            {"index": 1, "title": "Leave", "description": "",
             "is_proceed": True},
        ],
    }
    rest_state = _player(70, floor=4)
    rest_state["rest_site"] = {"options": [
        {"index": 0, "id": "HEAL", "name": "Rest"},
        {"index": 1, "id": "SMITH", "name": "Smith"},
    ], "can_proceed": False}
    records = [
        _rec(1, "map", map_state, {"action": "choose_map_node", "index": 0}),
        _rec(2, "card_reward", draft_state,
             {"action": "select_card_reward", "card_index": 2},
             rationale="take Uppercut+", scores={"Uppercut": 9.0}),
        # combat wait record (slim state, no action) must be skipped harmlessly
        _rec(3, "monster", None, None, rationale="wait: combat loading"),
        _rec(4, "monster", _battle(80, 2, 1),
             {"action": "play_card", "card_index": 0}),
        _rec(5, "monster", _battle(74, 2, 2),
             {"action": "play_card", "card_index": 1}),
        _rec(6, "rewards", _player(72, floor=2),
             {"action": "proceed"}),
        _rec(7, "event", event_state,
             {"action": "choose_event_option", "index": 0},
             rationale="relic > nothing"),
        _rec(8, "rest_site", rest_state,
             {"action": "choose_rest_option", "index": 0},
             rationale="rest at 87% HP"),
        _rec(9, "boss", _battle(60, 16, 1, enemies=[
            {"id": "VANTOM_BOSS_0", "name": "Vantom", "hp": 250, "max_hp": 250},
        ]), {"action": "play_card", "card_index": 0}),
        _rec(10, "boss", _battle(31, 16, 3, enemies=[
            {"id": "VANTOM_BOSS_0", "name": "Vantom", "hp": 120, "max_hp": 250},
        ]), {"action": "end_turn"}),
        _rec(11, "game_over", None, None),
    ]
    meta = {
        "started_at": "2026-08-27T00:00:00+00:00", "policy": "standard",
        "config_hash": "cafe01234567",
        "outcome": {
            "status": "completed", "victory": False,
            "character": "The Ironclad", "ascension": 0, "act": 1, "floor": 16,
            "decisions": 11, "seed": "TESTSEED", "build_id": "v0.107.1",
            "killed_by_encounter": "ENCOUNTER.VANTOM_BOSS",
            "killed_by_event": "NONE.NONE", "was_abandoned": False,
        },
    }
    return _write_run(root, "20260827-000000_ironclad", meta, records)


def test_loss_run_tables(tmp_path):
    rows = parse_run(_loss_run(tmp_path))

    run = rows["runs"][0]
    assert run["outcome_valid"] is True and run["victory"] is False
    assert run["boss_by_act"] == {"1": "Vantom"}
    assert run["killed_by"] == "VANTOM_BOSS"
    assert run["n_fights"] == 2

    f1, f2 = rows["fights"]
    assert f1["floor"] == 2 and not f1["is_boss"]
    assert f1["hp_start"] == 80 and f1["hp_end"] == 72 and f1["hp_delta"] == -8
    assert f1["rounds"] == 2 and f1["n_actions"] == 2 and f1["closed"]
    assert f1["enemies"] == ["Shrinker Beetle"]
    assert f2["is_boss"] and f2["hp_start"] == 60 and f2["hp_end"] == 0
    assert f2.get("died_here") is True

    (d,) = rows["drafts"]
    assert d["picked"] == "UPPERCUT+" and d["picked_index"] == 2
    assert [o["key"] for o in d["offers"]] == \
        ["INFERNO", "TRUE_GRIT", "UPPERCUT+"]
    assert d["deck"] == ["STRIKE_IRONCLAD", "BASH+"]
    assert d["act_boss"] == "Vantom"
    assert d["hp_boss_entry"] == 60
    assert d["beat_act_boss"] is False
    assert d["floors_survived"] == 15
    # next fights after the draft: floor-2 (-8) then boss (0-60 = -60)
    assert d["hp_delta_next3"] == -68
    assert d["config_hash"] == "cafe01234567"
    assert d["bot_scores"] == {"Uppercut": 9.0}

    (e,) = rows["events"]
    assert e["event_name"] == "Ancient of Blades" and e["is_ancient"] is True
    assert e["picked_title"] == "Blessing"
    # event sits after the first fight: only the boss bleed remains
    assert e["hp_delta_next3"] == -60

    (rst,) = rows["rests"]
    assert rst["picked"] == "HEAL" and rst["options"] == ["HEAL", "SMITH"]


def test_outcomeless_run_is_flagged_invalid(tmp_path):
    records = [
        _rec(1, "card_reward",
             {**_player(80, floor=1),
              "card_reward": {"can_skip": True, "cards": [
                  {"id": "INFERNO", "index": 0, "is_upgraded": False}]}},
             {"action": "select_card_reward", "card_index": 0}),
        _rec(2, "monster", _battle(80, 2, 1),
             {"action": "play_card", "card_index": 0}),
    ]
    meta = {"started_at": "2026-08-27T01:00:00+00:00", "policy": "standard",
            "config_hash": "dead00000000", "outcome": None}
    rows = parse_run(_write_run(tmp_path, "20260827-010000_ironclad",
                                meta, records))
    assert rows["runs"][0]["outcome_valid"] is False
    (d,) = rows["drafts"]
    assert d["outcome_valid"] is False and d["victory"] is None
    assert d["floors_survived"] is None and d["beat_act_boss"] is None
    # fight left open by the mid-run kill: closed with last seen hp, not 0
    (f,) = rows["fights"]
    assert f["hp_end"] == 80 and not f.get("died_here")


def test_build_writes_tables_and_manifest(tmp_path):
    runs = tmp_path / "runs"
    _loss_run(runs)
    out = tmp_path / "datasets"
    manifest = build(runs, out)
    assert manifest["rows"] == {
        "runs": 1, "drafts": 1, "events": 1, "rests": 1, "fights": 2}
    assert manifest["parse_errors"] == []
    for t in ("runs", "drafts", "events", "rests", "fights"):
        lines = (out / f"{t}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == manifest["rows"][t]
        json.loads(lines[0])
