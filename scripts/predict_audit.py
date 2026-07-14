"""Prediction-vs-reality audit: where does the planner's model diverge from the game?

Owner idea (2026-07-14): the planner PREDICTS the turn's outcome (hp_loss in scores,
and the damage its plan deals). The game then delivers the truth. Systematic gaps
between the two are unmodeled mechanics — a self-verification harness.

Runs POST-HOC over the run logs (no runtime cost, no policy contamination), so it
audits the whole existing corpus. Two checks per player turn:

  * HP: predicted hp_loss (scores) vs actual HP delta to the next player turn.
    Catches incoming/block/thorns/DoT modeling gaps.
  * DAMAGE: the plan's projected enemy damage vs the enemy HP actually lost that turn.
    Catches damage-model gaps (this class is what the Strength double-count was).

Single mismatches are noise (randomness, unmodeled potions). SYSTEMATIC ones are bugs,
so results are bucketed by enemy / player-status / relic and ranked by
frequency x magnitude. Usage:  python scripts/predict_audit.py [--limit N] [--min-n 5]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 2  # HP within this of prediction = agreement (rounding, chip)


def _player_turn_states(path: str):
    """Yield (decision_with_scores, next_player_state) pairs for combat turns."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            st = d.get("state") or {}
            if not (st.get("battle") and st.get("player")):
                continue
            rows.append(d)

    # a turn = the LAST scored decision of round R, matched against the first state of R+1
    by_round: dict[int, list] = defaultdict(list)
    for d in rows:
        b = d["state"]["battle"]
        rnd = b.get("round")
        if rnd is not None:
            by_round[rnd].append(d)
    for rnd in sorted(by_round):
        cur = by_round[rnd]
        nxt = by_round.get(rnd + 1)
        if not nxt:
            continue
        scored = [d for d in cur if (d.get("scores") or {}).get("hp_loss") is not None]
        if not scored:
            continue
        yield scored[-1], cur[0], nxt[0]


def audit(paths, min_n: int):
    hp_buckets = defaultdict(list)   # signature -> [(pred, actual)]
    dmg_buckets = defaultdict(list)
    totals = {"turns": 0, "hp_ok": 0, "dmg_ok": 0}

    for path in paths:
        try:
            pairs = list(_player_turn_states(path))
        except (OSError, KeyError):
            continue
        for last, first, nxt in pairs:
            sc = last.get("scores") or {}
            pred_loss = sc.get("hp_loss")
            if pred_loss is None:
                continue
            pl0, pl1 = first["state"]["player"], nxt["state"]["player"]
            e0 = {e["entity_id"]: e for e in first["state"]["battle"].get("enemies") or []}
            e1 = {e["entity_id"]: e for e in nxt["state"]["battle"].get("enemies") or []}
            if pl0.get("hp") is None or pl1.get("hp") is None:
                continue
            totals["turns"] += 1

            enemies = ",".join(sorted({e.get("name", "?") for e in e0.values()}))
            statuses = ",".join(sorted({s.get("id", "") for s in (pl0.get("status") or [])}))
            relics = ",".join(sorted({r.get("id", "") for r in (pl0.get("relics") or [])}))

            # --- HP check
            actual_loss = pl0["hp"] - pl1["hp"]
            if abs(actual_loss - pred_loss) <= TOL:
                totals["hp_ok"] += 1
            else:
                hp_buckets[("enemy", enemies)].append((pred_loss, actual_loss))
                if statuses:
                    hp_buckets[("status", statuses)].append((pred_loss, actual_loss))

            # --- DAMAGE check: what the plan expected to deal vs what the enemies lost
            pred_dmg = sc.get("plan_damage")
            if pred_dmg is None:
                continue
            actual_dmg = sum(max(0, e0[k]["hp"] - e1.get(k, {}).get("hp", 0))
                             for k in e0 if k in e1)
            if abs(actual_dmg - pred_dmg) <= TOL:
                totals["dmg_ok"] += 1
            else:
                dmg_buckets[("enemy", enemies)].append((pred_dmg, actual_dmg))
                if statuses:
                    dmg_buckets[("status", statuses)].append((pred_dmg, actual_dmg))
                if relics:
                    dmg_buckets[("relic", relics)].append((pred_dmg, actual_dmg))

    def report(name, buckets):
        print(f"\n=== {name}: systematic divergences (n >= {min_n}) ===")
        rows = []
        for (kind, sig), obs in buckets.items():
            if len(obs) < min_n:
                continue
            bias = sum(a - p for p, a in obs) / len(obs)  # + = game did MORE than predicted
            rows.append((abs(bias) * len(obs), kind, sig, len(obs), bias))
        rows.sort(reverse=True)
        if not rows:
            print("  (none)")
        for _, kind, sig, n, bias in rows[:15]:
            direction = "MORE than predicted" if bias > 0 else "LESS than predicted"
            print(f"  [{kind:6}] {sig[:58]:58} n={n:4} avg {abs(bias):5.1f} {direction}")

    t = totals["turns"] or 1
    print(f"turns audited: {totals['turns']}")
    print(f"  HP prediction within +-{TOL}: {totals['hp_ok']} ({100*totals['hp_ok']/t:.0f}%)")
    print(f"  damage prediction within +-{TOL}: {totals['dmg_ok']}"
          f" (of turns that logged plan_damage)")
    report("HP LOSS", hp_buckets)
    report("DAMAGE DEALT", dmg_buckets)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="most recent N runs")
    ap.add_argument("--min-n", type=int, default=5)
    args = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(ROOT, "logs", "runs", "*", "decisions.jsonl")),
                   key=os.path.getmtime, reverse=True)[: args.limit]
    print(f"auditing {len(paths)} runs\n")
    audit(paths, args.min_n)


if __name__ == "__main__":
    main()
