"""Reconstruct a recorded run (human or bot) from its state trace into a readable timeline.

The recorder logs *states*, not choices, so we recover decisions by diffing successive
states: deck/relic/gold/HP deltas plus the `was_chosen` flag on event options. One logical
run can span several dirs (a recording interrupted and resumed continues the same run), so
this accepts multiple dirs and concatenates their records in order.

Usage:
    python scripts/analyze_manual_run.py logs/manual/runs/DIR1 [logs/manual/runs/DIR2 ...]
    python scripts/analyze_manual_run.py --latest         # newest dir only
    python scripts/analyze_manual_run.py --manual         # all logs/manual dirs, in order
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter


def load(dirs: list[str]) -> list[dict]:
    recs: list[dict] = []
    for d in dirs:
        path = os.path.join(d, "decisions.jsonl")
        with open(path, encoding="utf-8") as f:
            recs += [json.loads(line) for line in f]
    return recs


def card_key(c: dict) -> tuple[str, bool]:
    return (c.get("id") or c.get("name"), bool(c.get("is_upgraded")))


def card_label(k: tuple[str, bool]) -> str:
    return f"{k[0]}{'+' if k[1] else ''}"


def deck_multiset(player: dict) -> Counter:
    return Counter(card_key(c) for c in (player.get("deck") or []))


def relic_set(player: dict) -> list[str]:
    return [r.get("id") or r.get("name") for r in (player.get("relics") or [])]


def node_type(state_types: set[str]) -> str:
    for st in ("boss", "elite", "monster", "event", "shop", "rest_site"):
        if st in state_types:
            return {"monster": "Monster", "rest_site": "Rest"}.get(st, st.capitalize())
    if "card_reward" in state_types or "rewards" in state_types:
        return "Combat"
    return "?"


def estatus(e: dict, sid: str) -> int:
    for s in e.get("status", []):
        if s["id"] == sid:
            return s["amount"]
    return 0


def trace_fight(recs: list[dict], floor: int) -> None:
    """Print one combat turn-by-turn: player + enemy HP/block/strength as it evolved.
    Strength on a minion = it is ramping; watch whether the player races the leader or
    diverts to the minions."""
    print(f"# Fight trace at floor {floor}\n")
    prev = None
    for r in recs:
        s = r.get("state") or {}
        if (s.get("run") or {}).get("floor") != floor:
            continue
        b = s.get("battle") or {}
        p = s.get("player") or {}
        es = b.get("enemies") or []
        key = (b.get("round"), p.get("hp"), p.get("block"),
               tuple((e["hp"], e.get("block"), estatus(e, "STRENGTH_POWER")) for e in es))
        if key == prev:
            continue
        prev = key

        def esnap(e: dict) -> str:
            out = f"{e['name'].split()[-1]}:{e['hp']}/{e['max_hp']}"
            if estatus(e, "STRENGTH_POWER"):
                out += f" str{estatus(e, 'STRENGTH_POWER')}"
            if e.get("block"):
                out += f" blk{e['block']}"
            if estatus(e, "VULNERABLE_POWER"):
                out += " VULN"
            return out

        alive = " ".join(esnap(e) for e in es if e["hp"] > 0) or "CLEAR"
        turn = b.get("turn") or "-"
        print(f"R{b.get('round')} {turn:>6} | me {p.get('hp')}hp blk{p.get('block')} "
              f"e{p.get('energy')} | {alive}")
        hand = [c["name"] for c in (p.get("hand") or [])]
        if hand and turn == "player":
            print("        hand:", ", ".join(hand))


def main() -> None:
    args = sys.argv[1:]
    if "--fight" in args:
        i = args.index("--fight")
        floor = int(args[i + 1])
        del args[i : i + 2]
    else:
        floor = None
    all_dirs = sorted(glob.glob("logs/manual/runs/*/"), key=os.path.getmtime)
    drop = 0
    if "--drop-latest" in args:
        i = args.index("--drop-latest")
        drop = int(args[i + 1])
        del args[i : i + 2]
    if drop:
        all_dirs = all_dirs[:-drop]
    if "--latest" in args:
        dirs = [all_dirs[-1]]
    elif "--manual" in args or not args:
        dirs = all_dirs
    else:
        dirs = args
    recs = load(dirs)
    if floor is not None:
        trace_fight(recs, floor)
        return
    print(f"# Run reconstruction from {len(dirs)} dir(s), {len(recs)} states\n")

    # --- per-floor route + HP, deck/relic/gold timeline ---
    floor_states: dict[int, set[str]] = {}
    floor_hp: dict[int, tuple[int, int]] = {}   # floor -> (min_hp, last_hp)
    floor_act: dict[int, int] = {}
    deck_events: list[str] = []
    relic_events: list[str] = []
    prev_deck: Counter | None = None
    prev_relics: list[str] | None = None
    prev_gold: int | None = None
    gold_spent_at: list[str] = []

    for r in recs:
        s = r.get("state") or {}
        run = s.get("run") or {}
        floor = run.get("floor")
        p = s.get("player") or {}
        if floor is None:
            continue
        floor_act[floor] = run.get("act", floor_act.get(floor, 0))
        floor_states.setdefault(floor, set()).add(r["state_type"])
        hp = p.get("hp")
        if hp is not None:
            mn, _ = floor_hp.get(floor, (hp, hp))
            floor_hp[floor] = (min(mn, hp), hp)
        # deck delta
        if p.get("deck") is not None:
            dm = deck_multiset(p)
            if prev_deck is not None and dm != prev_deck:
                added = dm - prev_deck
                removed = prev_deck - dm
                ctx = node_type(floor_states.get(floor, set()))
                # detect upgrades (same id, False->True)
                up = []
                for k in list(added):
                    base = (k[0], False)
                    if k[1] and base in removed:
                        up.append(k[0])
                        removed[base] -= 1
                        added[k] -= 1
                for name in up:
                    deck_events.append(f"  f{floor:<2} [{ctx}] upgrade {name}")
                for k, n in (+added).items():
                    sfx = f" x{n}" if n > 1 else ""
                    deck_events.append(f"  f{floor:<2} [{ctx}] + {card_label(k)}{sfx}")
                for k, n in (+removed).items():
                    sfx = f" x{n}" if n > 1 else ""
                    deck_events.append(f"  f{floor:<2} [{ctx}] - {card_label(k)}{sfx}")
            prev_deck = dm
        # relic delta
        if p.get("relics") is not None:
            rs = relic_set(p)
            if prev_relics is not None and rs != prev_relics:
                for relic in rs:
                    if relic not in prev_relics:
                        ctx = node_type(floor_states.get(floor, set()))
                        relic_events.append(f"  f{floor:<2} [{ctx}] + {relic}")
            prev_relics = rs
        # gold spent (drops) on shop floors
        g = p.get("gold")
        on_shop = "shop" in floor_states.get(floor, set())
        if g is not None and prev_gold is not None and g < prev_gold and on_shop:
            gold_spent_at.append(f"  f{floor:<2} spent {prev_gold - g}g (-> {g}g)")
        if g is not None:
            prev_gold = g

    # --- route ---
    print("## Route (floor: node — HP end / min)")
    last_act = None
    for floor in sorted(floor_states):
        act = floor_act.get(floor, 0)
        if act != last_act:
            print(f"  --- Act {act} ---")
            last_act = act
        nt = node_type(floor_states[floor])
        mn, last = floor_hp.get(floor, ("?", "?"))
        print(f"  f{floor:<2} {nt:<8} hp {last}" + (f" (low {mn})" if mn != last else ""))

    # --- events ---
    print("\n## Event choices")
    seen_events = set()
    for r in recs:
        if r["state_type"] != "event":
            continue
        ev = (r.get("state") or {}).get("event") or {}
        chosen = [o for o in ev.get("options", []) if o.get("was_chosen")]
        key = (ev.get("event_id"), tuple(o["title"] for o in chosen))
        if chosen and key not in seen_events:
            seen_events.add(key)
            floor = (r.get("state") or {}).get("run", {}).get("floor")
            anc = " [ANCIENT]" if ev.get("is_ancient") else ""
            opts = "; ".join(o["title"] for o in ev.get("options", []))
            chose = chosen[0]["title"]
            print(f"  f{floor} {ev.get('event_name')}{anc}: CHOSE {chose!r}  (of: {opts})")

    # --- deck + relics ---
    print("\n## Deck changes")
    for line in deck_events:
        print(line)
    print("\n## Relics gained")
    for line in relic_events:
        print(line)
    print("\n## Shop spending")
    for line in gold_spent_at:
        print(line)

    # --- final state ---
    final = next((r["state"]["player"] for r in reversed(recs)
                  if (r.get("state") or {}).get("player", {}).get("deck")), None)
    if final:
        dm = deck_multiset(final)
        print(f"\n## Final deck ({sum(dm.values())} cards)")
        for k, n in sorted(dm.items(), key=lambda kv: (-kv[1], kv[0][0])):
            print(f"  {n}x {card_label(k)}")
        print(f"\n## Final relics ({len(relic_set(final))})")
        print("  " + ", ".join(relic_set(final)))
        print(f"\n## End: hp {final.get('hp')}/{final.get('max_hp')}  gold {final.get('gold')}")


if __name__ == "__main__":
    main()
