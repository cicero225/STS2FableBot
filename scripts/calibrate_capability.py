"""Calibrate estimate_fight against reality — the forward-model baseline harness.

For every ELITE and BOSS fight in the modern-era logs (the two places the router
actually uses the §5-C capability estimate), rebuild the prediction from the fight's
ENTRY state (deck, entry HP, enemies via bestiary — same construction as _map) and
compare with what actually happened. Reports bias, classification accuracy, and the
worst false-negatives (predicted-lose fights that were WON — the engine-blindness
signature: the owner's f6 Stoke deck read as 9.6 sustained dmg and went 3-for-3).

Run: .venv/Scripts/python scripts/calibrate_capability.py [--since 20260714]
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2bot.kb.config import load_policy_config
from sts2bot.policy.capability import (
    FightEnemy,
    bestiary_enemy,
    deck_output,
    estimate_fight,
)
from sts2bot.policy.rollout import rollout_fight
from sts2bot.policy.standard import _GENERIC_ELITE, StandardRouter

SINCE = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "20260714"

router = StandardRouter(load_policy_config())  # for bestiary + card_effects only


def wrap_deck(deck_raw):
    return [SimpleNamespace(**{k: c.get(k) for k in
                               ("id", "name", "type", "cost", "is_upgraded", "description")})
            for c in deck_raw]


def fights_in(path):
    """Yield (kind, act, entry_state_raw, exit_hp_or_None[death]) per elite/boss fight.

    One fight per (kind, floor): mid-fight modals (card_select / hand_select /
    potion screens) leave the combat state_type briefly — treating them as fight
    end fragmented each boss fight into a dozen rows (first-draft bug, n=2082
    "boss fights"). A fight ends only at game_over (death) or a genuine post-fight
    screen with player HP."""
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            raw = r.get("state") or {}
            if raw.get("state_type"):
                recs.append((r.get("state_type"), raw))
    _MODALS = ("card_select", "hand_select", "unknown")
    groups = {}  # (kind, floor) -> [indices]
    for i, (t, raw) in enumerate(recs):
        if t in ("elite", "boss"):
            fl = (raw.get("run") or {}).get("floor")
            groups.setdefault((t, fl), []).append(i)
    for (kind, _fl), idxs in sorted(groups.items(), key=lambda kv: kv[1][0]):
        # entry = first record with enemies AND a deck (transitional states lack both)
        entry = None
        for i in idxs:
            raw = recs[i][1]
            if ((raw.get("battle") or {}).get("enemies")
                    and (raw.get("player") or {}).get("deck")):
                entry = raw
                break
        if entry is None:
            continue
        # outcome: scan from the LAST in-fight record past modals to a terminal state
        died = None
        exit_hp = None
        for j in range(idxs[-1] + 1, len(recs)):
            t2, raw2 = recs[j]
            if t2 == "game_over":
                died = True
                break
            if t2 in _MODALS:
                continue
            hp2 = (raw2.get("player") or {}).get("hp")
            if hp2 is not None:
                died = False
                exit_hp = hp2
                break
        if died is None:
            continue  # log ended mid-fight (crash/handoff): unknown outcome, skip
        act = min(int((entry.get("run") or {}).get("act") or 1), 3)
        yield kind, act, entry, (None if died else exit_hp)


def predict(kind, act, entry):
    pl = entry.get("player") or {}
    deck_raw = pl.get("deck")
    hp = pl.get("hp")
    enemies_raw = ((entry.get("battle") or {}).get("enemies")) or []
    if not deck_raw or hp is None or not enemies_raw:
        return None
    ehp, edps, eramp = _GENERIC_ELITE.get(act, _GENERIC_ELITE[1])
    deck = deck_output(wrap_deck(deck_raw), descriptions=router.card_effects)
    members = []
    for e in enemies_raw:
        if (e.get("hp") or 0) <= 0:
            continue
        name = e.get("name") or ""
        entry_b = router.bestiary.get(name)
        dps = edps + (4 if kind == "boss" else 0)
        if entry_b:
            m = bestiary_enemy(entry_b, dps=dps, name=name)
            # use the OBSERVED hp for this instance (bestiary carries max seen)
            m = FightEnemy(**{**m.__dict__, "hp": e.get("hp") or m.hp})
        else:
            m = FightEnemy(hp=e.get("hp") or ehp, dps=dps, str_ramp=eramp)
        members.append(m)
    if not members:
        return None
    out = estimate_fight(int(hp), deck, members)
    roll = rollout_fight(wrap_deck(deck_raw), members, int(hp),
                         int(pl.get("max_hp") or hp),
                         card_effects=router.card_effects, n=20)
    return out, roll


def main():
    rows = []
    for d in sorted(glob.glob("logs/runs/*")):
        if os.path.basename(d)[:8] < SINCE:
            continue
        p = os.path.join(d, "decisions.jsonl")
        if not os.path.isfile(p):
            continue
        for kind, act, entry, exit_hp in fights_in(p):
            res = predict(kind, act, entry)
            if res is None:
                continue
            out, roll = res
            hp = (entry.get("player") or {}).get("hp")
            actual_win = exit_hp is not None
            actual_loss = (hp - exit_hp) if actual_win else hp
            pred_loss = (hp - out.exp_end_hp) if out.win else hp
            roll_loss = hp - roll.exp_end_hp
            rows.append(dict(kind=kind, act=act, hp=hp,
                             pred_win=bool(out.win), actual_win=actual_win,
                             pred_loss=float(pred_loss), actual_loss=float(actual_loss),
                             roll_win=roll.win, roll_loss=float(roll_loss),
                             roll_win_rate=roll.win_rate,
                             deck_n=len((entry.get("player") or {}).get("deck") or []),
                             run=os.path.basename(d)))
    print(f"calibration over {len(rows)} elite/boss fights since {SINCE}\n")
    print(f"{'seg':<12}{'n':>4} {'predW%':>7} {'actW%':>7} {'predLoss':>9} "
          f"{'actLoss':>8} {'bias':>6}  FN%(predL,actW)  FP%(predW,died)")
    for kind in ("elite", "boss"):
        for act in (1, 2, 3):
            seg = [r for r in rows if r["kind"] == kind and r["act"] == act]
            if not seg:
                continue
            n = len(seg)
            pw = sum(r["pred_win"] for r in seg) / n
            aw = sum(r["actual_win"] for r in seg) / n
            pl_ = sum(r["pred_loss"] for r in seg) / n
            al = sum(r["actual_loss"] for r in seg) / n
            fn = sum((not r["pred_win"]) and r["actual_win"] for r in seg) / n
            fp = sum(r["pred_win"] and (not r["actual_win"]) for r in seg) / n
            rw = sum(r["roll_win"] for r in seg) / n
            rl = sum(r["roll_loss"] for r in seg) / n
            rfn = sum((not r["roll_win"]) and r["actual_win"] for r in seg) / n
            rfp = sum(r["roll_win"] and (not r["actual_win"]) for r in seg) / n
            print(f"{kind}-act{act:<6}{n:>4} {pw:>6.0%} {aw:>6.0%} {pl_:>9.1f} "
                  f"{al:>8.1f} {pl_-al:>+6.1f}  {fn:>8.0%} {fp:>14.0%}")
            print(f"  ROLLOUT{'':<5}{n:>4} {rw:>6.0%} {aw:>6.0%} {rl:>9.1f} "
                  f"{al:>8.1f} {rl-al:>+6.1f}  {rfn:>8.0%} {rfp:>14.0%}")
    # the engine-blindness exhibit: predicted-lose fights that were WON
    fns = [r for r in rows if not r["pred_win"] and r["actual_win"]]
    fns.sort(key=lambda r: r["pred_loss"] - r["actual_loss"], reverse=True)
    print(f"\nworst false-negatives ({len(fns)} total):")
    for r in fns[:8]:
        print(f"  {r['kind']}-act{r['act']} {r['run'][:15]} entry {r['hp']} HP, "
              f"deck {r['deck_n']} cards: predicted loss {r['pred_loss']:.0f} "
              f"(unwinnable), actual loss {r['actual_loss']:.0f}")


if __name__ == "__main__":
    main()
