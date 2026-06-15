"""Estimate the bot's HP loss per fight type from its own decision logs.

Output: data/combat_stats.json — per fight type (monster/elite/boss):
        {"mean": .., "p75": .., "n": ..}  net HP lost across the fight (start HP minus
        HP at the first post-combat state, so end-of-combat heals like Burning Blood
        are included). Deaths are excluded (not clean loss samples).

This feeds the rest-vs-smith decision (PLAN.md §8 / owner tip): rest only when you
might not survive to the next heal, else smith. Re-run as the bot accumulates runs;
the estimate adapts to how the current policy actually performs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
DEST = ROOT / "data" / "combat_stats.json"

COMBAT = {"monster", "elite", "boss"}
IN_FIGHT = COMBAT | {"hand_select"}  # hand_select is a mid-combat sub-screen


def _hp(rec: dict) -> int | None:
    player = (rec.get("state") or {}).get("player")
    return player.get("hp") if player else None


def fights_in_run(records: list[dict]) -> list[tuple[str, int]]:
    """-> list of (fight_type, net_hp_lost) for fights the player survived."""
    out: list[tuple[str, int]] = []
    i, n = 0, len(records)
    while i < n:
        if records[i].get("state_type") not in COMBAT:
            i += 1
            continue
        ftype = records[i]["state_type"]
        hp_start = None
        j = i
        while j < n and records[j].get("state_type") in IN_FIGHT:
            if hp_start is None:
                hp_start = _hp(records[j])
            j += 1
        # hp at the first post-combat record with player data
        hp_end = None
        k = j
        while k < n and hp_end is None:
            hp_end = _hp(records[k])
            k += 1
        if hp_start is not None and hp_end is not None and hp_end > 0:
            out.append((ftype, max(0, hp_start - hp_end)))
        i = max(j, i + 1)
    return out


def main() -> int:
    samples: dict[str, list[int]] = {"monster": [], "elite": [], "boss": []}
    runs = 0
    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        records = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
        runs += 1
        for ftype, loss in fights_in_run(records):
            samples[ftype].append(loss)

    stats: dict[str, dict] = {}
    for ftype, losses in samples.items():
        if not losses:
            continue
        losses.sort()
        mean = sum(losses) / len(losses)
        p75 = losses[min(len(losses) - 1, (len(losses) * 3) // 4)]
        stats[ftype] = {"mean": round(mean, 1), "p75": p75, "n": len(losses)}

    payload = {"source": f"{runs} run logs", "fight_hp_loss": stats}
    DEST.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {DEST.name} from {runs} runs:")
    for ftype, s in stats.items():
        print(f"  {ftype:8} mean={s['mean']:5.1f}  p75={s['p75']:3}  (n={s['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
