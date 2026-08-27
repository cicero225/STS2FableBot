"""Conditional offer counterfactuals (owner thoughts #2/#3, 2026-08-27).

Extends scripts/offer_counterfactuals.py's quasi-random-offer design with
conditioning:

  A. Act-stratified ITT — is pick value act-dependent (owner #3)? Also the
     Bloodletting drafted-too-early hypothesis.
  B. Needs-met ITT — for focus cards, split offered rows by whether the
     card's OWN tag-table needs are met at offer time (providers >= threshold
     via the same drafttags lens drafting uses). Tests the tag machinery
     against outcomes: if the needs are right, ITT should be better when met.
  C. Companion conditioning — ITT split by presence of specific staple/engine
     cards in the deck at offer time; only standout gaps are printed.

All baselines are act-weighted within the SAME stratum (rows satisfying the
condition), so the comparison stays offered-vs-not among like decks. Power
shrinks per cell — direction, not verdicts (snapshot A/Bs settle things).

Usage: python scripts/conditional_counterfactuals.py [--datasets DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.learn.data import jsonl_rows  # noqa: E402
from sts2bot.learn.features import _tag_provides, cards_from_keys  # noqa: E402
from sts2bot.policy.drafttags import deck_tag_weights, load_draft_tags  # noqa: E402

DS = ROOT / "logs" / "datasets"

# owner-flagged (2026-08-27 review) + both extremes of the ITT table
FOCUS = [
    "BLOODLETTING", "HOWL_FROM_BEYOND", "EVIL_EYE", "COLOSSUS", "BRAND",
    "PACTS_END", "TRUE_GRIT", "ASHEN_STRIKE", "RUPTURE", "INFERNO",
    "STAMPEDE", "SWORD_BOOMERANG", "WHIRLWIND", "TREMBLE",
    "TEAR_ASUNDER", "MANGLE", "AGGRESSION", "FEED",
]
COMPANIONS = [
    "BLOODLETTING", "INFLAME", "DOMINATE", "TRUE_GRIT", "BURNING_PACT",
    "FEEL_NO_PAIN", "BATTLE_TRANCE", "POMMEL_STRIKE", "UPPERCUT", "BULLY",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=DS)
    args = ap.parse_args()
    ds = args.datasets

    runs = {r["run_id"]: r for r in jsonl_rows(ds / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    drafts = [d for d in jsonl_rows(ds / "drafts.jsonl")
              if d.get("outcome_valid") and d.get("config_hash") == era
              and d.get("victory") is not None]
    catalog = json.loads(
        (ROOT / "data" / "card_catalog.json").read_text(encoding="utf-8"),
    )["cards"]
    tags = load_draft_tags()

    # per-row: act, win, deck set, tag-provider counts (drafting's own lens)
    print(f"era {era}: {len(drafts)} rows; computing per-row tag counts...")
    for d in drafts:
        cards = cards_from_keys(d["deck"], catalog)
        counts = deck_tag_weights(cards)
        counts.update(_tag_provides(cards, tags))
        d["_tags"] = counts
        d["_deck_set"] = {k.rstrip("+") for k in d["deck"]}
        d["_act"] = d.get("act") or 0

    offered_rows: dict[str, list[dict]] = defaultdict(list)
    picked_in: dict[str, set[int]] = defaultdict(set)
    for i, d in enumerate(drafts):
        d["_i"] = i
        seen = set()
        for o in d["offers"]:
            c = o["key"].rstrip("+")
            if c in seen:
                continue
            seen.add(c)
            offered_rows[c].append(d)
            if (d.get("picked") or "").rstrip("+") == c:
                picked_in[c].add(i)

    def itt(card: str, cond) -> tuple[float, float, int, float] | None:
        """(ITT, per-pick-or-nan, n_offered, pick_rate) among rows where
        cond(row) holds; baseline = act-weighted win% of ALL cond rows."""
        off = [d for d in offered_rows[card] if cond(d)]
        if len(off) < 60:
            return None
        pool_by_act: dict[int, list[dict]] = defaultdict(list)
        for d in drafts:
            if cond(d):
                pool_by_act[d["_act"]].append(d)
        n_by_act = Counter(d["_act"] for d in off)
        base = sum(
            n * (sum(x["victory"] for x in pool_by_act[a])
                 / max(1, len(pool_by_act[a])))
            for a, n in n_by_act.items()) / len(off)
        win = sum(d["victory"] for d in off) / len(off)
        pick = sum(1 for d in off if d["_i"] in picked_in[card]) / len(off)
        return (win - base, (win - base) / pick if pick >= 0.08 else float("nan"),
                len(off), pick)

    lines = ["# Conditional offer counterfactuals", "",
             f"Era {era}; {len(drafts)} draft rows. Same ITT design as "
             "offer_counterfactuals.md, conditioned; baselines act-weighted "
             "within each stratum. Cells under 60 offers are dropped; treat "
             "everything as direction, not verdict.", ""]

    # ---- A: act-stratified, all cards with volume ----
    lines += ["## A. Act-stratified ITT (per-pick where pick% >= 8%)", "",
              "| card | a1 n | a1/pick | a2 n | a2/pick | a3 n | a3/pick |",
              "|---|---|---|---|---|---|---|"]
    vol = sorted((c for c, off in offered_rows.items() if len(off) >= 400),
                 key=str)
    for c in vol:
        cells = []
        for a in (1, 2, 3):
            r = itt(c, lambda d, a=a: d["_act"] == a)
            if r is None:
                cells.append("- | -")
            else:
                pp = f"{100 * r[1]:+.0f}pp" if r[1] == r[1] else "-"
                cells.append(f"{r[2]} | {pp}")
        lines.append(f"| {c} | " + " | ".join(cells) + " |")

    # ---- B: needs-met vs unmet for focus cards ----
    lines += ["", "## B. Focus cards: ITT with own tag-table needs met vs "
              "unmet", "",
              "| card | need | met n | met pick% | met/pick | unmet n | "
              "unmet pick% | unmet/pick |",
              "|---|---|---|---|---|---|---|---|"]
    for c in FOCUS:
        needs = (tags.get(c) or {}).get("needs") or []
        if not needs:
            lines.append(f"| {c} | (no needs in table) | | | | | | |")
            continue
        for nd in needs:
            tag, thr = nd["tag"], nd["threshold"]

            def met(d, tag=tag, thr=thr):
                return d["_tags"].get(tag, 0.0) >= thr

            rm = itt(c, met)
            ru = itt(c, lambda d, m=met: not m(d))
            def fmt(r):
                if r is None:
                    return "- | - | -"
                pp = f"{100 * r[1]:+.0f}pp" if r[1] == r[1] else "-"
                return f"{r[2]} | {100 * r[3]:.0f}% | {pp}"
            lines.append(f"| {c} | {tag}>={thr} | {fmt(rm)} | {fmt(ru)} |")

    # ---- C: companion standouts for focus cards ----
    lines += ["", "## C. Companion conditioning (standout gaps only: "
              "|gap| >= 5pp per-pick, both cells n >= 100)", "",
              "| card | companion in deck | with n | with/pick | without n | "
              "without/pick |",
              "|---|---|---|---|---|---|"]
    found = 0
    for c in FOCUS:
        for comp in COMPANIONS:
            if comp == c:
                continue

            def has(d, comp=comp):
                return comp in d["_deck_set"]

            rw = itt(c, has)
            ro = itt(c, lambda d, h=has: not h(d))
            if rw is None or ro is None or rw[2] < 100 or ro[2] < 100:
                continue
            if rw[1] != rw[1] or ro[1] != ro[1]:
                continue
            if abs(rw[1] - ro[1]) < 0.05:
                continue
            found += 1
            lines.append(
                f"| {c} | {comp} | {rw[2]} | {100 * rw[1]:+.0f}pp "
                f"| {ro[2]} | {100 * ro[1]:+.0f}pp |")
    if not found:
        lines.append("| (none cleared the bar) | | | | | |")

    out = ROOT / "logs" / "reports" / "conditional_counterfactuals.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
