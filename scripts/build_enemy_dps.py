"""Harvest REALIZED per-enemy dps from fight logs -> data/enemy_dps.json.

The calibration sensitivity probe (2026-07-25) localized the estimator's error to
the enemy pressure model: the per-act dps priors read like peak attack turns, ~2x
too high as sustained averages. The fix is empirical: intent labels are
fully-resolved previews (THE PRE-BAKE RULE), so averaging each enemy's parsed
attack-intent damage across all its recorded rounds — counting buff/summon/stall
rounds as ZERO — is exactly the sustained average the race model needs, cleanly
attributable per enemy even in multi-enemy fights (no block confound).

Early/late split: averaging across rounds bakes Strength ramp into the mean, and
feeding both the baked mean AND str_ramp to the race would double-count. Consumers
use dps_early (rounds 1-3) as the base with the ramp parameter, or dps_mean with
ramp zeroed; we store both plus dps_late (rounds 4+) so the choice is theirs.

Additive-safe: unlike build_bestiary this only ever ADDS/updates names found in the
local logs and merges over the existing committed file — a machine with few logs
cannot silently shrink the dataset.

Run: .venv/Scripts/python scripts/build_enemy_dps.py
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "enemy_dps.json"
sys.path.insert(0, str(ROOT))

from sts2bot.policy.textparse import parse_intent_damage  # noqa: E402

FIGHT_STATES = ("monster", "elite", "boss")


def harvest() -> dict[str, dict]:
    # name -> list of per-(fight, round) attack-intent damage totals
    per_round: dict[str, list[tuple[int, int]]] = defaultdict(list)  # (round, dmg)
    fights_seen: dict[str, set] = defaultdict(set)
    for run_dir in sorted(glob.glob(str(ROOT / "logs" / "runs" / "*"))):
        p = Path(run_dir) / "decisions.jsonl"
        if not p.is_file():
            continue
        seen_rounds: set = set()  # (floor, round, name) dedupe within a run
        with open(p, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("state_type") not in FIGHT_STATES:
                    continue
                st = r.get("state") or {}
                bt = st.get("battle") or {}
                rnd = bt.get("round")
                fl = (st.get("run") or {}).get("floor")
                if rnd is None or fl is None:
                    continue
                for e in bt.get("enemies") or []:
                    if (e.get("hp") or 0) <= 0:
                        continue
                    name = e.get("name") or ""
                    if not name:
                        continue
                    key = (fl, rnd, name, e.get("entity_id"))
                    if key in seen_rounds:
                        continue
                    seen_rounds.add(key)
                    dmg = sum(
                        parse_intent_damage(i.get("label") or "")
                        for i in e.get("intents") or []
                        if (i.get("type") or "").lower() in ("attack", "deathblow")
                    )
                    per_round[name].append((int(rnd), dmg))
                    fights_seen[name].add((run_dir, fl))
    out: dict[str, dict] = {}
    for name, rows in per_round.items():
        if len(rows) < 6:  # too little data to trust
            continue
        early = [d for rnd, d in rows if rnd <= 3]
        late = [d for rnd, d in rows if rnd >= 4]
        out[name] = {
            "dps_mean": round(sum(d for _, d in rows) / len(rows), 1),
            "dps_early": round(sum(early) / len(early), 1) if early else None,
            "dps_late": round(sum(late) / len(late), 1) if late else None,
            "rounds": len(rows),
            "fights": len(fights_seen[name]),
        }
    return out


def main() -> None:
    fresh = harvest()
    existing: dict = {}
    if OUT.is_file():
        existing = json.loads(OUT.read_text(encoding="utf-8")).get("enemies", {})
    merged = {**existing, **fresh}  # local harvest wins per-name; absent names survive
    OUT.write_text(json.dumps({
        "_meta": {
            "source": "scripts/build_enemy_dps.py (realized intent-damage averages; "
                      "buff/stall rounds count as 0 — the sustained dps the race needs)",
            "n_enemies": len(merged),
        },
        "enemies": merged,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(fresh)} harvested, {len(merged)} total")


if __name__ == "__main__":
    main()
