"""Pair every fuzzed play's logged prediction against the next poll's actuals.

The fuzz router (sts2bot/policy/fuzz.py) plays RANDOM legal cards and logs the
text-parse prediction in the rationale:
    FUZZ: Strike -> TOADPOLE_0 | PRED dmg=6x1 aoe=0 blk=5 draw=1 egain=0 ...
This script replays the decision logs, finds the post-action settled state for
each fuzzed play, and compares per-channel:
  - dmg:  target enemy (hp + block) drop vs predicted dmg*hits (aoe: all enemies)
  - blk:  player block gain vs predicted
  - draw: hand growth vs predicted (net of the played card leaving)
  - egain: energy delta vs (gain - cost)
Divergences are bucketed by card id so systematic misparses surface with n>=3.
Off-policy coverage is the point: random orderings visit conditional riders and
sequencing states the standard policy never enters (owner design 2026-08-06).

Usage: python scripts/fuzz_audit.py [--min-n 3] [--runs-glob "logs/runs/*"]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

_PRED = re.compile(
    r"FUZZ: (?P<name>.+?) -> (?P<target>\S+) \| PRED dmg=(?P<dmg>-?\d+)x(?P<hits>\d+) "
    r"aoe=(?P<aoe>\d) blk=(?P<blk>-?\d+) draw=(?P<draw>-?\d+) egain=(?P<egain>-?\d+)"
)


def _battle(row: dict) -> dict | None:
    st = row.get("state") or {}
    return st.get("battle")


def _player(row: dict) -> dict | None:
    st = row.get("state") or {}
    return st.get("player")


def _enemy_pool(row: dict) -> dict[str, tuple[int, int]]:
    b = _battle(row) or {}
    return {
        e.get("entity_id"): (e.get("hp") or 0, e.get("block") or 0)
        for e in (b.get("enemies") or [])
    }


def _settled_after(rows: list[dict], i: int) -> dict | None:
    """First later row in the SAME fight whose state visibly changed (the action
    settle guard means several identical polls may intervene). None if the fight
    ends or a rail/menu transition happens first."""
    base_b, base_p = _battle(rows[i]), _player(rows[i])
    if base_b is None or base_p is None:
        return None
    base_sig = (json.dumps(base_b, sort_keys=True), base_p.get("hp"),
                base_p.get("block"), base_p.get("energy"),
                len(base_p.get("hand") or []))
    for r in rows[i + 1 : i + 40]:
        ra = r.get("rationale") or r.get("reason") or ""
        if "FUZZ-RAIL" in ra or r.get("state_type") in ("menu", "map", "rewards"):
            return None
        b, p = _battle(r), _player(r)
        if b is None or p is None:
            return None
        sig = (json.dumps(b, sort_keys=True), p.get("hp"), p.get("block"),
               p.get("energy"), len(p.get("hand") or []))
        if sig != base_sig:
            return r
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=3)
    ap.add_argument("--runs-glob", default="logs/runs/*")
    args = ap.parse_args()

    plays = 0
    paired = 0
    # (card_name, channel) -> list of (predicted, actual)
    buckets: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)

    for run_dir in sorted(glob.glob(args.runs_glob)):
        f = Path(run_dir) / "decisions.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(line) for line in f.open(encoding="utf-8")]
        if not any("FUZZ:" in (r.get("rationale") or "") for r in rows):
            continue
        for i, row in enumerate(rows):
            m = _PRED.search(row.get("rationale") or "")
            if not m:
                continue
            plays += 1
            after = _settled_after(rows, i)
            if after is None:
                continue
            paired += 1
            name = m["name"]
            pred_dmg = int(m["dmg"]) * max(1, int(m["hits"]))
            aoe = m["aoe"] == "1"
            pool0, pool1 = _enemy_pool(row), _enemy_pool(after)
            if pred_dmg and (m["target"] != "self" or aoe):
                ids = pool0.keys() if aoe else [m["target"]]
                actual = sum(
                    max(0, sum(pool0.get(t, (0, 0))) - sum(pool1.get(t, (0, 0))))
                    for t in ids
                    if t in pool0
                )
                want = pred_dmg * (len([t for t in ids if t in pool0]) if aoe else 1)
                buckets[(name, "dmg")].append((want, actual))
            p0, p1 = _player(row), _player(after)
            if int(m["blk"]):
                buckets[(name, "blk")].append(
                    (int(m["blk"]), (p1.get("block") or 0) - (p0.get("block") or 0))
                )
            if int(m["draw"]):
                # net of this card leaving the hand: playing a "draw 2" from a
                # 5-card hand settles at 6 cards (5 - 1 + 2)
                actual_draw = (len(p1.get("hand") or []) - len(p0.get("hand") or [])) + 1
                buckets[(name, "draw")].append((int(m["draw"]), actual_draw))
            if int(m["egain"]):
                buckets[(name, "egain")].append(
                    (int(m["egain"]), (p1.get("energy") or 0) - (p0.get("energy") or 0))
                )

    print(f"fuzzed plays: {plays}  paired with settled actuals: {paired}")
    print(f"\n=== divergences by (card, channel), n >= {args.min_n} ===")
    scored = []
    for (name, ch), pairs in buckets.items():
        if len(pairs) < args.min_n:
            continue
        diffs = [a - p for p, a in pairs]
        avg = sum(diffs) / len(diffs)
        hit = sum(1 for d in diffs if abs(d) <= 1) / len(diffs)
        scored.append((abs(avg), name, ch, len(pairs), avg, hit))
    for _, name, ch, n, avg, hit in sorted(scored, reverse=True):
        flag = "  <-- CHECK" if abs(avg) > 2 and hit < 0.7 else ""
        print(f"  {name:28s} {ch:5s} n={n:3d} avg_actual-pred={avg:+6.1f} "
              f"within+-1={hit:4.0%}{flag}")


if __name__ == "__main__":
    main()
