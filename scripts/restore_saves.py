"""Restore StS2 saves from a backup. Companion to backup_saves.py + per-run snapshots.

** CLOSE THE GAME before restoring — it locks the save files while running. **

Every restore first snapshots whatever it is about to overwrite (to
backups/pre-restore/), so a restore is itself reversible.

Usage:
  python scripts/restore_saves.py --list
  python scripts/restore_saves.py --restore <snapshot.zip> [--to <saves_dir>]
  python scripts/restore_saves.py --full <backups/TIMESTAMP> --yes
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKUPS = REPO / "backups"
SNAP_DIR = BACKUPS / "profile_snapshots"
PRE_RESTORE = BACKUPS / "pre-restore"


def _appdata_sts2() -> Path | None:
    appdata = os.environ.get("APPDATA")
    p = Path(appdata) / "SlayTheSpire2" if appdata else None
    return p if p and p.is_dir() else None


def _active_saves_dir() -> Path | None:
    try:
        from sts2bot.runlog.runfile import discover_history_dirs
        from sts2bot.runlog.saves import active_saves_dir

        return active_saves_dir(discover_history_dirs())
    except Exception:
        return None


def _zip_dir(src: Path, dest_zip: Path, skip_history: bool = False) -> int:
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src)
            if skip_history and "history" in rel.parts:
                continue
            zf.write(path, rel)
            count += 1
    return count


def cmd_list() -> int:
    print("Full-tree backups  (backups/<timestamp>/  — use with --full):")
    for d in sorted(BACKUPS.glob("20*")):
        if d.is_dir():
            zips = ", ".join(z.name for z in d.glob("*.zip"))
            print(f"  {d.name}   [{zips}]")
    print("\nProfile snapshots  (backups/profile_snapshots/  — use with --restore):")
    snaps = sorted(SNAP_DIR.glob("*.zip"))
    if not snaps:
        print("  (none yet — they are written after each run)")
    for z in snaps:
        print(f"  {z.name}   ({z.stat().st_size // 1024} KB)")
    active = _active_saves_dir()
    print(f"\nActive modded profile saves dir (default --to): {active or '(not found)'}")
    return 0


def cmd_restore(snapshot: str, to: str | None) -> int:
    zip_path = Path(snapshot)
    if not zip_path.exists():
        zip_path = SNAP_DIR / snapshot
    if not zip_path.is_file():
        print(f"Snapshot not found: {snapshot}")
        return 1
    dest = Path(to) if to else _active_saves_dir()
    if dest is None:
        print("Could not determine target saves dir; pass --to <saves_dir>.")
        return 1
    dest.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety = PRE_RESTORE / f"{dest.parent.name}_{stamp}.zip"
    n = _zip_dir(dest, safety, skip_history=True)
    print(f"Backed up current target ({n} files) -> {safety}")

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    print(f"Restored {zip_path.name} -> {dest}")
    print("Done. Launch the game and confirm the profile looks right.")
    return 0


def cmd_full(backup_dir: str, yes: bool) -> int:
    src_zip = Path(backup_dir)
    if src_zip.is_dir():
        src_zip = src_zip / "roaming_appdata.zip"
    if not src_zip.is_file():
        print(f"roaming_appdata.zip not found under {backup_dir}")
        return 1
    target = _appdata_sts2()
    if target is None:
        print("Could not locate %APPDATA%\\SlayTheSpire2.")
        return 1
    if not yes:
        print(f"This OVERWRITES the live save tree at:\n  {target}\nfrom:\n  {src_zip}")
        print("Re-run with --yes to proceed (and make sure the game is CLOSED).")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety = PRE_RESTORE / f"full_{stamp}.zip"
    n = _zip_dir(target, safety)
    print(f"Backed up current live tree ({n} files) -> {safety}")
    with zipfile.ZipFile(src_zip) as zf:
        zf.extractall(target)
    print(f"Restored full tree from {src_zip} -> {target}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list", action="store_true", help="List available backups.")
    ap.add_argument("--restore", metavar="ZIP", help="Restore a profile snapshot.")
    ap.add_argument(
        "--to", metavar="DIR", help="Target saves dir (default: active modded profile)."
    )
    ap.add_argument("--full", metavar="BACKUP_DIR", help="Restore a full-tree backup.")
    ap.add_argument("--yes", action="store_true", help="Confirm a destructive --full restore.")
    args = ap.parse_args()

    if args.list:
        return cmd_list()
    if args.restore:
        return cmd_restore(args.restore, args.to)
    if args.full:
        return cmd_full(args.full, args.yes)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
