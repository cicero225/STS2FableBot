"""Watch a running batch for a boss fight and checkpoint it for savescum A/B.

Owner suggestion (2026-08-18, Test Subject burst_window validation): when the
target boss turns up and the fight is nearly decided (either way), kill the
batch process FIRST (so its abandon-recovery can't consume the parked save),
then save_and_quit -- mid-combat never saves, so Continue reloads the FIGHT
START: a deterministic snapshot to A/B mode changes against.

Usage:
  python scripts/watch_boss_checkpoint.py "Test Subject" [--batch-image sts2bot.exe]

Trigger (near-end, either way): final-phase body (max_hp >= --p3-hp) at/below
--boss-hp, OR player at/below --player-hp in any phase. Exits after the
checkpoint (or when the game/API goes away).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2bot.client import Sts2Client
from sts2bot.client.actions import SaveAndQuit
from sts2bot.policy.forward import canonical_enemy_name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("boss", help="canonical enemy name to watch for, e.g. 'Test Subject'")
    ap.add_argument("--batch-image", default="sts2bot.exe",
                    help="process image to kill before checkpointing")
    ap.add_argument("--p3-hp", type=int, default=250,
                    help="max_hp at/above this marks the final phase body")
    ap.add_argument("--boss-hp", type=int, default=80,
                    help="final-phase body hp at/below this triggers")
    ap.add_argument("--player-hp", type=int, default=20,
                    help="player hp at/below this triggers in any phase")
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()
    target = args.boss.upper()

    seen_fight = False
    with Sts2Client() as client:
        while True:
            try:
                raw = client.get_state_raw()
            except Exception as e:  # game restarting between runs is normal
                print(f"state unavailable ({e}); retrying", flush=True)
                time.sleep(10)
                continue
            b = raw.get("battle") or {}
            enemies = b.get("enemies") or []
            boss_bodies = [
                e for e in enemies
                if canonical_enemy_name(e.get("name")).upper() == target
                and (e.get("hp") or 0) > 0
            ]
            if not boss_bodies:
                time.sleep(args.poll)
                continue
            if not seen_fight:
                seen_fight = True
                print(f"{args.boss} FIGHT DETECTED r{b.get('round')} "
                      f"floor {(raw.get('run') or {}).get('floor')}", flush=True)
            body = boss_bodies[0]
            hp = body.get("hp") or 0
            max_hp = body.get("max_hp") or 0
            php = (raw.get("player") or {}).get("hp") or 999
            final_phase = max_hp >= args.p3_hp
            if (final_phase and hp <= args.boss_hp) or php <= args.player_hp:
                print(f"NEAR-END r{b.get('round')}: body {hp}/{max_hp} "
                      f"player {php} -> killing batch + save_and_quit", flush=True)
                subprocess.run(["taskkill", "/IM", args.batch_image, "/F"],
                               capture_output=True)
                time.sleep(2)  # let the batch process die before we act
                res = client.act(SaveAndQuit())
                print(f"CHECKPOINT save_and_quit: {getattr(res, 'status', res)} | "
                      f"Continue reloads the fight start. Batch is DOWN.", flush=True)
                return 0
            time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
