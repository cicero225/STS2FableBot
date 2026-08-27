"""First-look report over the stage-0 dataset (scripts/build_run_dataset.py).

Reads logs/datasets/*.jsonl and writes a markdown summary: win rate by config
era, per-boss lethality (the boss wall, quantified), draft pick rates when
offered, and event-choice distributions. Doubles as the drafting-review
substrate (owner ask 2026-08-19: reviewable decision aggregates).

Usage: python scripts/dataset_summary.py [--datasets DIR] [--out FILE]
                                         [--era-runs N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = ROOT / "logs" / "datasets"

sys.path.insert(0, str(ROOT))

from sts2bot.policy.forward import canonical_enemy_name  # noqa: E402


def _rows(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--era-runs", type=int, default=300,
                    help="how many latest runs count as the 'recent era'")
    args = ap.parse_args()
    ds = args.datasets

    runs = list(_rows(ds / "runs.jsonl"))
    valid = [r for r in runs if r["outcome_valid"]]
    lines = ["# Dataset summary — stage 0 first look", ""]
    lines.append(f"Runs: {len(runs)} logged, {len(valid)} outcome-valid, "
                 f"{sum(r['victory'] for r in valid)} wins "
                 f"({100 * sum(r['victory'] for r in valid) / max(1, len(valid)):.1f}%)")

    # win rate by config era (order of first appearance)
    era_order: list[str] = []
    era_runs: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        h = r.get("config_hash") or "?"
        if h not in era_runs:
            era_order.append(h)
        era_runs[h].append(r)
    lines += ["", "## Win rate by config era (chronological, last 12)", "",
              "| era | runs | wins | win% | first seen |",
              "|---|---|---|---|---|"]
    for h in era_order[-12:]:
        rs = era_runs[h]
        w = sum(r["victory"] for r in rs)
        lines.append(f"| {h} | {len(rs)} | {w} | "
                     f"{100 * w / len(rs):.1f}% | {rs[0]['started_at'][:10]} |")

    # per-boss lethality across all valid runs and the recent era
    recent_ids = {r["run_id"] for r in valid[-args.era_runs:]}
    fights = [f for f in _rows(ds / "fights.jsonl") if f["outcome_valid"]]
    boss = [f for f in fights if f["is_boss"]]

    def boss_table(rows: list[dict], title: str) -> None:
        agg: dict[str, list[dict]] = defaultdict(list)
        for f in rows:
            # specimen suffixes (Test Subject #C20) are per-instance — collapse
            agg[" + ".join(canonical_enemy_name(e) for e in f["enemies"])
                or "?"].append(f)
        lines.extend(["", f"## {title}", "",
                      "| boss | fights | deaths | death% | mean hp delta |",
                      "|---|---|---|---|---|"])
        for name, fs in sorted(agg.items(),
                               key=lambda kv: -sum(bool(f.get("died_here"))
                                                   for f in kv[1])):
            d = sum(bool(f.get("died_here")) for f in fs)
            hd = [f["hp_delta"] for f in fs if f["hp_delta"] is not None]
            mean = sum(hd) / len(hd) if hd else 0.0
            lines.append(f"| {name} | {len(fs)} | {d} | "
                         f"{100 * d / len(fs):.0f}% | {mean:+.1f} |")

    boss_table(boss, "Boss lethality — all valid runs")
    boss_table([f for f in boss if f["run_id"] in recent_ids],
               f"Boss lethality — recent era (last {args.era_runs} valid runs)")

    # draft pick rate when offered (recent era)
    drafts = [d for d in _rows(ds / "drafts.jsonl")
              if d["outcome_valid"] and d["run_id"] in recent_ids]
    offered: Counter[str] = Counter()
    picked: Counter[str] = Counter()
    skips = 0
    for d in drafts:
        for o in d["offers"]:
            offered[o["key"].rstrip("+")] += 1
        if d["picked"]:
            picked[d["picked"].rstrip("+")] += 1
        else:
            skips += 1
    lines += ["", f"## Draft pick rates — recent era "
              f"({len(drafts)} drafts, {skips} skips "
              f"[{100 * skips / max(1, len(drafts)):.0f}%])", "",
              "| card | offered | picked | pick% |", "|---|---|---|---|"]
    common = [(c, n) for c, n in offered.most_common() if n >= 20]
    common.sort(key=lambda kv: -(picked[kv[0]] / kv[1]))
    for c, n in common[:25]:
        lines.append(f"| {c} | {n} | {picked[c]} | {100 * picked[c] / n:.0f}% |")
    lines.append("| ... | | | |")
    for c, n in common[-10:]:
        lines.append(f"| {c} | {n} | {picked[c]} | {100 * picked[c] / n:.0f}% |")

    # event choices (recent era)
    events = [e for e in _rows(ds / "events.jsonl")
              if e["outcome_valid"] and e["run_id"] in recent_ids]
    by_event: dict[str, Counter] = defaultdict(Counter)
    for e in events:
        by_event[e["event_name"] or "?"][e["picked_title"] or "?"] += 1
    lines += ["", f"## Event choices — recent era ({len(events)} choices)", ""]
    for name, ctr in sorted(by_event.items(), key=lambda kv: -sum(kv[1].values()))[:15]:
        total = sum(ctr.values())
        tops = ", ".join(f"{t} ×{n}" for t, n in ctr.most_common(4))
        lines.append(f"- **{name}** ({total}): {tops}")

    out = args.out or (ROOT / "logs" / "reports" / "dataset_summary_stage0.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print("\n".join(lines[:6]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
