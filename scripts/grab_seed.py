"""Read the current run's Act-1 boss + seed; store seeds whose boss matches a target.

Why: custom-mode seeded replay needs *current-content* seeds (the Act-3-win unlocks —
new cards + the Undergrowth Act-1 area — shifted map generation, so pre-unlock seeds no
longer reproduce their old boss). The custom *setup* screen isn't exposed by the mod API
(no way to type the seed / embark programmatically), and singleplayer runs can't be
abandoned via the API either — so the owner starts standard A0 runs and abandons non-Kin
ones; this read-only helper grabs the boss + seed at the map and banks the matches.

The Act-1 boss is visible in `/state` `map.boss` once past Neow; the seed is in
`/compendium` `current_run.seed`. Run this when a fresh run is sitting on the Act-1 map.

Usage:  python scripts/grab_seed.py [TARGET_SUBSTRING=KIN]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from sts2bot.client import Sts2Client

STORE = Path("data/test_seeds.json")


def main() -> None:
    target = (sys.argv[1] if len(sys.argv) > 1 else "KIN").upper()
    with Sts2Client() as client:
        raw = client.get_state_raw()
        comp = client.get_compendium()

    cur = (comp or {}).get("current_run") or {}
    seed = cur.get("seed")
    if not seed or not cur.get("is_in_progress", True):
        print("No run in progress (no current_run.seed). Start/enter a run first.")
        return

    run = raw.get("run") or {}
    boss = (raw.get("map") or {}).get("boss") or {}
    boss_id = boss.get("id")
    boss_name = boss.get("name")
    char = (raw.get("player") or {}).get("character")
    asc = run.get("ascension")
    act = run.get("act")

    if not boss_id:
        print(f"seed={seed} | Act-1 boss not visible yet (state={raw.get('state_type')}, "
              f"act={act}). Advance past Neow to the map, then re-run.")
        return

    hit = target in (boss_id or "").upper() or target in (boss_name or "").upper()
    flag = "  <<< MATCH" if hit else ""
    print(f"seed={seed} | act1_boss={boss_name} ({boss_id}) | char={char} A{asc}{flag}")

    if not hit:
        print(f"  (not {target} — abandon in-game and start another)")
        return

    store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else []
    if any(e.get("seed") == seed for e in store):
        print(f"  already stored seed {seed}.")
        return
    store.append({
        "seed": seed, "boss_id": boss_id, "boss_name": boss_name,
        "character": char, "ascension": asc, "mode": "standard",
        "found_at": int(time.time()),
    })
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    print(f"  STORED -> {STORE} ({len(store)} seed(s) total). "
          f"Next: type {seed} into Custom mode to verify it reproduces {boss_name}.")


if __name__ == "__main__":
    main()
