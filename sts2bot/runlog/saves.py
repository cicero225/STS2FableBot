"""Lightweight per-run backups of the bot's modded save profile (REQUIREMENTS C1).

Steam Cloud reshuffled the modded profiles once (2026-06-14), which is why this
exists: after every run we snapshot the active modded profile's live save files
(unlocks/stats/current_run — NOT the bulky `history/`, which our own run logs
already capture), into a rotating local store. `scripts/restore_saves.py` puts one
back. The full-tree `scripts/backup_saves.py` remains the comprehensive belt; this
is the cheap per-run suspenders.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


def active_saves_dir(history_dirs: list[Path]) -> Path | None:
    """The modded profile's `saves/` dir whose `history/` holds the newest `.run`
    (i.e. the profile the bot just played). history dir = .../profileN/saves/history,
    so its parent is the `saves/` dir we want to snapshot."""
    best_mtime = -1.0
    chosen: Path | None = None
    for hist in history_dirs:
        for run_file in hist.glob("*.run"):
            mtime = run_file.stat().st_mtime
            if mtime > best_mtime:
                best_mtime, chosen = mtime, hist.parent
    return chosen


def _label_for(saves_dir: Path) -> str:
    """e.g. .../steam/<id>/modded/profile1/saves -> 'modded-profile1'."""
    profile = saves_dir.parent.name  # profile1
    scope = saves_dir.parent.parent.name  # modded
    return f"{scope}-{profile}"


def snapshot_saves(
    saves_dir: Path,
    dest_root: Path,
    keep: int = 50,
    label: str | None = None,
) -> Path | None:
    """Zip the live save files under `saves_dir` (excluding `history/`) into
    `dest_root/<label>_<timestamp>.zip`, then prune that label to the newest `keep`.
    Returns the zip path, or None if there was nothing to back up."""
    if not saves_dir.is_dir():
        return None
    label = label or _label_for(saves_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # microseconds: no collisions
    dest = dest_root / f"{label}_{stamp}.zip"

    wrote = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(saves_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(saves_dir)
            if "history" in rel.parts:  # run records already live in our own logs
                continue
            zf.write(path, rel)
            wrote += 1
    if wrote == 0:
        dest.unlink(missing_ok=True)
        return None

    # rotate: keep the newest `keep` snapshots for this label
    snaps = sorted(dest_root.glob(f"{label}_*.zip"))
    for old in snaps[: max(0, len(snaps) - keep)]:
        old.unlink(missing_ok=True)
    return dest


def backup_active_profile(
    history_dirs: list[Path], dest_root: Path, keep: int = 50
) -> Path | None:
    """Convenience: find the active modded profile and snapshot it. Best-effort —
    never raises into the run loop."""
    try:
        saves_dir = active_saves_dir(history_dirs)
        if saves_dir is None:
            return None
        return snapshot_saves(saves_dir, dest_root, keep=keep)
    except OSError:
        return None
