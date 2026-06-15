"""Tests for per-run modded-profile backups (sts2bot/runlog/saves.py)."""

import zipfile
from pathlib import Path

from sts2bot.runlog.saves import (
    active_saves_dir,
    backup_active_profile,
    snapshot_saves,
)


def make_profile(root: Path, scope: str, profile: str, run_mtime: float | None = None) -> Path:
    """Build a fake .../steam/<acc>/<scope>/<profile>/saves/{progress.save,history/} tree.
    Returns the history dir (what discover_history_dirs yields)."""
    saves = root / "steam" / "ACC" / scope / profile / "saves"
    (saves / "history").mkdir(parents=True, exist_ok=True)
    (saves / "progress.save").write_bytes(b"unlocks-and-stats")
    (saves / "current_run.save").write_bytes(b"mid-run")
    run = saves / "history" / "123.run"
    run.write_text("{}", encoding="utf-8")
    if run_mtime is not None:
        import os

        os.utime(run, (run_mtime, run_mtime))
    return saves / "history"


def test_active_saves_dir_picks_newest_run(tmp_path: Path) -> None:
    h1 = make_profile(tmp_path, "modded", "profile1", run_mtime=1000.0)
    h2 = make_profile(tmp_path, "modded", "profile2", run_mtime=2000.0)
    active = active_saves_dir([h1, h2])
    assert active == h2.parent  # the saves/ dir of the newer profile
    assert active.parent.name == "profile2"


def test_snapshot_excludes_history_and_keeps_progress(tmp_path: Path) -> None:
    hist = make_profile(tmp_path, "modded", "profile1")
    saves = hist.parent
    dest = tmp_path / "snaps"
    zip_path = snapshot_saves(saves, dest, keep=50)
    assert zip_path is not None and zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert "progress.save" in names
    assert "current_run.save" in names
    assert not any("history" in n for n in names)  # run records live in our own logs
    assert zip_path.name.startswith("modded-profile1_")


def test_snapshot_rotates_to_keep(tmp_path: Path) -> None:
    hist = make_profile(tmp_path, "modded", "profile1")
    saves = hist.parent
    dest = tmp_path / "snaps"
    for _ in range(5):
        snapshot_saves(saves, dest, keep=3)
    assert len(list(dest.glob("modded-profile1_*.zip"))) == 3


def test_snapshot_missing_dir_returns_none(tmp_path: Path) -> None:
    assert snapshot_saves(tmp_path / "nope", tmp_path / "snaps") is None


def test_backup_active_profile_roundtrip(tmp_path: Path) -> None:
    h1 = make_profile(tmp_path, "modded", "profile1", run_mtime=1000.0)
    h2 = make_profile(tmp_path, "modded", "profile2", run_mtime=2000.0)
    dest = tmp_path / "snaps"
    out = backup_active_profile([h1, h2], dest, keep=10)
    assert out is not None
    assert out.name.startswith("modded-profile2_")  # the active (newest-run) profile
