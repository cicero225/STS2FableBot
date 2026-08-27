"""Upgrade-disparity scan (owner line of experimentation, 2026-08-27).

True Grit's badness turned out to live almost entirely in the BASE copy
(-7.0pp/pick vs TG+ -1.8). This scans every card for the same signature:
per-variant (base vs upgraded-at-offer) ITT on the quasi-random offer design,
side by side with the tag table's upgrade flags (upgrade_unlocks,
exhaust_drops_on_upgrade). Big measured disparity WITHOUT a flag = candidate
to add one; a flagged card with NO measured disparity = candidate to review
(owner called flag changes the riskier half — this ranks, never edits).

Upgraded offers are ~20% of volume, so upgraded-side cells are thin; the
report keeps n visible and flags |gap| that clears a rough 2-sigma bar.

Usage: python scripts/upgrade_disparity.py [--since 2026-08-08] [--min-upg N]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.learn.data import jsonl_rows  # noqa: E402
from sts2bot.policy.drafttags import load_draft_tags  # noqa: E402

DS = ROOT / "logs" / "datasets"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--since", type=str, default="2026-08-08",
                    help="low-divergence window per drift_check (empty = full era)")
    ap.add_argument("--min-upg", type=int, default=40,
                    help="min upgraded-variant offers to report")
    args = ap.parse_args()
    ds = args.datasets

    runs = {r["run_id"]: r for r in jsonl_rows(ds / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    drafts = [d for d in jsonl_rows(ds / "drafts.jsonl")
              if d.get("outcome_valid") and d.get("config_hash") == era
              and d.get("victory") is not None
              and (not args.since
                   or (runs[d["run_id"]].get("started_at") or "") >= args.since)]

    act_rows: dict[int, list[dict]] = defaultdict(list)
    for d in drafts:
        act_rows[d.get("act") or 0].append(d)
    act_win = {a: sum(x["victory"] for x in v) / len(v)
               for a, v in act_rows.items()}

    # exact-variant offer collection (offer_counterfactuals strips '+')
    offered: dict[str, list[dict]] = defaultdict(list)
    picked_n: Counter[str] = Counter()
    for d in drafts:
        seen = set()
        for o in d["offers"]:
            k = o["key"]
            if k in seen:
                continue
            seen.add(k)
            offered[k].append(d)
            if d.get("picked") == k:
                picked_n[k] += 1

    def itt(key: str):
        off = offered.get(key) or []
        if not off:
            return None
        base = sum(act_win.get(d.get("act") or 0, 0.0) for d in off) / len(off)
        win = sum(d["victory"] for d in off) / len(off)
        pick = picked_n[key] / len(off)
        se = (base * (1 - base) / len(off)) ** 0.5
        return {"n": len(off), "pick": pick, "itt": win - base, "se": se,
                "per_pick": (win - base) / pick if pick >= 0.08 else None}

    tags = load_draft_tags()
    rows_out = []
    for key in list(offered):
        if key.endswith("+"):
            continue
        up = itt(key + "+")
        lo = itt(key)
        if up is None or lo is None or up["n"] < args.min_upg or lo["n"] < 100:
            continue
        gap = up["itt"] - lo["itt"]
        sig = gap / ((up["se"] ** 2 + lo["se"] ** 2) ** 0.5)
        entry = tags.get(key) or {}
        flags = []
        if entry.get("upgrade_unlocks"):
            flags.append("unlocks")
        if entry.get("exhaust_drops_on_upgrade"):
            flags.append("exh-drop")
        if entry.get("flat_adj_base"):
            flags.append("base-dock")
        rows_out.append({"card": key, "lo": lo, "up": up, "gap": gap,
                         "sig": sig, "flags": "/".join(flags) or "-"})
    rows_out.sort(key=lambda r: -abs(r["sig"]))

    def pp(r):
        return f"{100 * r['per_pick']:+.1f}pp" if r["per_pick"] is not None else "-"

    lines = ["# Upgrade disparity scan", "",
             f"Era {era}" + (f", since {args.since}" if args.since else "") +
             f"; {len(drafts)} draft rows. gap = upgraded-offer ITT minus "
             "base-offer ITT (win%); ~sig is a rough 2-sample z on thin "
             "upgraded cells — ranking, not verdicts.", "",
             "| card | base n | pick% | base/pick | upg n | pick% | upg/pick "
             "| gap | ~sig | flags |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows_out:
        lo, up = r["lo"], r["up"]
        lines.append(
            f"| {r['card']} | {lo['n']} | {100 * lo['pick']:.0f}% | {pp(lo)} "
            f"| {up['n']} | {100 * up['pick']:.0f}% | {pp(up)} "
            f"| {100 * r['gap']:+.1f}pp | {r['sig']:+.1f} | {r['flags']} |")

    # stratum confound: mechanically-impossible negatives (Expect a Fight+ is
    # strictly better than base yet measures worse) show the upgraded-offer
    # stratum carries its own outcome correlation (elite rewards / late
    # floors). Center reads on the median gap, not zero.
    med = sorted(r["gap"] for r in rows_out)[len(rows_out) // 2] if rows_out else 0.0
    lines += ["", f"**Background**: median gap {100 * med:+.1f}pp across "
              f"{len(rows_out)} cards — the upgraded-offer stratum is "
              "systematically confounded (elite-reward/late-floor contexts); "
              "judge cards against the MEDIAN, not zero, and require "
              "mechanical plausibility (cost/text step-change) before "
              "believing a gap."]

    flagged = {c for c, e in tags.items()
               if e.get("upgrade_unlocks") or e.get("exhaust_drops_on_upgrade")}
    seen_cards = {r["card"] for r in rows_out}
    lines += ["", "Flagged cards (upgrade_unlocks / exh-drop) with NO "
              "measurable disparity data in this slice: "
              + (", ".join(sorted(flagged - seen_cards)) or "(none)")]

    out = ROOT / "logs" / "reports" / "upgrade_disparity.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows_out)} cards)")
    for r in rows_out[:10]:
        print(f"  {r['card']}: gap {100 * r['gap']:+.1f}pp sig {r['sig']:+.1f} "
              f"[{r['flags']}] (base n={r['lo']['n']}, upg n={r['up']['n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
