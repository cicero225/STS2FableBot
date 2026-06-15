"""End-to-end: trivial policy completes a full scripted run, with full logging."""

import json
import sqlite3
from pathlib import Path

from mock_game import FakeClient, build_doc_script

from sts2bot.orchestrator.loop import AgentLoop, LoopConfig
from sts2bot.policy.trivial import TrivialRouter

COMPENDIUM = {
    "profile_id": 2,
    "sections": {
        "run_history": {
            "status": "exposed",
            "entry_count": 1,
            "entries": [
                {
                    "id": "1",
                    "run_id": "modded:profile2:1",
                    "players": [{"id": 1, "character": "CHARACTER.IRONCLAD"}],
                    "ascension": 0,
                    "win": False,
                    "run_time": 1234,
                }
            ],
        }
    },
}


def run_scripted(tmp_path: Path):
    game = build_doc_script()
    client = FakeClient(game, compendium=COMPENDIUM)
    loop = AgentLoop(
        client=client,
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, character="IRONCLAD"),
    )
    return game, loop.play_one_run()


def test_full_scripted_run_completes(tmp_path: Path) -> None:
    game, outcome = run_scripted(tmp_path)

    assert game.current == "menu_end"
    assert outcome.status == "completed"
    assert outcome.victory is False  # from scripted compendium run history
    assert outcome.character == "The Ironclad"
    assert outcome.act == 2 and outcome.floor == 24  # from the game_over state
    assert outcome.decisions == 19
    # every scripted transition was exercised exactly once
    assert [s for s, _ in game.history][:4] == [
        "menu_main",
        "menu_sp",
        "char_select",
        "char_select_picked",
    ]
    assert len(game.history) == 19


def test_run_logs_written(tmp_path: Path) -> None:
    run_scripted(tmp_path)

    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    lines = (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    actions = [r for r in records if r["action"] is not None]
    assert len(actions) == 19
    assert all(r["result"]["status"] == "ok" for r in actions)
    assert all(r["rationale"] for r in records)
    # decision records carry the full state for replay (C6 / FR-5.3)
    combat_records = [r for r in actions if r["state_type"] == "monster"]
    assert combat_records and "player" in combat_records[0]["state"]
    assert actions[-1]["action"] == {"action": "menu_select", "option": "main_menu"}

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["outcome"]["status"] == "completed"
    assert meta["ended_at"] >= meta["started_at"]

    conn = sqlite3.connect(tmp_path / "index.sqlite")
    rows = conn.execute(
        "SELECT character, ascension, victory, decisions, status FROM runs"
    ).fetchall()
    conn.close()
    assert rows == [("The Ironclad", 0, 0, 19, "completed")]


def test_unexpected_action_errors_halt_the_loop(tmp_path: Path) -> None:
    game = build_doc_script()
    # Sabotage: remove the transition out of the rest site so every action errors.
    game.transitions["rest"] = []
    client = FakeClient(game, compendium=COMPENDIUM)
    loop = AgentLoop(
        client=client,
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, error_streak_limit=3),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "error"
    assert outcome.error is not None and "consecutive action errors" in outcome.error


def test_pause_for_resume_returns_when_signal_present(tmp_path: Path) -> None:
    """The resume mechanism: _pause_for_resume blocks until the signal file appears,
    then consumes it. With the signal already present it returns immediately."""
    sig = tmp_path / "resume.signal"
    sig.write_text("go", encoding="utf-8")
    loop = AgentLoop(
        client=FakeClient(build_doc_script()),
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, resume_signal_path=sig),
    )
    loop._pause_for_resume(5)  # returns at once (signal present)
    assert not sig.exists()  # consumed
