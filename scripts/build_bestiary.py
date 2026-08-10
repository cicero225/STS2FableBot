"""Harvest a bestiary from the bot's combat logs (ENEMY_PASS.md Phase 0).

Per enemy: the act(s) and role (boss/elite/monster) it appears in, HP range, how many runs it was
seen in, and its full status/power list WITH the mod's rules-text descriptions (Plating, Slippery,
Intangible, ...). The mod ships enemy status descriptions in the state, so most mechanics come
straight from our own logs; online research only fills hidden / multi-turn behaviour (revive,
escalation). This file is the source the §5-C estimate / combat planner will consult, and the
tracking checklist for the enemy-mechanics pass. Re-run as runs accumulate.

Output: data/bestiary.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
DEST = ROOT / "data" / "bestiary.json"
COMBAT = {"monster", "elite", "boss"}


def main() -> int:
    enemies: dict[str, dict] = {}
    runs = 0
    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        runs += 1
        run_id = f.parent.name
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("state_type") not in COMBAT:
                continue
            state = rec.get("state") or {}
            act = (state.get("run") or {}).get("act")
            for e in (state.get("battle") or {}).get("enemies") or []:
                name = e.get("name") or e.get("entity_id")
                if not name:
                    continue
                ent = enemies.setdefault(
                    name,
                    {"roles": set(), "acts": set(), "runs": set(),
                     "hp_min": None, "hp_max": None, "statuses": {}},
                )
                ent["roles"].add(rec["state_type"])
                ent["runs"].add(run_id)
                if act is not None:
                    ent["acts"].add(act)
                mhp = e.get("max_hp")
                if mhp and mhp >= 1e8:
                    # WG eruption 'preparing' sentinel (2^32-1 shown as HP):
                    # not a real max-HP observation -- recording it once made
                    # every WG forecast read unkillable (caught 2026-08-10)
                    mhp = None
                if mhp:
                    ent["hp_min"] = mhp if ent["hp_min"] is None else min(ent["hp_min"], mhp)
                    ent["hp_max"] = mhp if ent["hp_max"] is None else max(ent["hp_max"], mhp)
                for s in e.get("status") or []:
                    sid = s.get("id") or s.get("name")
                    if sid and sid not in ent["statuses"]:
                        ent["statuses"][sid] = {
                            "name": s.get("name"),
                            "description": s.get("description"),
                        }

    out: dict[str, dict] = {}
    for name, ent in sorted(enemies.items()):
        out[name] = {
            "roles": sorted(ent["roles"]),
            "acts": sorted(ent["acts"]),
            "runs_seen": len(ent["runs"]),
            "hp": [ent["hp_min"], ent["hp_max"]],
            "statuses": dict(sorted(ent["statuses"].items())),
        }
    DEST.write_text(
        json.dumps({"source": f"{runs} run logs", "enemies": out}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"wrote {len(out)} enemies from {runs} runs to {DEST.name}")
    for role in ("boss", "elite", "monster"):
        names = sorted(n for n, e in out.items() if role in e["roles"])
        print(f"  {role} ({len(names)}): {', '.join(names)}")
    catalogue = {sid: s["name"] for e in out.values() for sid, s in e["statuses"].items()}
    print(f"  distinct statuses/powers catalogued: {len(catalogue)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
