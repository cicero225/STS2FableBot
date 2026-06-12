"""Tests for the .run history reader and its wiring into the loop outcome."""

import json
import os
import time
from pathlib import Path

from mock_game import FakeClient, build_doc_script

from sts2bot.orchestrator.loop import AgentLoop, LoopConfig
from sts2bot.policy.trivial import TrivialRouter
from sts2bot.runlog.runfile import RunFileSummary, latest_run_summary

SAMPLE_RUN = {
    "acts": ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"],
    "ascension": 0,
    "build_id": "v0.103.3",
    "game_mode": "standard",
    "killed_by_encounter": "ENCOUNTER.NIBBITS_NORMAL",
    "killed_by_event": "NONE.NONE",
    "platform_type": "steam",
    "run_time": 461,
    "schema_version": 9,
    "seed": "0J4Z607V5P",
    "start_time": 1781237135,
    "was_abandoned": False,
    "win": False,
    "map_point_history": [],
    "modifiers": [],
    "players": [],
}


def write_run_file(history_dir: Path, name: str, **overrides) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{name}.run"
    path.write_text(json.dumps({**SAMPLE_RUN, **overrides}), encoding="utf-8")
    return path


def test_run_file_summary_parses(tmp_path: Path) -> None:
    path = write_run_file(tmp_path / "history", "1781237135")
    summary = RunFileSummary.from_file(path)
    assert summary.win is False
    assert summary.seed == "0J4Z607V5P"
    assert summary.build_id == "v0.103.3"
    assert summary.killed_by_encounter == "ENCOUNTER.NIBBITS_NORMAL"


def test_latest_run_summary_respects_since_epoch(tmp_path: Path) -> None:
    history = tmp_path / "history"
    old = write_run_file(history, "old", win=True)
    # backdate the old record well before the cutoff
    past = time.time() - 3600
    os.utime(old, (past, past))
    assert latest_run_summary([history], since_epoch=time.time() - 60) is None
    write_run_file(history, "new", win=False, seed="NEWSEED")
    found = latest_run_summary([history], since_epoch=time.time() - 60)
    assert found is not None and found.seed == "NEWSEED"


def test_event_death_survives_none_none_padding(tmp_path: Path) -> None:
    """Observed live: event deaths pad killed_by_encounter with 'NONE.NONE' (truthy),
    which must not mask the real event killer in the index."""
    import sqlite3

    history = tmp_path / "history"
    write_run_file(
        history,
        "record",
        killed_by_encounter="NONE.NONE",
        killed_by_event="EVENT.DENSE_VEGETATION",
    )
    game = build_doc_script()
    loop = AgentLoop(
        client=FakeClient(game),
        router=TrivialRouter(),
        log_root=tmp_path / "logs",
        config=LoopConfig(poll_interval=0, history_dirs=[history]),
    )
    outcome = loop.play_one_run()
    assert outcome.killed_by_event == "EVENT.DENSE_VEGETATION"
    conn = sqlite3.connect(tmp_path / "logs" / "index.sqlite")
    killed_by = conn.execute("SELECT killed_by FROM runs").fetchone()[0]
    conn.close()
    assert killed_by == "EVENT.DENSE_VEGETATION"


def test_loop_enriches_outcome_from_run_record(tmp_path: Path) -> None:
    history = tmp_path / "history"
    write_run_file(history, "record", win=True, seed="WINSEED")

    game = build_doc_script()
    loop = AgentLoop(
        client=FakeClient(game),
        router=TrivialRouter(),
        log_root=tmp_path / "logs",
        config=LoopConfig(poll_interval=0, history_dirs=[history]),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "completed"
    assert outcome.victory is True  # from the .run record, not the API
    assert outcome.seed == "WINSEED"
    assert outcome.build_id == "v0.103.3"
