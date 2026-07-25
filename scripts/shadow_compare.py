"""Shadow-compare: replay an owner-recorded run through the live policy and diff
every decision screen — bot-would-have vs owner-did (owner proposal, 2026-07-24).

Works offline (C3-safe): policies are pure (state, kb, config) -> decision, and the
recorder logged every state the owner saw. All states are fed to ONE router instance
in order so per-run caches (act-boss, region) populate exactly as live; only the
interesting screens are reported. Owner actions are INFERRED from state deltas
(the recorder often misses the `was_chosen` frame): deck additions for card picks,
next-room type for map routes, hp/upgrade deltas for rest sites. Ambiguities are
marked '?' — the report is discussion fodder, not ground truth.

Run: .venv/Scripts/python scripts/shadow_compare.py logs/manual/runs/<run_dir>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2bot.client.models import parse_state
from sts2bot.kb.config import load_policy_config
from sts2bot.orchestrator.loop import LoopContext
from sts2bot.policy.base import Wait
from sts2bot.policy.standard import StandardRouter

SCREENS = ("card_reward", "map", "event", "rest_site", "shop")


def load_records(run_dir: Path) -> list[dict]:
    recs = []
    with open(run_dir / "decisions.jsonl", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            raw = rec.get("state") or rec  # recorder logs raw state under "state"
            if raw.get("state_type"):
                recs.append(raw)
    return recs


def deck_names(raw: dict) -> Counter:
    deck = (raw.get("player") or {}).get("deck") or []
    return Counter((c.get("name") or "?") for c in deck)


def floor_of(raw: dict) -> int | None:
    return (raw.get("run") or {}).get("floor")


def screen_key(raw: dict):
    t = raw.get("state_type")
    fl = floor_of(raw)
    if t == "card_reward":
        offers = tuple(sorted((c.get("name") or "?")
                              for c in (raw.get("card_reward") or {}).get("cards") or []))
        return (t, fl, offers)
    if t == "map":
        opts = tuple(sorted(f"{o.get('type')}@{o.get('col')},{o.get('row')}"
                            for o in (raw.get("map") or {}).get("next_options") or []))
        return (t, fl, opts)
    if t == "event":
        opts = tuple((o.get("title") or "") for o in (raw.get("event") or {}).get("options") or [])
        return (t, fl, opts)
    return (t, fl)


# ---------------------------------------------------------------- owner inference

def infer_card_pick(recs: list[dict], i: int) -> str:
    """Deck delta while still on this floor (or +1): the added offer card, else skip."""
    raw = recs[i]
    fl = floor_of(raw) or 0
    offers = Counter((c.get("name") or "?")
                     for c in (raw.get("card_reward") or {}).get("cards") or [])
    base = deck_names(raw)
    for later in recs[i + 1:]:
        lfl = floor_of(later)
        if lfl is not None and lfl > fl + 1:
            break
        if not (later.get("player") or {}).get("deck"):
            continue
        added = deck_names(later) - base
        for name in added:
            if name in offers:
                return f"took {name}"
        if added and later.get("state_type") == "card_reward" \
                and screen_key(later) != screen_key(raw):
            break
    return "SKIPPED"


def infer_map_pick(recs: list[dict], i: int) -> str:
    """The room type actually entered on the next floor."""
    fl = floor_of(recs[i]) or 0
    for later in recs[i + 1:]:
        lfl = floor_of(later)
        if lfl is None or lfl <= fl:
            continue
        t = later.get("state_type")
        if t in ("monster", "elite", "boss", "event", "rest_site", "shop", "treasure"):
            room = {"monster": "Monster", "elite": "Elite", "boss": "Boss",
                    "event": "Unknown/Event", "rest_site": "RestSite",
                    "shop": "Shop", "treasure": "Treasure"}[t]
            return f"went {room}"
        if t == "map" and lfl > fl:
            break
    return "?"


def infer_rest_pick(recs: list[dict], i: int) -> str:
    raw = recs[i]
    fl = floor_of(raw) or 0
    hp0 = (raw.get("player") or {}).get("hp")
    ups0 = sum(1 for c in (raw.get("player") or {}).get("deck") or []
               if c.get("is_upgraded"))
    for later in recs[i + 1:]:
        lfl = floor_of(later)
        if lfl is not None and lfl > fl:
            break
        pl = later.get("player") or {}
        if pl.get("hp") is not None and hp0 is not None and pl["hp"] > hp0 + 5:
            return f"rested ({hp0} -> {pl['hp']})"
        ups = sum(1 for c in pl.get("deck") or [] if c.get("is_upgraded"))
        if pl.get("deck") and ups > ups0:
            new = [c.get("name") for c in pl["deck"]
                   if c.get("is_upgraded")][-1] if ups else "?"
            return f"smithed (+{ups - ups0} upgrade, latest {new})"
    return "?"


def infer_event_pick(raw: dict) -> str:
    for o in (raw.get("event") or {}).get("options") or []:
        if o.get("was_chosen"):
            return f"chose '{o.get('title')}'"
    return "?"


def owner_action(recs: list[dict], i: int) -> str:
    t = recs[i].get("state_type")
    if t == "card_reward":
        return infer_card_pick(recs, i)
    if t == "map":
        return infer_map_pick(recs, i)
    if t == "rest_site":
        return infer_rest_pick(recs, i)
    if t == "event":
        return infer_event_pick(recs[i])
    return "?"


# ---------------------------------------------------------------- main

def main() -> None:
    run_dir = Path(sys.argv[1])
    recs = load_records(run_dir)
    config = load_policy_config()
    router = StandardRouter(config)
    ctx = LoopContext()

    seen: set = set()
    rows = []
    for i, raw in enumerate(recs):
        try:
            state = parse_state(raw)
        except Exception:
            continue
        t = raw.get("state_type")
        report_this = t in SCREENS
        key = screen_key(raw) if report_this else None
        if report_this and key in seen:
            report_this = False
        try:
            decision = router.decide(state, ctx)  # feed EVERYTHING: caches must populate
        except Exception as e:
            if report_this:
                rows.append((floor_of(raw), t, f"<router error: {e}>", "", None))
                seen.add(key)
            continue
        if not report_this:
            continue
        seen.add(key)
        if isinstance(decision, Wait):
            bot = f"WAIT: {decision.reason}"
        else:
            bot = decision.rationale or json.dumps(decision.action.payload())
        rows.append((floor_of(raw), t, owner_action(recs, i), bot,
                     decision.scores if not isinstance(decision, Wait) else None))

    print(f"shadow-compare: {run_dir.name} — {len(rows)} decision screens\n")
    for fl, t, owner, bot, scores in rows:
        owner_l = owner or "?"
        # a rough match heuristic purely for eyeballing; the discussion decides
        key_o = owner_l.replace("took ", "").replace("went ", "").lower()
        bot_l = (bot or "").lower()
        agree = key_o != "?" and key_o.split(" (")[0] in bot_l
        if key_o.startswith("skipped") and bot_l.startswith("skip"):
            agree = True
        if key_o.startswith("smithed") and "smith" in bot_l:
            agree = True
        if key_o.startswith("rested") and bot_l.startswith("rest"):
            agree = True
        mark = "same " if agree else "DIFF "
        print(f"[{mark}] f{fl:>2} {t:<12} owner: {owner_l}")
        print(f"         bot:   {bot}")
        if scores and not agree:
            top = sorted(scores.items(), key=lambda kv: -kv[1])[:4]
            print(f"         scores: {', '.join(f'{k}={v}' for k, v in top)}")
        print()


if __name__ == "__main__":
    main()
