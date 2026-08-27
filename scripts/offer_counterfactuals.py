"""Offer-set counterfactuals: the model-free pick signal (PLAN §9).

The value-head ΔV failed face validity (observational confounding: deck
archetype ↔ winning). This takes the assumption-light route instead: card
OFFERS are quasi-random given the act, so "was C offered here?" is a natural
experiment. For each card, compare outcomes of draft rows where it was
offered vs the same-act baseline (intention-to-treat); dividing the ITT
delta by the pick rate approximates the per-pick effect for cards the bot
usually takes.

Caveats baked into the report: rows within a run share outcomes (effective n
is closer to run count), so a run-level offered-ever comparison is included
for the most-picked cards; power is weak for small effects — this ranks
candidates for snapshot A/Bs, it does not settle them (owner steer
2026-08-18: batch statistics resolve small effects too slowly).

Usage: python scripts/offer_counterfactuals.py [--datasets DIR] [--min-offers N]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.learn.data import jsonl_rows  # noqa: E402

DS = ROOT / "logs" / "datasets"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    ap.add_argument("--min-offers", type=int, default=80)
    ap.add_argument("--since", type=str, default=None,
                    help="only runs started on/after this date (YYYY-MM-DD) — "
                    "drift_check.md showed early-era picks diverge up to 38%% "
                    "from current code, so late-slice reruns test robustness")
    ap.add_argument("--out-name", type=str, default="offer_counterfactuals.md")
    args = ap.parse_args()
    ds = args.datasets

    runs = {r["run_id"]: r for r in jsonl_rows(ds / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    ok_runs = {rid for rid, r in runs.items()
               if not args.since or (r.get("started_at") or "") >= args.since}
    drafts = [d for d in jsonl_rows(ds / "drafts.jsonl")
              if d.get("outcome_valid") and d.get("config_hash") == era
              and d.get("victory") is not None and d["run_id"] in ok_runs]

    # per-act baselines over ALL era draft rows
    act_rows: dict[int, list[dict]] = defaultdict(list)
    for d in drafts:
        act_rows[d.get("act") or 0].append(d)

    def _mean(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    stats: dict[str, dict] = defaultdict(lambda: {
        "offered": [], "picked": 0})
    for d in drafts:
        seen = set()
        for o in d["offers"]:
            c = o["key"].rstrip("+")
            if c in seen:  # double-offer in one reward: count once
                continue
            seen.add(c)
            stats[c]["offered"].append(d)
            if (d.get("picked") or "").rstrip("+") == c:
                stats[c]["picked"] += 1

    rows_out = []
    for card, s in stats.items():
        off = s["offered"]
        if len(off) < args.min_offers:
            continue
        pick_rate = s["picked"] / len(off)
        # act-weighted baseline: expected outcome given the offer's act mix
        n_by_act = Counter(d.get("act") or 0 for d in off)
        base_win = sum(
            n * (_mean(act_rows[a], "victory") or 0.0)
            for a, n in n_by_act.items()) / len(off)
        base_hp = sum(
            n * (_mean(act_rows[a], "hp_delta_next3") or 0.0)
            for a, n in n_by_act.items()) / len(off)
        win_off = _mean(off, "victory") or 0.0
        hp_off = _mean(off, "hp_delta_next3")
        itt = win_off - base_win
        # rough binomial SE on the offered-rows win%; understates the true SE
        # (rows within a run share outcomes) — the sigma column is a
        # DISCOUNT-ME flag, not a test
        se = (base_win * (1 - base_win) / len(off)) ** 0.5
        rows_out.append({
            "card": card, "n": len(off), "pick": pick_rate,
            "win_off": win_off, "itt": itt, "sigma": itt / se if se else 0.0,
            "per_pick": (itt / pick_rate) if pick_rate >= 0.10 else None,
            "hp_itt": (hp_off - base_hp) if hp_off is not None else None,
        })

    rows_out.sort(key=lambda r: -(r["per_pick"]
                                  if r["per_pick"] is not None else r["itt"]))
    lines = [
        "# Offer-set counterfactuals (model-free pick signal)", "",
        f"Era {era}; {len(drafts)} draft rows. ITT = win% of rows where the "
        "card was OFFERED minus the act-weighted baseline win%; per-pick = "
        "ITT / pick rate (only when pick rate >= 10%). hpITT = same for mean "
        "HP delta over the next 3 fights. Rows within a run share outcomes — "
        "treat as ranking for snapshot A/Bs, not verdicts.", "",
        "| card | offers | pick% | ITT win | ~sigma | per-pick | hpITT |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows_out:
        pp = f"{100 * r['per_pick']:+.1f}pp" if r["per_pick"] is not None else "-"
        hp = f"{r['hp_itt']:+.1f}" if r["hp_itt"] is not None else "-"
        lines.append(
            f"| {r['card']} | {r['n']} | {100 * r['pick']:.0f}% "
            f"| {100 * r['itt']:+.1f}pp | {r['sigma']:+.1f} | {pp} | {hp} |")

    # run-level ITT with a FIXED exposure window: treatment = offered within
    # the run's first 3 draft rows. ("Offered ever" is length-biased — deeper
    # runs see more offers, so every staple looked run-winning; the first
    # version of this table fell for exactly that.)
    lines += ["", "## Run-level ITT (offered in the run's first 3 drafts, "
              "top-picked cards)", "",
              "| card | runs offered | win% | runs not | win% | delta |",
              "|---|---|---|---|---|---|"]
    first3: dict[str, list[dict]] = defaultdict(list)
    for d in drafts:
        first3[d["run_id"]].append(d)
    early_offers: dict[str, set] = defaultdict(set)
    eligible = set()
    for run_id, ds_run in first3.items():
        ds_run.sort(key=lambda d: d["seq"])
        if len(ds_run) < 3:
            continue
        eligible.add(run_id)
        for d in ds_run[:3]:
            for o in d["offers"]:
                early_offers[o["key"].rstrip("+")].add(run_id)
    era_runs = [r for r in runs.values()
                if r["outcome_valid"] and r["config_hash"] == era
                and r["run_id"] in eligible and r["run_id"] in ok_runs]
    staples = sorted(rows_out, key=lambda r: -r["pick"])[:15]
    for r in staples:
        got = early_offers[r["card"]]
        a = [x for x in era_runs if x["run_id"] in got]
        b = [x for x in era_runs if x["run_id"] not in got]
        if len(a) < 50 or len(b) < 50:
            continue
        wa = sum(x["victory"] for x in a) / len(a)
        wb = sum(x["victory"] for x in b) / len(b)
        lines.append(f"| {r['card']} | {len(a)} | {100 * wa:.1f}% "
                     f"| {len(b)} | {100 * wb:.1f}% | {100 * (wa - wb):+.1f}pp |")

    out = ROOT / "logs" / "reports" / args.out_name
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows_out)} cards)")
    for r in rows_out[:8]:
        print(f"  best: {r['card']} per-pick "
              f"{r['per_pick'] and round(100 * r['per_pick'], 1)}pp n={r['n']}")
    for r in rows_out[-8:]:
        print(f"  worst: {r['card']} per-pick "
              f"{r['per_pick'] and round(100 * r['per_pick'], 1)}pp n={r['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
