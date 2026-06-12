"""Distill the Spirebird cohort export into compact committed card priors.

Input:  data/spirebird/cohort_stats.json (58MB community export, gitignored;
        owner downloads it from spirebird.com — one-time/occasional, per C4)
Output: data/priors_cards.json (~small, committed) — per (character, card_id):
        shrunk Elo-based prior score, roughly (-8 .. +8), 0 = replacement-level.

Key format observed: CARDID_<u>_<f>_CHARACTER_<build>  (u/f are 0/1 variant flags;
a handful of malformed keys lack the build suffix and are skipped).
Pooling: picked-weighted mean Elo across builds/variants per (card, character),
shrunk toward neutral 1600 by sample size: weight = picked / (picked + K).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "spirebird" / "cohort_stats.json"
DEST = ROOT / "data" / "priors_cards.json"

CHARACTERS = {"IRONCLAD", "SILENT", "DEFECT", "REGENT", "NECROBINDER"}
NEUTRAL_ELO = 1600.0
SHRINK_K = 30.0
COHORT = "all"


def parse_key(key: str) -> tuple[str, str] | None:
    """-> (card_id, character) or None for malformed keys."""
    parts = key.split("_")
    if len(parts) < 4:
        return None
    if not parts[-1].replace(".", "").isdigit():
        return None  # missing build suffix (rare malformed entries)
    character = parts[-2]
    if character not in CHARACTERS:
        return None
    card_id = "_".join(parts[:-4])
    return (card_id, character) if card_id else None


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC} — download the export from spirebird.com first")
        return 1
    data = json.loads(SRC.read_text(encoding="utf-8"))
    cards = data["cohorts"][COHORT]["cards"]

    pooled: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    skipped = 0
    for entry in cards:
        parsed = parse_key(entry["key"])
        if parsed is None:
            skipped += 1
            continue
        picked = float(entry.get("picked") or 0)
        elo = entry.get("elo")
        if picked <= 0 or elo is None:
            continue
        acc = pooled[parsed]
        acc[0] += picked * float(elo)
        acc[1] += picked

    out: dict[str, dict[str, float]] = defaultdict(dict)
    for (card_id, character), (elo_weighted, picked_total) in pooled.items():
        if picked_total <= 0:
            continue
        mean_elo = elo_weighted / picked_total
        shrink = picked_total / (picked_total + SHRINK_K)
        score = (mean_elo - NEUTRAL_ELO) / 100.0 * shrink
        out[character][card_id] = round(score, 3)

    payload = {
        "meta": {
            "source": "spirebird.com cohort export",
            "cohort": COHORT,
            "total_runs_parsed": data.get("totalRunsParsed"),
            "generated_at": data.get("generatedAt"),
            "distilled_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "metric": f"picked-weighted mean Elo, shrunk k={SHRINK_K:.0f}, "
            f"(elo-{NEUTRAL_ELO:.0f})/100",
        },
        "cards": {ch: dict(sorted(cards_.items())) for ch, cards_ in sorted(out.items())},
    }
    DEST.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    sizes = {ch: len(c) for ch, c in payload["cards"].items()}
    print(f"wrote {DEST.name}: {sizes} (skipped {skipped} malformed keys)")
    print(f"size: {DEST.stat().st_size / 1024:.0f} KB")

    # spot-check against ids the bot has actually seen in its own logs
    seen: set[str] = set()
    for f in (ROOT / "logs" / "runs").glob("*/decisions.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            state = rec.get("state") or {}
            for c in (state.get("card_reward") or {}).get("cards") or []:
                if c.get("id"):
                    seen.add(c["id"])
    if seen:
        ironclad = payload["cards"].get("IRONCLAD", {})
        all_ids = {cid for ch in payload["cards"].values() for cid in ch}
        hit = sum(1 for s in seen if s in all_ids)
        print(
            f"coverage check: {hit}/{len(seen)} card-reward ids from our logs "
            f"have priors ({hit / len(seen):.0%}); ironclad table: {len(ironclad)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
