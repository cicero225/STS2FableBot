"""Back up every StS2 save location found on this machine (REQUIREMENTS C1).

Run before ANY live bot session: `python scripts/backup_saves.py`
Zips each discovered save directory into backups/<timestamp>/ at the repo root.

The exact live save path is a P0 investigation item; this script checks every
candidate reported by the community and prints what it found, so the first run
also answers that question.
"""

from __future__ import annotations

import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CANDIDATES = [
    ("localappdata", Path(os.environ.get("LOCALAPPDATA", "")) / "SlayTheSpire2"),
    ("roaming_appdata", Path(os.environ.get("APPDATA", "")) / "SlayTheSpire2"),
]


def steam_userdata_candidates() -> list[tuple[str, Path]]:
    """Steam Cloud local mirrors: <steam>/userdata/<account>/<appid>."""
    found = []
    for steam_root in (
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
    ):
        userdata = steam_root / "userdata"
        if not userdata.is_dir():
            continue
        for account_dir in userdata.iterdir():
            sts2 = account_dir / "2868840"  # StS2 app id (verify: remote/ contains saves)
            if sts2.is_dir():
                found.append((f"steam_userdata_{account_dir.name}", sts2))
    return found


def zip_dir(src: Path, dest_zip: Path) -> int:
    count = 0
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                try:
                    zf.write(path, path.relative_to(src))
                except ValueError:
                    # zip can't store mtimes before 1980 (2026-09-26: the v0.111
                    # beta wrote modded/profile.save with a 1970 stamp); store
                    # the bytes under a clamped timestamp rather than abort
                    info = zipfile.ZipInfo(str(path.relative_to(src)).replace("\\", "/"),
                                           date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(info, path.read_bytes())
                count += 1
    return count


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = REPO_ROOT / "backups" / stamp
    targets = [(name, p) for name, p in CANDIDATES if p.is_dir()] + steam_userdata_candidates()

    if not targets:
        print("No StS2 save directories found in any known location:")
        for name, p in CANDIDATES:
            print(f"  - {name}: {p} (missing)")
        print("Is the game installed / has it been launched at least once?")
        return 1

    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"Backing up to {backup_dir}")
    for name, src in targets:
        dest = backup_dir / f"{name}.zip"
        n = zip_dir(src, dest)
        size_kb = dest.stat().st_size / 1024
        print(f"  {name}: {src}")
        print(f"    -> {dest.name} ({n} files, {size_kb:.0f} KB)")
    print("Done. Keep these until the bot profile setup is verified safe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
