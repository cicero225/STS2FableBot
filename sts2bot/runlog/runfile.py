"""Reader for the game's own run-history records (saves/history/*.run).

The game writes a rich JSON record when a run ends (win flag, seed, build_id,
killed_by, full per-floor history). It is the authoritative source for outcomes —
the player can see all of it in-game, so reading it is C3-clean. Modded play uses
the `modded/` save scope, so these globs can never touch vanilla profiles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RunFileSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    win: bool | None = None
    seed: str | None = None
    build_id: str | None = None
    ascension: int | None = None
    game_mode: str | None = None
    killed_by_encounter: str | None = None
    killed_by_event: str | None = None
    run_time: int | None = None
    was_abandoned: bool | None = None
    start_time: int | None = None
    schema_version: int | None = None

    @classmethod
    def from_file(cls, path: Path) -> RunFileSummary:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def default_save_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    root = Path(appdata) / "SlayTheSpire2" / "steam"
    return root if root.is_dir() else None


def discover_history_dirs(save_root: Path | None = None) -> list[Path]:
    """All modded-scope history dirs across Steam accounts/profiles on this machine."""
    root = save_root or default_save_root()
    if root is None:
        return []
    return sorted(root.glob("*/modded/profile*/saves/history"))


def newest_record_mtime(history_dirs: list[Path]) -> float:
    """Snapshot the newest .run mtime (loop start uses this as a strict watermark)."""
    mtimes = [f.stat().st_mtime for d in history_dirs for f in d.glob("*.run")]
    return max(mtimes, default=0.0)


def latest_run_summary(
    history_dirs: list[Path],
    since_epoch: float | None = None,
    newer_than_mtime: float | None = None,
) -> RunFileSummary | None:
    """Newest .run record, filtered by write time.

    `newer_than_mtime` is the strict watermark (snapshot taken at loop start) —
    preferred, because grace-window matching once attributed the previous run's
    record to an errored run that never finished. `since_epoch` (with grace)
    remains for callers without a watermark.
    """
    candidates = [f for d in history_dirs for f in d.glob("*.run")]
    if newer_than_mtime is not None:
        candidates = [f for f in candidates if f.stat().st_mtime > newer_than_mtime]
    elif since_epoch is not None:
        candidates = [f for f in candidates if f.stat().st_mtime >= since_epoch - 5]
    if not candidates:
        return None
    newest = max(candidates, key=lambda f: f.stat().st_mtime)
    try:
        return RunFileSummary.from_file(newest)
    except (json.JSONDecodeError, OSError):
        return None
