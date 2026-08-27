"""Play-time audit of Bloodletting HP spending (follow-up to the 2026-08-27
conditional counterfactuals: draft context cleared the card — flat mild
negative everywhere — so the suspicion moved to HOW the planner spends the HP).

Scans acting combat records (full battle state) of dominant-era runs whose
deck held Bloodletting, and asks:

  1. How often is the bought energy simply unspent? (end-of-turn energy >= 2
     on a Bloodletting turn = the 3 HP bought nothing this turn)
  2. How low does the bot play it? (HP fraction at play time)
  3. How much does it cost per run/fight, and how many DEATHS carry
     meaningful Bloodletting self-spend in the fatal fight?

Reads logs/runs/ directly (the stage-0 fights table provides outcome joins).
Writes logs/reports/bloodletting_usage.md.

Usage: python scripts/audit_bloodletting.py [--card BLOODLETTING] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.learn.data import jsonl_rows  # noqa: E402

DS = ROOT / "logs" / "datasets"
LOGS = ROOT / "logs" / "runs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", default="BLOODLETTING")
    ap.add_argument("--hp-cost", type=int, default=3,
                    help="self HP cost per play (Bloodletting: 3)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    card = args.card

    runs = {r["run_id"]: r for r in jsonl_rows(DS / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    holders: set[str] = set()
    for table in ("drafts", "events", "rests"):
        for d in jsonl_rows(DS / f"{table}.jsonl"):
            if (d.get("config_hash") == era and d.get("outcome_valid")
                    and any(k.rstrip("+") == card for k in d.get("deck") or [])):
                holders.add(d["run_id"])
    fights_by_key: dict[tuple[str, int], dict] = {}
    era_fight_deltas: list[float] = []
    for f in jsonl_rows(DS / "fights.jsonl"):
        if f.get("config_hash") == era and f.get("outcome_valid"):
            fights_by_key[(f["run_id"], f["floor"])] = f
            if f.get("hp_delta") is not None:
                era_fight_deltas.append(f["hp_delta"])

    run_ids = sorted(holders)
    if args.limit:
        run_ids = run_ids[-args.limit:]
    print(f"era {era}: scanning {len(run_ids)} {card}-holding runs...")

    plays: list[dict] = []
    # (run, floor, round) -> {"n": plays this turn, "end_energy": ...}
    turns: dict[tuple, dict] = {}
    spend_by_fight: Counter[tuple] = Counter()
    for i, rid in enumerate(run_ids):
        path = LOGS / rid / "decisions.jsonl"
        if not path.is_file():
            continue
        try:
            for raw in path.open(encoding="utf-8"):
                if '"play_card"' not in raw and '"end_turn"' not in raw:
                    continue
                try:
                    r = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                act = r.get("action") or {}
                st = r.get("state") or {}
                p = st.get("player") or {}
                b = st.get("battle") or {}
                run_info = st.get("run") or {}
                floor, rnd = run_info.get("floor"), b.get("round")
                if act.get("action") == "play_card":
                    hand = p.get("hand") or []
                    ci = act.get("card_index")
                    if (ci is not None and 0 <= ci < len(hand)
                            and hand[ci].get("id") == card):
                        plays.append({
                            "run_id": rid, "floor": floor, "round": rnd,
                            "act": run_info.get("act"),
                            "hp": p.get("hp"), "max_hp": p.get("max_hp"),
                            "energy": p.get("energy"),
                        })
                        key = (rid, floor, rnd)
                        turns.setdefault(key, {"n": 0, "end_energy": None})
                        turns[key]["n"] += 1
                        spend_by_fight[(rid, floor)] += args.hp_cost
                elif act.get("action") == "end_turn":
                    key = (rid, floor, rnd)
                    if key in turns and turns[key]["end_energy"] is None:
                        turns[key]["end_energy"] = p.get("energy")
        except OSError:
            continue
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(run_ids)} runs...")

    lines = [f"# {card} play-time audit", "",
             f"Era {era}; {len(run_ids)} holding runs scanned; "
             f"{len(plays)} plays across {len(spend_by_fight)} fights "
             f"({len(turns)} turns).", ""]

    # 1. wasted-energy turns. Confound guard: in decks with hp-loss PAYOFFS
    # (Rupture / Tear Asunder / Inferno), a play with unspent energy can be a
    # deliberate trigger — split the metric by payoff-holding runs.
    payoff_cards = {"RUPTURE", "TEAR_ASUNDER", "INFERNO"}
    payoff_runs: set[str] = set()
    for table in ("drafts", "events", "rests"):
        for d in jsonl_rows(DS / f"{table}.jsonl"):
            if (d.get("config_hash") == era and d["run_id"] in holders
                    and any(k.rstrip("+") in payoff_cards
                            for k in d.get("deck") or [])):
                payoff_runs.add(d["run_id"])

    def _waste_line(label, items):
        known = [t for k, t in items if t["end_energy"] is not None]
        w2 = sum(1 for t in known if t["end_energy"] >= 2)
        w1 = sum(1 for t in known if t["end_energy"] >= 1)
        return (f"- {label}: {len(known)} turns; >=2 unspent "
                f"**{100 * w2 / max(1, len(known)):.1f}%**; >=1 unspent "
                f"{100 * w1 / max(1, len(known)):.1f}%")

    all_items = list(turns.items())
    lines += ["## Was the bought energy even spent?", "",
              _waste_line("all holding runs", all_items),
              _waste_line("runs WITHOUT hp-loss payoffs (clean waste)",
                          [(k, t) for k, t in all_items
                           if k[0] not in payoff_runs]),
              _waste_line("runs WITH Rupture/Tear Asunder/Inferno",
                          [(k, t) for k, t in all_items
                           if k[0] in payoff_runs]), ""]

    # 2. how low does it get played?
    fr = [p["hp"] / p["max_hp"] for p in plays
          if p.get("hp") and p.get("max_hp")]
    buckets = Counter("<25%" if f < 0.25 else "<50%" if f < 0.5 else ">=50%"
                      for f in fr)
    lines += ["## HP fraction at play time", ""]
    for k in ("<25%", "<50%", ">=50%"):
        lines.append(f"- {k}: {buckets.get(k, 0)} "
                     f"({100 * buckets.get(k, 0) / max(1, len(fr)):.1f}%)")
    acts = Counter(p.get("act") for p in plays)
    lines += ["", f"Plays by act: {dict(sorted(acts.items(), key=str))}", ""]

    # 3. cost + deaths carrying spend
    per_run = Counter()
    for (rid, _fl), s in spend_by_fight.items():
        per_run[rid] += s
    death_fights = []
    for key, s in spend_by_fight.items():
        f = fights_by_key.get(key)
        if f and f.get("died_here"):
            death_fights.append((s, f))
    heavy = [x for x in death_fights if x[0] >= 6]
    n_deaths_holding = sum(
        1 for rid in run_ids
        if runs.get(rid, {}).get("victory") is False)
    lines += ["## Cost and deaths", "",
              f"- mean HP spent per holding run: "
              f"{sum(per_run.values()) / max(1, len(per_run)):.1f} "
              f"(mean per fight-with-play: "
              f"{sum(spend_by_fight.values()) / max(1, len(spend_by_fight)):.1f})",
              f"- deaths IN a fight with {card} spend: {len(death_fights)} "
              f"(of {n_deaths_holding} deaths among holding runs); "
              f"mean spend in those fatal fights "
              f"{sum(s for s, _ in death_fights) / max(1, len(death_fights)):.1f} HP",
              f"- fatal fights with spend >= 6 HP (2+ plays): **{len(heavy)}**",
              ""]
    boss_deaths = Counter(" + ".join(f["enemies"]) for s, f in death_fights
                          if f.get("is_boss"))
    if boss_deaths:
        lines += ["Fatal boss fights with spend: "
                  + ", ".join(f"{k} x{v}" for k, v in
                              boss_deaths.most_common(6)), ""]

    # 4. context: fights with plays vs era baseline (descriptive only)
    deltas = [fights_by_key[k]["hp_delta"] for k in spend_by_fight
              if k in fights_by_key
              and fights_by_key[k].get("hp_delta") is not None]
    if deltas and era_fight_deltas:
        lines += ["## Context (descriptive, confounded — harder fights "
                  "invite more plays)", "",
                  f"- mean hp_delta of fights with {card} played: "
                  f"{sum(deltas) / len(deltas):+.1f} vs era all-fights "
                  f"{sum(era_fight_deltas) / len(era_fight_deltas):+.1f}", ""]

    out = ROOT / "logs" / "reports" / f"{card.lower()}_usage.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print("\n".join(lines[2:14]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
