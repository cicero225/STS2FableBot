"""Global legacy-drift check (owner Q 2026-08-27): how much of the logged era
would TODAY'S bot decide differently?

The config-era tables (counterfactuals, audits) treat era f0e54b35 as one
policy — but the config hash pins WEIGHTS, not code, and ~50+ policy commits
landed inside it (the Bloodletting waste turned out to be legacy-code states).
Two instruments:

  1. Code-vintage tagging: git log timestamps over sts2bot/data/config joined
     against run started_at — every run gets the commit that was HEAD when it
     ran (assumes batches ran from committed HEAD; mid-session uncommitted
     edits blur single runs, not aggregates).
  2. Draft divergence replay: policies are pure functions, so re-run TODAY'S
     StandardRouter on the logged card_reward states and compare picks. The
     divergence rate over time is the direct drift measure, and the per-card
     flip table says exactly which counterfactual rows are contaminated.
     (ctx approximation: act_boss_name is replayed from the logged map data;
     seen-elite memory starts fresh — a minor, noted divergence source.)

Combat decisions are NOT replayed here (full DFS per state — hours); the
draft layer is where the counterfactual tables live anyway.

Usage: python scripts/drift_check.py [--sample-every N] [--limit-runs N]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sts2bot.client.models import parse_state  # noqa: E402
from sts2bot.kb.config import load_policy_config  # noqa: E402
from sts2bot.learn.data import jsonl_rows  # noqa: E402
from sts2bot.policy.base import LoopContext  # noqa: E402
from sts2bot.policy.standard import StandardRouter  # noqa: E402

DS = ROOT / "logs" / "datasets"
LOGS = ROOT / "logs" / "runs"


def vintage_map() -> list[tuple[datetime, str, str]]:
    out = subprocess.run(
        ["git", "log", "--format=%H|%cI|%s", "--reverse", "--",
         "sts2bot", "data", "config"],
        capture_output=True, text=True, cwd=ROOT, check=True).stdout
    rows = []
    for line in out.splitlines():
        h, iso, subj = line.split("|", 2)
        rows.append((datetime.fromisoformat(iso), h[:9], subj[:60]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-every", type=int, default=4,
                    help="replay every Nth draft decision (1 = all)")
    ap.add_argument("--limit-runs", type=int, default=None)
    args = ap.parse_args()

    runs = {r["run_id"]: r for r in jsonl_rows(DS / "runs.jsonl")}
    era = Counter(r["config_hash"] for r in runs.values()
                  if r["outcome_valid"]).most_common(1)[0][0]
    era_runs = [r for r in runs.values()
                if r["outcome_valid"] and r["config_hash"] == era]
    boss_by_run: dict[str, dict] = {
        r["run_id"]: r.get("boss_by_act") or {} for r in era_runs}

    # ---- 1. vintage segmentation ----
    vm = vintage_map()
    def vintage_of(started_at: str):
        t = datetime.fromisoformat(started_at)
        lo, hi = 0, len(vm)
        while lo < hi:
            mid = (lo + hi) // 2
            if vm[mid][0] <= t:
                lo = mid + 1
            else:
                hi = mid
        return vm[lo - 1] if lo else vm[0]

    seg = Counter(vintage_of(r["started_at"])[1] for r in era_runs)
    lines = ["# Legacy drift check", "",
             f"Era {era}: {len(era_runs)} valid runs spanning "
             f"**{len(seg)} distinct code vintages** "
             f"({len(vm)} policy-relevant commits repo-wide).", "",
             "Largest vintage segments (runs per HEAD commit):", ""]
    subj = {h: s for _, h, s in vm}
    for h, n in seg.most_common(10):
        lines.append(f"- `{h}` ({n} runs): {subj.get(h, '?')}")

    # ---- 2. draft divergence replay under TODAY'S policy ----
    router = StandardRouter(load_policy_config())
    ordered = sorted(era_runs, key=lambda r: r["started_at"])
    if args.limit_runs:
        ordered = ordered[-args.limit_runs:]
    n_replayed = n_div = n_err = 0
    by_week: dict[str, list[int]] = defaultdict(list)
    flips: Counter[tuple[str, str]] = Counter()
    seen_card: Counter[str] = Counter()
    k = 0
    for i, r in enumerate(ordered):
        rid = r["run_id"]
        path = LOGS / rid / "decisions.jsonl"
        if not path.is_file():
            continue
        week = r["started_at"][:10][:7] + "-w" + str(
            (int(r["started_at"][8:10]) - 1) // 7 + 1)
        try:
            for raw in path.open(encoding="utf-8"):
                if '"card_reward"' not in raw or (
                        '"select_card_reward"' not in raw
                        and '"skip' not in raw):
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if rec.get("state_type") != "card_reward" or not rec.get("action"):
                    continue
                k += 1
                if k % args.sample_every:
                    continue
                st_dict = rec["state"]
                logged = rec["action"]
                logged_idx = (logged.get("card_index")
                              if logged.get("action") == "select_card_reward"
                              else None)
                try:
                    st = parse_state(st_dict)
                    act_now = (st_dict.get("run") or {}).get("act")
                    ctx = LoopContext(screen_mem={
                        "act_boss_name":
                        boss_by_run.get(rid, {}).get(str(act_now))})
                    d = router.decide(st, ctx)
                    payload = d.action.payload() if hasattr(d, "action") else {}
                    new_idx = (payload.get("card_index")
                               if payload.get("action") == "select_card_reward"
                               else None)
                except Exception:
                    n_err += 1
                    continue
                n_replayed += 1
                cards = (st_dict.get("card_reward") or {}).get("cards") or []
                def name_of(idx, cards=cards):
                    if idx is None:
                        return "SKIP"
                    return next((c.get("id") for c in cards
                                 if c.get("index") == idx), "?")
                for c in cards:
                    seen_card[c.get("id")] += 1
                div = new_idx != logged_idx
                n_div += div
                by_week[week].append(int(div))
                if div:
                    flips[(name_of(logged_idx), name_of(new_idx))] += 1
        except OSError:
            continue
        if (i + 1) % 250 == 0:
            print(f"  {i + 1}/{len(ordered)} runs; divergence so far "
                  f"{100 * n_div / max(1, n_replayed):.1f}%")

    lines += ["", "## Draft divergence: today's bot vs the logged era", "",
              f"- {n_replayed} draft decisions replayed "
              f"(every {args.sample_every}th; {n_err} parse/replay errors)",
              f"- overall divergence: **{n_div} "
              f"({100 * n_div / max(1, n_replayed):.1f}%)**", "",
              "| week | replayed | divergence |", "|---|---|---|"]
    for wk in sorted(by_week):
        v = by_week[wk]
        lines.append(f"| {wk} | {len(v)} | {100 * sum(v) / len(v):.1f}% |")
    lines += ["", "Top pick flips (logged -> today):", "",
              "| logged pick | today's pick | n |", "|---|---|---|"]
    for (old, new), n in flips.most_common(20):
        lines.append(f"| {old} | {new} | {n} |")
    lines += ["", "Caveats: seen-elite ctx memory replays as fresh (minor); "
              "runs launched from uncommitted mid-session code blur single "
              "runs; combat decisions not replayed (DFS cost) — this bounds "
              "DRAFT-table contamination only."]

    out = ROOT / "logs" / "reports" / "drift_check.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"divergence {100 * n_div / max(1, n_replayed):.1f}% "
          f"({n_div}/{n_replayed}), {len(seg)} vintages, {n_err} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
