"""Power-play timing: mechanism check for the powers-under-played Tier-1 fix (PLAN §8.4). For a
config, scan every fight in the logged traces and measure how promptly Power cards get played:
  - play-rate: of fights where a *playable* Power was in hand, the fraction that played one (the
    rest left it idling as an effective curse — the failure the fix targets),
  - first-play round: the mean round at which the first Power went down (lower = earlier = ASAP).

Usage: .venv\\Scripts\\python.exe scripts/power_timing.py [config_hash] [character]
Defaults to the most recent config and 'The Ironclad'. Run before/after the fix to compare.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics as st
import sys

LOG_DB = "logs/index.sqlite"


def fights_of(path: str) -> list[dict]:
    """Group a run's decisions into fights (maximal runs with a battle block); per fight record
    whether a playable Power was in hand, whether one was played, and the first play's round."""
    fights: list[dict] = []
    cur: dict | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            state = d.get("state") or {}
            battle = state.get("battle")
            if not battle:
                if cur is not None:
                    fights.append(cur)
                    cur = None
                continue
            if cur is None:
                cur = {"avail": False, "played": False, "first": None}
            hand = (state.get("player") or {}).get("hand") or []
            rnd = battle.get("round")
            if any(c.get("type") == "Power" and c.get("can_play") for c in hand):
                cur["avail"] = True
            action = d.get("action") or {}
            if action.get("action") == "play_card":
                ci = action.get("card_index")
                if ci is not None and 0 <= ci < len(hand) and hand[ci].get("type") == "Power":
                    cur["played"] = True
                    if cur["first"] is None:
                        cur["first"] = rnd
    if cur is not None:
        fights.append(cur)
    return fights


def main() -> None:
    conn = sqlite3.connect(LOG_DB)
    cfg = sys.argv[1] if len(sys.argv) > 1 else conn.execute(
        "SELECT config_hash FROM runs GROUP BY config_hash ORDER BY MAX(started_at) DESC LIMIT 1"
    ).fetchone()[0]
    char = sys.argv[2] if len(sys.argv) > 2 else "The Ironclad"
    rows = conn.execute(
        "SELECT run_dir FROM runs WHERE config_hash=? AND character=? AND status='completed'",
        (cfg, char),
    ).fetchall()
    print(f"config {cfg}  character {char}  completed runs: {len(rows)}")

    all_fights = []
    for (run_dir,) in rows:
        path = os.path.join(run_dir.replace("\\", "/"), "decisions.jsonl")
        if os.path.exists(path):
            all_fights.extend(fights_of(path))

    avail = [f for f in all_fights if f["avail"]]
    played = [f for f in avail if f["played"]]
    first_rounds = [f["first"] for f in played if f["first"] is not None]
    print(f"  fights total: {len(all_fights)}   with a playable Power in hand: {len(avail)}")
    if avail:
        print(f"  play-rate (played a Power | one was playable): {100*len(played)/len(avail):.0f}%"
              f"  ({len(played)}/{len(avail)})")
    if first_rounds:
        print(f"  first Power-play round: mean {st.mean(first_rounds):.1f}, "
              f"median {st.median(first_rounds):.0f}")


if __name__ == "__main__":
    main()
