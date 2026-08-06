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

    # a turn = the LAST scored decision of round R, matched against the first state of
    # R+1 — WITHIN one fight. Rounds reset to 1 each combat, so group by (fight, round):
    # a round number lower than the previous row's marks a NEW fight (2026-07-16 bug:
    # grouping by round alone paired predictions from one fight with outcomes from
    # another, contaminating every metric).
    by_round: dict[tuple[int, int], list] = defaultdict(list)
    fight = 0
    prev_rnd = None
    for d in rows:
        b = d["state"]["battle"]
        rnd = b.get("round")
        if rnd is None:
            continue
        if prev_rnd is not None and rnd < prev_rnd:
            fight += 1
        prev_rnd = rnd
        by_round[(fight, rnd)].append(d)
    for (fid, rnd) in sorted(by_round):
        cur = by_round[(fid, rnd)]
        nxt = by_round.get((fid, rnd + 1))
        if not nxt:
            continue
        scored = [d for d in cur if (d.get("scores") or {}).get("hp_loss") is not None]
        if not scored:
            continue
        # Two different decisions are the right yardstick for the two channels:
        #  * HP: the LAST plan of the turn — it knows the final block/played state.
        #  * DAMAGE: the FIRST plan — its plan_damage covers the WHOLE intended turn,
        #    while later re-plans only cover the cards still unplayed (pairing those
        #    against the turn's total enemy HP loss made everything read "MORE than
        #    predicted" — a measurement artifact, not a model error).
        yield scored[-1], scored[0], cur[0], nxt[0]


def audit(paths, min_n: int):
    hp_buckets = defaultdict(list)   # signature -> [(pred, actual)]
    dmg_buckets = defaultdict(list)
    totals = {"turns": 0, "hp_ok": 0, "dmg_ok": 0}

    for path in paths:
        try:
            pairs = list(_player_turn_states(path))
        except (OSError, KeyError):
            continue
        for last, first_plan, first, nxt in pairs:
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

            # --- DAMAGE check: the FIRST plan of the turn covers the whole turn
            pred_dmg = (first_plan.get("scores") or {}).get("plan_damage")
            if pred_dmg is None:
                continue
            # A Heal intent makes the HP-delta channel lie (Knowledge Demon healed ~30/
            # cycle: a 29-damage turn read as -16 "dealt") — those turns are accounting
            # noise, not model error; skip them rather than pollute the buckets.
            if any((i.get("type") or "").lower() == "heal"
                   for e in e0.values() for i in (e.get("intents") or [])):
                continue
            # Player THORNS makes the damage channel lie the other way: enemies
            # attacking into our thorns lose HP during THEIR turn -- counted in
            # the e0->e1 delta, never in plan_damage (the +11.6 THORNS_POWER
            # bucket was this artifact, not a model error). Accounting noise.
            if any("THORNS" in (s.get("id") or "").upper()
                   for s in (pl0.get("status") or [])):
                continue
            # A killed enemy DROPS OUT of the next state's list, so `k not in e1` means we
            # dealt its full remaining HP (skipping those under-counted our own damage —
            # it read as the Nibbit "-18.6 less than predicted" artifact).
            actual_dmg = sum(max(0, e0[k]["hp"] - e1[k]["hp"]) if k in e1 else e0[k]["hp"]
                             for k in e0)
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


def drill(paths, enemy_name: str | None, status_id: str | None = None,
          max_rows: int = 12) -> None:
    """Show the divergent turns for one enemy: prediction, actual, intents, block,
    player statuses — the raw material for diagnosing an unmodeled mechanic."""
    shown = 0
    for path in paths:
        if shown >= max_rows:
            break
        try:
            pairs = list(_player_turn_states(path))
        except (OSError, KeyError):
            continue
        for last, _first_plan, first, nxt in pairs:
            if shown >= max_rows:
                break
            e0 = first["state"]["battle"].get("enemies") or []
            pl0_ = first["state"]["player"]
            if status_id and not any(
                    status_id.upper() in (s.get("id") or "").upper()
                    for s in (pl0_.get("status") or [])):
                continue
            if enemy_name and not any(
                    enemy_name.lower() in (e.get("name") or "").lower() for e in e0):
                continue
            sc = last.get("scores") or {}
            pl0, pl1 = first["state"]["player"], nxt["state"]["player"]
            pred = sc.get("hp_loss")
            if pred is None or pl0.get("hp") is None or pl1.get("hp") is None:
                continue
            actual = pl0["hp"] - pl1["hp"]
            if abs(actual - pred) <= TOL:
                continue
            shown += 1
            run = os.path.basename(os.path.dirname(path))
            rnd = first["state"]["battle"].get("round")
            es = "; ".join(
                f"{e.get('name')} {e.get('hp')}hp "
                f"i={[(i.get('type'), i.get('label')) for i in e.get('intents') or []]} "
                f"s={[(s.get('id'), s.get('amount')) for s in e.get('status') or []]}"
                for e in e0)
            pst = [(s.get("id"), s.get("amount")) for s in (pl0.get("status") or [])]
            print(f"{run} r{rnd}: pred={pred} actual={actual} "
                  f"(hp {pl0['hp']}->{pl1['hp']}, start blk={pl0.get('block')})")
            print(f"    {es}")
            print(f"    my status: {pst}  last plan: {str(last.get('rationale'))[:90]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="most recent N runs")
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--enemy", type=str, default=None,
                    help="drill into divergent turns vs this enemy instead of the summary")
    ap.add_argument("--status", type=str, default=None,
                    help="drill into divergent turns where the PLAYER has this status id")
    args = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(ROOT, "logs", "runs", "*", "decisions.jsonl")),
                   key=os.path.getmtime, reverse=True)[: args.limit]
    if args.enemy or args.status:
        drill(paths, args.enemy, status_id=args.status)
        return
    print(f"auditing {len(paths)} runs\n")
    audit(paths, args.min_n)


if __name__ == "__main__":
    main()
