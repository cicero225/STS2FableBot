"""Deck-power diagnostic: mine logged decision traces for the Act-1 boss fight of each run and
aggregate the deck-power gap (how much boss HP the bot removes before dying) against deck
composition. Tests the §8.1 hypothesis that drafting over-values long-game / context-poor cards,
leaving the boss-entry deck too basic-heavy to close the kill.

Usage: .venv\\Scripts\\python.exe scripts/deck_power_diagnostic.py [config_hash] [character]
Defaults to the most-populous recent config and 'The Ironclad'.
"""

from __future__ import annotations

import json
import os
import sqlite3
import statistics as st
import sys
from collections import Counter

BASICS = {"Strike", "Defend"}
LOG_DB = "logs/index.sqlite"


def act1_boss_fight(path: str) -> dict | None:
    """Pull the Act-1 boss fight from a run's decisions.jsonl: entry deck, boss HP arc, end HP."""
    deck = None
    maxhp = 0
    hpmin = 10**9
    pfinal = None
    reached = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            state = d.get("state") or {}
            run = state.get("run") or {}
            if d.get("state_type") == "boss" and run.get("act") == 1:
                reached = True
                pl = state.get("player") or {}
                bt = state.get("battle") or {}
                if deck is None and pl.get("deck"):
                    deck = pl["deck"]
                enemies = bt.get("enemies") or []
                if enemies:
                    tot = sum((e.get("hp") or 0) for e in enemies)
                    mx = sum((e.get("max_hp") or 0) for e in enemies)
                    maxhp = max(maxhp, mx)
                    hpmin = min(hpmin, tot)
                if pl.get("hp") is not None:
                    pfinal = pl["hp"]
    if not reached or deck is None or maxhp == 0:
        return None
    names = [c.get("name") for c in deck]
    dmg = maxhp - hpmin
    return {
        "size": len(deck),
        "basics": sum(1 for n in names if n in BASICS),
        "maxhp": maxhp,
        "hpmin": hpmin,
        "pct": 100 * dmg / maxhp,
        # 'won' is set by the caller from the index final floor: the lethal blow transitions out of
        # the boss state before HP logs as 0, so hpmin==0 is unreliable. Passing floor>17 is truth.
        "won": None,
        "pfinal": pfinal,
        "names": names,
    }


def main() -> None:
    conn = sqlite3.connect(LOG_DB)
    if len(sys.argv) > 1:
        cfg = sys.argv[1]
    else:
        cfg = conn.execute(
            "SELECT config_hash FROM runs GROUP BY config_hash "
            "ORDER BY MAX(started_at) DESC LIMIT 1"
        ).fetchone()[0]
    char = sys.argv[2] if len(sys.argv) > 2 else "The Ironclad"
    rows = conn.execute(
        "SELECT run_dir, floor FROM runs WHERE config_hash=? AND character=? "
        "AND status='completed'",
        (cfg, char),
    ).fetchall()
    print(f"config {cfg}  character {char}  completed runs: {len(rows)}")

    res = []
    for run_dir, floor in rows:
        path = os.path.join(run_dir.replace("\\", "/"), "decisions.jsonl")
        if not os.path.exists(path):
            continue
        r = act1_boss_fight(path)
        if r:
            r["won"] = (floor or 0) > 17  # progressed past the Act-1 boss (floor 17) -> beat it
            res.append(r)
    print(f"reached Act-1 boss with deck logged: {len(res)}")
    if not res:
        return

    won = [r for r in res if r["won"]]
    lost = [r for r in res if not r["won"]]
    print(f"  beat Act-1 boss: {len(won)}    died to Act-1 boss: {len(lost)}")

    def summ(group: list, label: str) -> None:
        if not group:
            return
        size = st.mean(r["size"] for r in group)
        basics = st.mean(r["basics"] for r in group)
        pctb = 100 * st.mean(r["basics"] / r["size"] for r in group)
        print(f"  [{label:16}] n={len(group):3}  deck={size:4.1f}  "
              f"basics={basics:3.1f} ({pctb:2.0f}%)")

    summ(res, "ALL")
    summ(won, "WON Act-1 boss")
    summ(lost, "LOST Act-1 boss")

    if lost:
        remain = [100 - r["pct"] for r in lost]
        print(f"\n  LOST: boss HP %% remaining at death — median {st.median(remain):.0f}%, "
              f"mean {st.mean(remain):.0f}%")
        near = [r for r in lost if r["pct"] >= 80]
        print(f"  near-misses (bot removed >=80%% of boss HP): {len(near)}/{len(lost)}")

    # which non-basic cards show up most in boss-entry decks?
    nonbasic = Counter()
    for r in res:
        for n in r["names"]:
            if n not in BASICS:
                nonbasic[n] += 1
    print("\n  most common non-basic boss-entry cards:")
    for name, ct in nonbasic.most_common(15):
        print(f"    {ct:3}x  {name}")

    # data-driven differentiator: avg copies/deck in WON vs LOST decks (no hand-taxonomy needed).
    # Positive delta => the card is over-represented in decks that beat the Act-1 boss.
    if won and lost:
        def avg_copies(group: list) -> Counter:
            c = Counter()
            for r in group:
                c.update(Counter(n for n in r["names"] if n not in BASICS))
            return Counter({k: v / len(group) for k, v in c.items()})

        wa, la = avg_copies(won), avg_copies(lost)
        support = {n for n, ct in nonbasic.items() if ct >= 5}  # ignore rare cards (noise)
        delta = sorted(
            ((wa.get(n, 0) - la.get(n, 0), n) for n in support), reverse=True
        )
        print("\n  cards MORE common in WINNING boss decks (avg copies/deck: won vs lost):")
        for dv, n in delta[:10]:
            print(f"    +{dv:+.2f}   {n:18} (won {wa.get(n,0):.2f} / lost {la.get(n,0):.2f})")
        print("  cards MORE common in LOSING boss decks:")
        for dv, n in delta[-10:][::-1]:
            print(f"    {dv:+.2f}   {n:18} (won {wa.get(n,0):.2f} / lost {la.get(n,0):.2f})")


if __name__ == "__main__":
    main()
