"""Estimate the bot's HP loss per fight type from its own decision logs.

Output: data/combat_stats.json — per fight type:
        {"mean": .., "p75": .., "n": ..}  net HP lost across the fight (start HP minus
        HP at the first post-combat state, so end-of-combat heals like Burning Blood
        are included). Deaths are excluded (not clean loss samples).

Normal fights are split into `monster_early` (within the first 3 floors of an act) and
`monster` (the rest): the first ~3 floors of each act generate deliberately easier normal
fights (humans route normals there, especially in Act 1), so one blended average would
over-state early-floor danger and under-state late-floor danger. Elite/boss are not split
(they don't occur that early). Feeds rest-vs-smith and, next, path-EV routing (PLAN §8.2).

Re-run as the bot accumulates runs; the estimate adapts to how the current policy performs.
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
EARLY_FLOORS = 3  # a normal fight within this many floors of an act's start is an "easy" early one


def _hp(rec: dict) -> int | None:
    player = (rec.get("state") or {}).get("player")
    return player.get("hp") if player else None


def _floor_act(rec: dict) -> tuple[int | None, int | None]:
    run = (rec.get("state") or {}).get("run") or {}
    return run.get("floor"), run.get("act")


def fights_in_run(records: list[dict]) -> list[tuple[str, int | None, int | None, int]]:
    """-> list of (fight_type, floor, act, net_hp_lost) for fights the player survived.
    floor/act are the first non-null run position seen during the fight (a fight's opening
    records can carry a null run block, so scan forward for the first populated one)."""
    out: list[tuple[str, int | None, int | None, int]] = []
    i, n = 0, len(records)
    while i < n:
        if records[i].get("state_type") not in COMBAT:
            i += 1
            continue
        ftype = records[i]["state_type"]
        hp_start = floor = act = None
        j = i
        while j < n and records[j].get("state_type") in IN_FIGHT:
            if hp_start is None:
                hp_start = _hp(records[j])
            if floor is None:
                fl, ac = _floor_act(records[j])
                if fl is not None and ac is not None:
                    floor, act = fl, ac
            j += 1
        # hp at the first post-combat record with player data
        hp_end = None
        k = j
        while k < n and hp_end is None:
            hp_end = _hp(records[k])
            k += 1
        if hp_start is not None and hp_end is not None and hp_end > 0:
            out.append((ftype, floor, act, max(0, hp_start - hp_end)))
        i = max(j, i + 1)
    return out


def main() -> int:
    samples: dict[str, list[int]] = {}
    runs = 0
    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        records = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
        runs += 1
        # first floor seen in each act this run = that act's start, so "early" is robust to
        # the varying act-2/3 boundary floors rather than a hard-coded floor number.
        act_start: dict[int, int] = {}
        for r in records:
            fl, ac = _floor_act(r)
            if fl is not None and ac is not None:
                act_start[ac] = min(act_start.get(ac, fl), fl)
        for ftype, floor, act, loss in fights_in_run(records):
            key = ftype
            if (
                ftype == "monster"
                and floor is not None
                and act in act_start
                and floor - act_start[act] < EARLY_FLOORS
            ):
                key = "monster_early"
            samples.setdefault(key, []).append(loss)

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
    for ftype in ("monster_early", "monster", "elite", "boss"):
        s = stats.get(ftype)
        if s:
            print(f"  {ftype:13} mean={s['mean']:5.1f}  p75={s['p75']:3}  (n={s['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
