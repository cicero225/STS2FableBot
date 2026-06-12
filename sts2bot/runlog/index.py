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
    error       TEXT,
    seed        TEXT,
    build_id    TEXT,
    killed_by   TEXT
);
"""

# columns added after the first release; applied idempotently to old DBs
_MIGRATION_COLUMNS = {
    "seed": "TEXT",
    "build_id": "TEXT",
    "killed_by": "TEXT",
    "policy": "TEXT",
    "config_hash": "TEXT",
}


class RunIndex:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(runs)")}
        for column, sql_type in _MIGRATION_COLUMNS.items():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {sql_type}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def start_run(
        self,
        run_dir: str,
        started_at: str,
        policy: str | None = None,
        config_hash: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (run_dir, started_at, policy, config_hash) VALUES (?, ?, ?, ?)",
            (run_dir, started_at, policy, config_hash),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_run(self, run_id: int, ended_at: str, outcome: RunOutcome) -> None:
        def clean(value: str | None) -> str | None:
            return None if value in (None, "NONE.NONE") else value

        # the game pads the unused killer slot with "NONE.NONE" (truthy!), so clean
        # each field before coalescing or an event death gets discarded
        killed_by = clean(outcome.killed_by_encounter) or clean(outcome.killed_by_event)
        self._conn.execute(
            """UPDATE runs SET ended_at=?, character=?, ascension=?, act=?, floor=?,
               victory=?, decisions=?, status=?, error=?, seed=?, build_id=?, killed_by=?
               WHERE id=?""",
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
                outcome.seed,
                outcome.build_id,
                killed_by,
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
