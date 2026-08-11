"""Harvest per-enemy, turn-indexed move scripts from the fight logs.

Multiturn planner P1 (owner design session 2026-08-11): the feasibility oracle
needs "what does this enemy do on turn N" -- Kaiser Rocket's T4 Laser, Soul
Siphon every 4th round, Sandpit's clock. Owner: scripts are MOSTLY turn-indexed;
exceptions are single-threshold bosses (Ceremonial Beast), Queen (Torch-death
trigger), Test Subject (staged bodies) -- those get special-cased, and every
harvested script gets cross-checked against the online wiki before the planner
trusts it (owner: the wiki reliably gives exact turn-by-turn behavior).

Output: data/move_scripts.json
  {enemy: {"turns": {"1": [{intent, label, n}, ...], ...},
           "n_fights": int, "notes": str}}
Turn index = the fight's round counter at the time the intent was shown.
Only intents actually observed are recorded; the wiki pass annotates gaps.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
DEST = ROOT / "data" / "move_scripts.json"


def main() -> int:
    # enemy -> round -> Counter[(intent_type, label)]
    scripts: dict[str, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    fights_seen: dict[str, set] = defaultdict(set)

    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        run_id = f.parent.name
        # one sample per (enemy, fight, round): consecutive polls repeat intents
        seen_this_run: set[tuple] = set()
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            st = json.loads(line).get("state") or {}
            b = st.get("battle") or {}
            rnd = b.get("round")
            floor = (st.get("run") or {}).get("floor")
            if not rnd or not b.get("enemies"):
                continue
            for e in b["enemies"]:
                name = e.get("name")
                if not name or (e.get("hp") or 0) <= 0:
                    continue
                for i in e.get("intents") or []:
                    itype = (i.get("type") or "").strip()
                    label = (i.get("label") or "").strip()
                    key = (name, run_id, floor, rnd, itype, label)
                    if key in seen_this_run:
                        continue
                    seen_this_run.add(key)
                    scripts[name][rnd][(itype, label)] += 1
                fights_seen[name].add((run_id, floor))

    out: dict[str, dict] = {}
    for name, rounds in sorted(scripts.items()):
        turns = {}
        for rnd in sorted(rounds):
            turns[str(rnd)] = [
                {"intent": t, "label": lbl, "n": n}
                for (t, lbl), n in rounds[rnd].most_common(6)
            ]
        out[name] = {
            "turns": turns,
            "n_fights": len(fights_seen[name]),
            "notes": "",
        }
    DEST.write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote move scripts for {len(out)} enemies to {DEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
