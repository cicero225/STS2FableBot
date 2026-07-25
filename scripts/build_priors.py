"""Distill the Spirebird cohort export into compact committed card priors.

Input:  data/spirebird/cohort_stats.json (58MB community export, gitignored;
        owner downloads it from spirebird.com — one-time/occasional, per C4)
Output: data/priors_cards.json (~small, committed) — per (character, card_id):
        {"s": score, "a": [tilt1, tilt2, tilt3]}
        score = shrunk Elo-based prior, roughly (-8..+8), 0 = replacement-level.
        a     = per-act tilt (8.1b): how much better/worse the card performs in
                each act vs. its own average, de-biased and zero-centered.

Key format observed: CARDID_<u>_<f>_CHARACTER_<build>  (u/f are 0/1 variant flags;
a handful of malformed keys lack the build suffix and are skipped).
Pooling: picked-weighted across builds/variants per (card, character).
Score: mean Elo shrunk toward neutral 1600 by sample size, /100.
Act tilt: per-act per-pick WAR = warA[i]/picked[i]; subtract the POPULATION per-act
mean M[i] (removes the survivorship inflation — act-3 picks come from winning runs),
then center per card and cap. Acts with too few picks contribute no tilt.
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
# below this an act's per-pick WAR is noisy AND biased (sparse-act picks skew toward
# winning decks — card-level survivorship); require solid sampling before tilting.
MIN_ACT_PICKS = 300
TILT_CAP = 1.0  # clamp per-act tilts; keeps the term a bounded secondary nudge
MIN_UPGRADE_PICKS = 100  # need both base and upgraded variants well-sampled for a delta
# Owner corrections to the community Elo (applied post-distill, recorded as
# owner_adj on the entry). COLOSSUS -0.8 (2026-07-24): "the global prior for
# Colossus is a bit high -- I picked it a lot when I started Ironclad and backed
# off once it became clear it wasn't working as well as I'd hoped"; passed it
# twice in one evening of shadow A/Bs, both times into decks it wouldn't serve.
OWNER_OVERRIDES: dict[tuple[str, str], float] = {
    ("IRONCLAD", "COLOSSUS"): -0.8,
}


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

    def new_acc() -> dict:
        return {
            "elo_w": 0.0,
            "picked": 0.0,
            "warA": [0.0, 0.0, 0.0],
            "pickedA": [0.0, 0.0, 0.0],
            "base_w": 0.0,  # Elo of the un-upgraded variant (flag 0), picked-weighted
            "base_p": 0.0,
            "upg_w": 0.0,  # Elo of the upgraded variant (flag 1)
            "upg_p": 0.0,
        }

    pooled: dict[tuple[str, str], dict] = defaultdict(new_acc)
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
        acc["elo_w"] += picked * float(elo)
        acc["picked"] += picked
        for i in range(3):
            acc["warA"][i] += float(entry.get(f"warA{i + 1}") or 0)
            acc["pickedA"][i] += float(entry.get(f"picked{i + 1}") or 0)
        # first flag after the card id is the upgrade flag (0=base, 1=upgraded)
        if entry["key"].split("_")[-4] == "1":
            acc["upg_w"] += picked * float(elo)
            acc["upg_p"] += picked
        else:
            acc["base_w"] += picked * float(elo)
            acc["base_p"] += picked

    # population per-act per-pick WAR (picked-weighted over acts with enough data)
    tot_w = [0.0, 0.0, 0.0]
    tot_p = [0.0, 0.0, 0.0]
    for acc in pooled.values():
        for i in range(3):
            if acc["pickedA"][i] >= MIN_ACT_PICKS:
                tot_w[i] += acc["warA"][i]
                tot_p[i] += acc["pickedA"][i]
    pop_mean = [tot_w[i] / tot_p[i] if tot_p[i] > 0 else 0.0 for i in range(3)]

    def act_tilts(acc: dict) -> list[float]:
        q: list[float | None] = [None, None, None]
        for i in range(3):
            if acc["pickedA"][i] >= MIN_ACT_PICKS:
                q[i] = acc["warA"][i] / acc["pickedA"][i] - pop_mean[i]
        avail = [x for x in q if x is not None]
        if not avail:
            return [0.0, 0.0, 0.0]
        center = sum(avail) / len(avail)
        return [
            round(max(-TILT_CAP, min(TILT_CAP, x - center)), 3) if x is not None else 0.0
            for x in q
        ]

    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for (card_id, character), acc in pooled.items():
        if acc["picked"] <= 0:
            continue
        mean_elo = acc["elo_w"] / acc["picked"]
        shrink = acc["picked"] / (acc["picked"] + SHRINK_K)
        score = (mean_elo - NEUTRAL_ELO) / 100.0 * shrink
        entry_out: dict = {"s": round(score, 3)}
        tilts = act_tilts(acc)
        if any(t != 0.0 for t in tilts):
            entry_out["a"] = tilts
        # upgrade value: Elo gained from upgrading (both variants well-sampled)
        if acc["base_p"] >= MIN_UPGRADE_PICKS and acc["upg_p"] >= MIN_UPGRADE_PICKS:
            delta = (acc["upg_w"] / acc["upg_p"] - acc["base_w"] / acc["base_p"]) / 100.0
            if abs(delta) >= 0.01:
                entry_out["u"] = round(delta, 3)
        out[character][card_id] = entry_out

    payload = {
        "meta": {
            "source": "spirebird.com cohort export",
            "cohort": COHORT,
            "total_runs_parsed": data.get("totalRunsParsed"),
            "generated_at": data.get("generatedAt"),
            "distilled_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "metric": f"s = picked-weighted mean Elo shrunk k={SHRINK_K:.0f}, "
            f"(elo-{NEUTRAL_ELO:.0f})/100; a = de-biased per-act tilt, "
            f"cap +-{TILT_CAP}, min {MIN_ACT_PICKS} picks/act; "
            f"u = upgrade Elo delta /100, min {MIN_UPGRADE_PICKS} picks/variant",
        },
        "cards": {ch: dict(sorted(cards_.items())) for ch, cards_ in sorted(out.items())},
    }
    for (char, cid), delta in OWNER_OVERRIDES.items():
        entry = payload["cards"].get(char, {}).get(cid)
        if entry is not None:
            entry["s"] = round(entry["s"] + delta, 3)
            entry["owner_adj"] = delta
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
