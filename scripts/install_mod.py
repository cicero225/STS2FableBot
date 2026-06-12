"""Install (or update) the STS2MCP mod into the game's mods/ folder.

Usage: .venv/Scripts/python scripts/install_mod.py [--game-dir PATH]

Finds the StS2 install via Steam library manifests, downloads the latest STS2MCP
GitHub release (STS2_MCP.dll + STS2_MCP.json), and copies it into <game>/mods/.
Prints every step; nothing outside the game's mods/ folder is touched.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

RELEASES_API = "https://api.github.com/repos/Gennadiyev/STS2MCP/releases/latest"
ASSET_NAMES = {"STS2_MCP.dll", "STS2_MCP.json"}
GAME_NAME = "Slay the Spire 2"


def steam_roots() -> list[Path]:
    roots = []
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    value, _ = winreg.QueryValueEx(
                        k, "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath"
                    )
                    roots.append(Path(value))
            except OSError:
                pass
    except ImportError:
        pass
    roots += [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    seen, unique = set(), []
    for r in roots:
        if r.is_dir() and r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def library_folders(steam_root: Path) -> list[Path]:
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    libs = [steam_root]
    if vdf.is_file():
        for match in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="ignore")):
            libs.append(Path(match.group(1).replace("\\\\", "\\")))
    return [lib for lib in libs if (lib / "steamapps").is_dir()]


def find_game_dir() -> Path | None:
    for steam_root in steam_roots():
        for lib in library_folders(steam_root):
            steamapps = lib / "steamapps"
            for manifest in steamapps.glob("appmanifest_*.acf"):
                text = manifest.read_text(errors="ignore")
                name = re.search(r'"name"\s+"([^"]+)"', text)
                installdir = re.search(r'"installdir"\s+"([^"]+)"', text)
                if name and installdir and name.group(1) == GAME_NAME:
                    game_dir = steamapps / "common" / installdir.group(1)
                    if game_dir.is_dir():
                        return game_dir
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, default=None, help="StS2 install directory")
    args = parser.parse_args()

    game_dir = args.game_dir or find_game_dir()
    if game_dir is None or not game_dir.is_dir():
        print("Could not locate the Slay the Spire 2 install directory.")
        print("Pass it explicitly: --game-dir \"C:\\...\\Slay the Spire 2\"")
        return 1
    mods_dir = game_dir / "mods"
    print(f"Game dir: {game_dir}")
    print(f"Mods dir: {mods_dir} ({'exists' if mods_dir.is_dir() else 'will be created'})")

    print(f"Fetching latest release info: {RELEASES_API}")
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        release = client.get(RELEASES_API).raise_for_status().json()
        tag = release.get("tag_name")
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        missing = ASSET_NAMES - set(assets)
        if missing:
            print(f"Release {tag} is missing expected assets: {missing}")
            print(f"Available: {sorted(assets)}")
            return 1
        print(f"Latest release: {tag}")

        mods_dir.mkdir(exist_ok=True)
        for name in sorted(ASSET_NAMES):
            dest = mods_dir / name
            print(f"  downloading {name} ... ", end="")
            data = client.get(assets[name]).raise_for_status().content
            dest.write_bytes(data)
            print(f"{len(data) / 1024:.0f} KB -> {dest}")

    print(f"Installed STS2MCP {tag}.")
    print("Launch the game via Steam and choose 'Play with Mods', then run:")
    print("  .venv\\Scripts\\sts2bot doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
