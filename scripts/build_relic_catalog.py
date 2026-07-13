"""Build data/relic_catalog.json from the run-log corpus.

Harvests every relic observed anywhere in logged states — held (player.relics, with
counter behavior), shop stock (relic_id/name/description), and relic-select offers —
with live rules text and exposure stats. The mod's compendium/wiki can top this up
later; the corpus is the ground truth for text the planner will actually see.
"""

from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "relic_catalog.json")

relics: dict[str, dict] = defaultdict(lambda: {
    "name": None, "description": None, "counter_seen": False,
    "runs_held": set(), "seen_in": set(),
})


def note(rid: str | None, name: str | None, desc: str | None, run: str,
         source: str, counter=None) -> None:
    key = (rid or name or "").upper().replace(" ", "_")
    if not key:
        return
    r = relics[key]
    if name:
        r["name"] = name
    if desc and (r["description"] is None or len(desc) > len(r["description"] or "")):
        r["description"] = desc
    if counter is not None:
        r["counter_seen"] = True
    r["seen_in"].add(source)
    if source == "held":
        r["runs_held"].add(run)


def scan_state(st: dict, run: str) -> None:
    pl = st.get("player") or {}
    for r in pl.get("relics") or []:
        note(r.get("id"), r.get("name"), r.get("description"), run, "held",
             counter=r.get("counter"))
    shop = (st.get("shop") or {})
    for it in shop.get("items") or []:
        if it.get("category") == "relic":
            note(it.get("relic_id"), it.get("relic_name"),
                 it.get("relic_description"), run, "shop")
    rs = st.get("relic_select") or {}
    for r in rs.get("relics") or []:
        note(r.get("id"), r.get("name"), r.get("description"), run, "offered")


def main() -> None:
    paths = sorted(glob.glob(os.path.join(ROOT, "logs", "runs", "*", "decisions.jsonl")))
    paths += sorted(glob.glob(os.path.join(ROOT, "logs", "manual", "*", "decisions.jsonl")))
    for path in paths:
        run = os.path.basename(os.path.dirname(path))
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if '"relic' not in line and '"relics"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    scan_state(d.get("state") or {}, run)
        except OSError:
            continue

    out = {}
    for key, r in sorted(relics.items()):
        out[key] = {
            "name": r["name"],
            "description": r["description"],
            "counter_seen": r["counter_seen"],
            "runs_held": len(r["runs_held"]),
            "seen_in": sorted(r["seen_in"]),
        }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "run-log corpus (live rules text)", "relics": out}, f, indent=1)
    held = sum(1 for r in out.values() if "held" in r["seen_in"])
    print(f"wrote {OUT}: {len(out)} relics ({held} ever held, "
          f"{sum(1 for r in out.values() if r['counter_seen'])} with counters)")


if __name__ == "__main__":
    main()
