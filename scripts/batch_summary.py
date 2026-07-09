"""Summarise the most recent run batch: Act-reach, deaths, relics, and elite appetite.

The point is to tell whether HP-aware elite-chasing (PLAN §8.2) is converting spare HP into
relics (deck power) without spiking deaths. Per run it reports where the run ended and what
killed it, the relics banked, how many elites were actually fought (the ground-truth elite
appetite), and boss-entry HP. Aggregates the batch, normalising elites_fought against the
elite opportunities offered, and with --compare prints the previous N runs for a before/after.

Usage: python scripts/batch_summary.py [--runs N] [--compare]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
COMBAT = {"monster", "elite", "boss"}
IN_FIGHT = COMBAT | {"hand_select"}


def _recs(run_dir: Path) -> list[dict]:
    text = (run_dir / "decisions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _relics_end(recs: list[dict]) -> list[str]:
    for r in reversed(recs):
        pl = (r.get("state") or {}).get("player")
        if pl and pl.get("relics") is not None:
            return [(x.get("name") or x.get("id") or "?") for x in pl["relics"]]
    return []


def _count_fights(recs: list[dict], ftype: str) -> int:
    n = i = 0
    while i < len(recs):
        if recs[i].get("state_type") == ftype:
            n += 1
            while i < len(recs) and recs[i].get("state_type") in IN_FIGHT:
                i += 1
        else:
            i += 1
    return n


def _boss_entry_hp(recs: list[dict]) -> int | None:
    for r in recs:
        if r.get("state_type") == "boss":
            pl = (r.get("state") or {}).get("player")
            if pl:
                return pl.get("hp")
    return None


def _elites_offered(recs: list[dict]) -> int:
    """Distinct map screens (deduped by act,col,row) where an elite was an immediate option —
    the elite *opportunities* the run saw, to normalise elites_fought against."""
    screens: set[tuple] = set()
    for r in recs:
        if r.get("state_type") != "map":
            continue
        st = r.get("state") or {}
        mp = st.get("map") or {}
        if any((o.get("type") or "").lower() == "elite" for o in (mp.get("next_options") or [])):
            pos = mp.get("current_position") or {}
            screens.add(((st.get("run") or {}).get("act"), pos.get("col"), pos.get("row")))
    return len(screens)


def summarise(run_dirs: list[Path], label: str) -> None:
    print(f"\n=== {label} ({len(run_dirs)} runs) ===")
    acts: list[int] = []
    relic_counts: list[int] = []
    elites_fought: list[int] = []
    off_tot = wins = 0
    for d in run_dirs:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        out = meta.get("outcome")
        recs = _recs(d)
        relics = _relics_end(recs)
        ef = _count_fights(recs, "elite")
        off_tot += _elites_offered(recs)
        elites_fought.append(ef)
        relic_counts.append(len(relics))
        if not out:
            print(f"  {d.name[:19]}  (in progress)  relics={len(relics)} elites_fought={ef}")
            continue
        acts.append(out.get("act") or 0)
        wins += 1 if out.get("victory") else 0
        kb = (out.get("killed_by_encounter") or "").replace("ENCOUNTER.", "") or out.get("status")
        bhp = _boss_entry_hp(recs)
        bhp_s = f" boss@{bhp}hp" if bhp is not None else ""
        print(
            f"  A{out.get('act') or '?'} f{out.get('floor') or '?':<2} "
            f"{'WIN ' if out.get('victory') else 'loss'} "
            f"relics={len(relics):<2} elites_fought={ef}{bhp_s}  "
            f"killed_by={kb}  [{','.join(relics)}]"
        )
    n = max(1, len(acts))
    relic_avg = sum(relic_counts) / max(1, len(relic_counts))
    elite_avg = sum(elites_fought) / max(1, len(elites_fought))
    print(
        f"  -- wins={wins}/{len(acts)}  act-reach avg={sum(acts) / n:.2f} "
        f"(max {max(acts) if acts else 0})  relics avg={relic_avg:.1f}  "
        f"elites_fought avg={elite_avg:.1f} (of {off_tot} elite chances offered)"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--compare", action="store_true", help="also show the previous N runs")
    args = ap.parse_args()
    dirs = sorted(LOGS.glob("*/"), key=lambda d: (d / "meta.json").stat().st_mtime)
    latest = dirs[-args.runs :]
    if args.compare and len(dirs) > args.runs:
        summarise(dirs[-2 * args.runs : -args.runs], f"previous {args.runs}")
    summarise(latest, f"latest {args.runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
