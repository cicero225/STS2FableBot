"""Observed HP cost of event FIGHTS, per (event, chosen option), from the run logs.

The event policy prices a fight option as a generic hallway loss (~10 HP), but
the Lantern Key's Mysterious Knight costs 30 mean / 41 p75 (175 A0 fights, 4
outright deaths) and Dense Vegetation's 'Rest' is a Wriggler ambush that never
says 'fight'. Every option chosen during an event visit that ends in a fight
is credited with that fight's loss, so the gate prices each screen honestly.

Output: data/event_fight_stats.json -> {"options": {"EVENT_ID|Option Title":
{"encounter", "n", "mean", "p75", "deaths"}}}. Deaths are excluded from the
loss stats (not clean samples) and counted separately.

Usage: .venv\\Scripts\\python scripts/build_event_fight_stats.py
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "event_fight_stats.json")
COMBAT = {"monster", "elite", "boss"}
END_OF_EVENT = {"map", "rewards", "rest_site", "shop", "treasure", "card_reward"}


def main() -> None:
    rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    runs = 0
    for d in sorted(glob.glob(os.path.join(ROOT, "logs", "runs", "*"))):
        try:
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except OSError:
            continue
        outcome = meta.get("outcome") or {}
        if outcome.get("status") != "completed":
            continue
        runs += 1
        chosen: list[tuple[str, str]] = []  # options chosen in the current event visit
        cur: dict | None = None
        with open(os.path.join(d, "decisions.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                st = r.get("state") or {}
                t = r.get("state_type")
                pl = st.get("player") or {}
                a = r.get("action") or {}
                if t == "event" and a.get("action") == "choose_event_option":
                    ev = st.get("event") or {}
                    opt = next((o for o in ev.get("options") or []
                                if o.get("index") == a.get("index")), None)
                    if opt and not opt.get("is_proceed"):
                        chosen.append((str(ev.get("event_id") or ev.get("event_name") or "?"),
                                       str(opt.get("title") or "")))
                elif t in COMBAT and chosen:
                    b = st.get("battle") or {}
                    if b.get("enemies"):
                        if cur is None:
                            cur = {"leader": b["enemies"][0].get("name"), "hp_in": pl.get("hp"),
                                   "hp_out": pl.get("hp"), "died": False}
                        cur["hp_out"] = pl.get("hp")
                elif cur is not None and t == "game_over":
                    cur["died"] = True
                    for key in chosen:
                        rows[key].append(cur)
                    cur, chosen = None, []
                elif cur is not None and t not in COMBAT and t not in ("hand_select", "unknown"):
                    for key in chosen:
                        rows[key].append(cur)
                    cur, chosen = None, []
                elif chosen and t in END_OF_EVENT:
                    chosen = []
    options: dict[str, dict] = {}
    for (eid, title), xs in rows.items():
        losses = sorted(x["hp_in"] - x["hp_out"] for x in xs
                        if not x["died"] and x["hp_in"] is not None and x["hp_out"] is not None)
        if not losses:
            continue
        leaders: dict[str, int] = defaultdict(int)
        for x in xs:
            leaders[x["leader"]] += 1
        options[f"{eid}|{title}"] = {
            "encounter": max(leaders, key=leaders.get),
            "n": len(xs),
            "deaths": sum(1 for x in xs if x["died"]),
            "mean": round(statistics.mean(losses), 1),
            "p75": losses[min(len(losses) - 1, (len(losses) * 3) // 4)],
        }
    payload = {"source": f"{runs} completed run logs", "options": dict(sorted(options.items()))}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=1)
        f.write("\n")
    print(f"wrote {OUT}: {len(options)} event-fight options")
    for k, v in sorted(options.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {k:48s} -> {v['encounter']:22s} n={v['n']:3d} deaths={v['deaths']} "
              f"mean={v['mean']:5.1f} p75={v['p75']}")


if __name__ == "__main__":
    main()
