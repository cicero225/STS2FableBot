"""Distil the Spirebird event ratings (from cohort_stats.json) into data/event_stats.json.

Each event has an overall vsBaseline plus per-option vsBaseline keyed by the option's
internal key (the last segment of Spirebird's optionKey, e.g. EAT / TAKE / READ_ENTIRE_BOOK).
The live EventOption carries no key — only title/description — and the internal key is NOT
a clean title derivation (Sapphire Seed's "Consume" => EAT), so the policy matches
best-effort and falls back to a gain/cost heuristic. event_id maps cleanly: the live
"BYRDONIS_NEST" == Spirebird "EVENT.BYRDONIS_NEST" with the prefix stripped.

Run: .venv\\Scripts\\python.exe scripts/build_event_stats.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

SRC = Path("data/spirebird/cohort_stats.json")
OUT = Path("data/event_stats.json")
COHORT = "all"  # broad average; A0 has no dedicated cohort and event value is ~ascension-flat


def main() -> None:
    cohorts = json.loads(SRC.read_text(encoding="utf-8"))["cohorts"]
    rows = cohorts[COHORT]["events"]
    events: dict[str, dict] = {}
    for e in rows:
        eid = e["eventId"].removeprefix("EVENT.")
        ev = events.setdefault(eid, {"overall_vs": None, "picked": 0, "options": {}})
        vs = e.get("vsBaseline")
        if not e.get("optionKey"):  # the event-level (overall) row
            ev["overall_vs"] = vs
            ev["picked"] = e.get("picked", 0)
        else:
            key = e["optionKey"].split(".")[-1]
            ev["options"][key] = {"vs": vs, "picked": e.get("picked", 0)}
    OUT.write_text(
        json.dumps(
            {
                "meta": {
                    "source": f"spirebird cohort '{COHORT}' events",
                    "generated": datetime.now(UTC).isoformat(),
                    "events": len(events),
                },
                "events": events,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    multi = sum(1 for v in events.values() if len(v["options"]) > 1)
    print(f"wrote {OUT}: {len(events)} events ({multi} with >1 rated option)")


if __name__ == "__main__":
    main()
