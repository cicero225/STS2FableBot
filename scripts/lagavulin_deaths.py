#!/usr/bin/env python
"""Death-deck + power-timing + Soul-Siphon timeline for Lagavulin Matriarch deaths.

Tests the owner hypothesis (PLAN §8.4): the Matriarch punishes decks that (a) can't stack
damage early, (b) lack big attacks (vs 12 Block/turn Plating), or (c) hold off on powers
(the 3 Asleep turns are free setup). Soul Siphon then permanently drains -2 Str/-2 Dex per
cycle, so a slow deck decays into a loss. For each recent run that died to the Matriarch we
print: boss-entry deck + deck_output, the estimate vs the real boss, and a per-round trace
(player Str/Dex = Soul-Siphon decay, block, HP; Lagavulin HP/Asleep/Plating), plus which
powers were drawn-but-not-played.

Usage: .venv\\Scripts\\python.exe scripts/lagavulin_deaths.py [--runs N] [--all]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter

from sts2bot.client.models import DeckCard
from sts2bot.policy.capability import bestiary_enemy, deck_output, estimate_fight
from sts2bot.policy.standard import StandardRouter

LAG = "Lagavulin Matriarch"
_CARD_FIELDS = set(DeckCard.model_fields)


def to_cards(deck: list[dict]) -> list[DeckCard]:
    """Raw log dicts -> DeckCard objects (what deck_output expects)."""
    out = []
    for i, c in enumerate(deck):
        data = {k: v for k, v in c.items() if k in _CARD_FIELDS}
        data.setdefault("index", i)
        data.setdefault("name", c.get("name", "?"))
        out.append(DeckCard(**data))
    return out


def recent_run_dirs(n: int) -> list[str]:
    metas = sorted(glob.glob("logs/runs/*/meta.json"), key=os.path.getmtime, reverse=True)
    return [os.path.dirname(m) for m in metas[:n]]


def load(d: str):
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(d, "decisions.jsonl"), encoding="utf-8") as f:
        recs = [json.loads(line) for line in f]
    return meta, recs


def enemy_named(rec: dict, name: str) -> dict | None:
    battle = (rec.get("state") or {}).get("battle") or {}
    for e in battle.get("enemies") or []:
        if e.get("name") == name:
            return e
    return None


def str_dex(pl: dict) -> tuple[int, int]:
    st = {s.get("name"): s.get("amount", 0) for s in (pl.get("status") or [])}
    return st.get("Strength", 0), st.get("Dexterity", 0)


def analyze(d: str, router: StandardRouter) -> bool:
    meta, recs = load(d)
    o = meta.get("outcome") or {}
    lag_idx = [i for i, r in enumerate(recs) if enemy_named(r, LAG)]
    if not lag_idx:
        return False

    # boss-entry deck: last populated deck before the first Lagavulin combat record
    deck = None
    for r in recs[: lag_idx[0]][::-1]:
        dk = ((r.get("state") or {}).get("player") or {}).get("deck")
        if dk:
            deck = dk
            break
    if not deck:
        deck = ((recs[lag_idx[0]].get("state") or {}).get("player") or {}).get("deck") or []

    do = deck_output(to_cards(deck), descriptions=router.card_effects)
    lag = bestiary_enemy(router.bestiary[LAG], dps=22, str_ramp=1)
    est = estimate_fight(80, do, [lag])

    attacks = [c for c in deck if c.get("type") == "Attack"]
    powers = {c.get("name") for c in deck if c.get("type") == "Power"}
    basics = sum(1 for c in deck if (c.get("name") or "").rstrip("+") in ("Strike", "Defend"))
    nonbasic = dict(Counter(
        c.get("name") for c in attacks if (c.get("name") or "").rstrip("+") != "Strike"
    ))

    seed, killer = o.get("seed"), o.get("killed_by_encounter")
    print(f"\n{'=' * 78}\n{os.path.basename(d)}  seed={seed}  killed_by={killer}")
    print(
        f"  deck: {len(deck)} cards | {basics} basic | {len(attacks)} atk | "
        f"{len(powers)} pwr | non-basic atk: {nonbasic}"
    )
    print(
        f"  deck_output: burst={do.burst_dmg:.0f} sustained={do.sustained_dmg:.1f} "
        f"biggest_hit={do.biggest_hit:.0f} block/turn={do.block_per_turn:.1f}"
    )
    print(
        f"  estimate vs Lagavulin@80: win={est.win} exp_end_hp={est.exp_end_hp} "
        f"turns={est.turns} boss_hp_left={est.enemy_hp_left}"
    )
    if powers:
        print(f"  powers in deck: {sorted(powers)}")

    # per-round trace (last snapshot per round) + power draw/play tracking
    drawn: set[str] = set()
    played: set[str] = set()
    by_round: dict[int, tuple] = {}
    prev_boss_hp = None
    biggest_drop = 0
    for i in lag_idx:
        r = recs[i]
        pl = (r.get("state") or {}).get("player") or {}
        b = (r.get("state") or {}).get("battle") or {}
        e = enemy_named(r, LAG)
        estat = {s.get("name"): s.get("amount", 0) for s in (e.get("status") or [])}
        for c in pl.get("hand") or []:
            if c.get("name") in powers:
                drawn.add(c.get("name"))
        for pile in ("discard_pile", "exhaust_pile"):
            for c in pl.get(pile) or []:
                if c.get("name") in powers:
                    played.add(c.get("name"))
        s_, x_ = str_dex(pl)
        rnd = b.get("round")
        by_round[rnd] = (s_, x_, pl.get("hp"), pl.get("block"), e.get("hp"),
                         estat.get("Asleep"), estat.get("Plating"))
        if prev_boss_hp is not None and e.get("hp") is not None:
            drop = prev_boss_hp - e.get("hp")
            if drop > biggest_drop:
                biggest_drop = drop
        prev_boss_hp = e.get("hp")

    print("  round |  Str  Dex |  myHP  blk | bossHP Asleep Plating")
    for rnd in sorted(k for k in by_round if k is not None):
        s_, x_, hp, blk, bhp, asleep, plating = by_round[rnd]
        print(f"   {rnd!s:>4} | {s_:>4} {x_:>4} | {hp!s:>5} {blk!s:>4} | "
              f"{bhp!s:>5}  {asleep!s:>5}  {plating!s:>5}")
    print(f"  biggest boss-HP drop in one step: {biggest_drop}")
    held = drawn - played
    print(f"  powers drawn-but-not-played (held): {sorted(held) or 'none'} "
          f"| never drawn: {sorted(powers - drawn) or 'none'}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--all", action="store_true", help="scan all runs, not just the recent N")
    args = ap.parse_args()
    router = StandardRouter()
    dirs = (
        [os.path.dirname(m) for m in sorted(glob.glob("logs/runs/*/meta.json"))]
        if args.all
        else recent_run_dirs(args.runs)
    )
    found = sum(analyze(d, router) for d in dirs)
    print(f"\n{'='*78}\nLagavulin deaths analysed: {found} (of {len(dirs)} runs scanned)")


if __name__ == "__main__":
    main()
