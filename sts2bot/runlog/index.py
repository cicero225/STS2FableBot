"""SQLite run index: queryable aggregates over all runs (REQUIREMENTS FR-5.2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sts2bot.runlog.logger import RunOutcome

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_dir     TEXT NOT NULL UNIQUE,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    character   TEXT,
    ascension   INTEGER,
    act         INTEGER,
    floor       INTEGER,
    victory     INTEGER,            -- 1/0/NULL(unknown)
    decisions   INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'running',
    error       TEXT
);
"""


class RunIndex:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def start_run(self, run_dir: str, started_at: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (run_dir, started_at) VALUES (?, ?)",
            (run_dir, started_at),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_run(self, run_id: int, ended_at: str, outcome: RunOutcome) -> None:
        self._conn.execute(
            """UPDATE runs SET ended_at=?, character=?, ascension=?, act=?, floor=?,
               victory=?, decisions=?, status=?, error=? WHERE id=?""",
            (
                ended_at,
                outcome.character,
                outcome.ascension,
                outcome.act,
                outcome.floor,
                None if outcome.victory is None else int(outcome.victory),
                outcome.decisions,
                outcome.status,
                outcome.error,
                run_id,
            ),
        )
        self._conn.commit()

    def summary(self) -> list[tuple]:
        """Win-rate rollup by character/ascension (None victory rows excluded from rate)."""
        return self._conn.execute(
            """SELECT character, ascension, COUNT(*) AS runs,
                      SUM(COALESCE(victory, 0)) AS wins
               FROM runs WHERE status='completed'
               GROUP BY character, ascension
               ORDER BY character, ascension"""
        ).fetchall()
