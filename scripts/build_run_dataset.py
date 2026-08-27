"""Stage 0 of the learning direction (PLAN §9): run logs -> training tables.

Walks logs/runs/ and emits JSONL tables under logs/datasets/ (gitignored,
regenerable — the run logs stay the source of truth):

  runs.jsonl    one row per run: identity, config era, outcome, boss-by-act
  drafts.jsonl  one row per card_reward decision: offers, pick, deck, labels
  events.jsonl  one row per event choice (incl. Ancients): options, pick, labels
  rests.jsonl   one row per rest-site choice: options, pick, labels
  fights.jsonl  one row per combat: enemies, hp_start/hp_end, rounds, labels

Rows carry RAW ids (+ upgrade marks) and lightly derived outcome labels only.
Feature extraction (tag-table / textparse vectors) is deliberately NOT baked in —
it stays a training-time module so the feature schema can evolve without
rebuilding this dataset. Labels beyond win/loss exist to decouple draft quality
from tactical skill (PLAN §9 nested-feedback): per-fight hp deltas, boss-entry
HP, act survival. `outcome_valid` gates rows from error/abandoned/killed runs.

Shop purchase decisions are out of scope for v1 (draft-like but with gold
pricing; revisit at stage 1 if the model wants them).

Usage: python scripts/build_run_dataset.py [--limit N] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
OUT = ROOT / "logs" / "datasets"

# Record types that can legitimately follow a combat and whose player.hp closes
# the open fight. Deliberately excludes card_select/hand_select (those occur
# MID-combat: discard picks, Armaments upgrades) and monster/boss themselves.
_FIGHT_CLOSERS = {
    "rewards", "map", "rest_site", "shop", "event", "treasure", "card_reward",
}


def _card_key(c: dict) -> str:
    return (c.get("id") or "?") + ("+" if c.get("is_upgraded") else "")


def _player_bits(st: dict) -> dict:
    p = st.get("player") or {}
    run = st.get("run") or {}
    return {
        "act": run.get("act"),
        "floor": run.get("floor"),
        "hp": p.get("hp"),
        "max_hp": p.get("max_hp"),
        "gold": p.get("gold"),
        "deck": [_card_key(c) for c in p.get("deck") or []],
        "relics": [r.get("id") for r in p.get("relics") or []],
        "potions": [q.get("id") for q in p.get("potions") or [] if q.get("id")],
    }


def parse_run(run_dir: Path) -> dict[str, list[dict]] | None:
    """Parse one run directory into table rows. None if meta.json is unreadable."""
    try:
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    o = meta.get("outcome") or {}
    outcome_valid = bool(o) and o.get("status") == "completed" \
        and not o.get("was_abandoned")
    victory = bool(o.get("victory"))
    final_act = o.get("act")
    final_floor = o.get("floor")

    run_id = run_dir.name
    boss_by_act: dict[int, str] = {}
    fights: list[dict] = []
    open_fight: dict | None = None
    drafts: list[dict] = []
    events: list[dict] = []
    rests: list[dict] = []

    def close_fight(hp_end, closed=True):
        nonlocal open_fight
        if open_fight is None:
            return
        f = open_fight
        f["hp_end"] = hp_end
        f["hp_delta"] = (hp_end - f["hp_start"]) \
            if (hp_end is not None and f["hp_start"] is not None) else None
        f["closed"] = closed
        fights.append(f)
        open_fight = None

    dec_path = run_dir / "decisions.jsonl"
    try:
        lines = dec_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        # cheap prefilter: combat "wait" records (no action) carry a slim state
        # with nothing to harvest — skip the json parse (they are ~70% of
        # combat records)
        if '"action": null' in raw and (
                '"state_type": "monster"' in raw or '"state_type": "boss"' in raw):
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stype = r.get("state_type")
        st = r.get("state") or {}
        act_rec = r.get("action") or {}
        seq = r.get("seq")

        if stype == "map":
            m = st.get("map") or {}
            b = m.get("boss") or {}
            a = (st.get("run") or {}).get("act")
            if a is not None and b.get("name"):
                boss_by_act[a] = b["name"]
            if open_fight is not None:
                hp = (st.get("player") or {}).get("hp")
                close_fight(hp)
            continue

        if stype in ("monster", "boss"):
            battle = st.get("battle")
            p = st.get("player") or {}
            if not battle or p.get("hp") is None:
                continue
            floor = (st.get("run") or {}).get("floor")
            if open_fight is not None and open_fight["floor"] != floor:
                # never saw a closer (schema drift / straight into next fight)
                close_fight(open_fight.get("last_hp"), closed=False)
            if open_fight is None:
                open_fight = {
                    "run_id": run_id,
                    "seq_start": seq,
                    "floor": floor,
                    "act": (st.get("run") or {}).get("act"),
                    "is_boss": stype == "boss",
                    "enemies": [e.get("name") or e.get("id")
                                for e in battle.get("enemies") or []],
                    "hp_start": p.get("hp"),
                    "max_hp": p.get("max_hp"),
                    "rounds": 0,
                    "n_actions": 0,
                }
            open_fight["rounds"] = max(
                open_fight["rounds"], battle.get("round") or 0)
            open_fight["n_actions"] += 1
            open_fight["last_hp"] = p.get("hp")
            continue

        if open_fight is not None and stype in _FIGHT_CLOSERS:
            hp = (st.get("player") or {}).get("hp")
            if hp is not None:
                close_fight(hp)

        if stype == "card_reward":
            cards = (st.get("card_reward") or {}).get("cards") or []
            if not cards:
                continue
            picked_idx = act_rec.get("card_index") \
                if act_rec.get("action") == "select_card_reward" else None
            picked = next(
                (_card_key(c) for c in cards if c.get("index") == picked_idx),
                None)
            drafts.append({
                "run_id": run_id, "seq": seq,
                **_player_bits(st),
                "offers": [{
                    "key": _card_key(c), "type": c.get("type"),
                    "rarity": c.get("rarity"), "cost": c.get("cost"),
                } for c in cards],
                "can_skip": (st.get("card_reward") or {}).get("can_skip"),
                "picked_index": picked_idx,
                "picked": picked,
                "bot_scores": r.get("scores"),
                "rationale": (r.get("rationale") or "")[:200],
            })
        elif stype == "event" and act_rec.get("action") == "choose_event_option":
            ev = st.get("event") or {}
            options = ev.get("options") or []
            real = [op for op in options if not op.get("is_proceed")]
            if not real:
                continue
            idx = act_rec.get("index")
            events.append({
                "run_id": run_id, "seq": seq,
                **_player_bits(st),
                "event_name": ev.get("event_name"),
                "is_ancient": ev.get("is_ancient"),
                "options": [{"index": op.get("index"),
                             "title": op.get("title"),
                             "description": (op.get("description") or "")[:200]}
                            for op in options],
                "picked_index": idx,
                "picked_title": next(
                    (op.get("title") for op in options
                     if op.get("index") == idx), None),
                "rationale": (r.get("rationale") or "")[:200],
            })
        elif stype == "rest_site" and act_rec.get("action") == "choose_rest_option":
            rs = st.get("rest_site") or {}
            idx = act_rec.get("index")
            opts = rs.get("options") or []
            rests.append({
                "run_id": run_id, "seq": seq,
                **_player_bits(st),
                "options": [op.get("id") for op in opts],
                "picked_index": idx,
                "picked": next((op.get("id") for op in opts
                                if op.get("index") == idx), None),
                "rationale": (r.get("rationale") or "")[:200],
            })

    # a fight open at end-of-log: the run died in it (or was killed mid-run)
    if open_fight is not None:
        died_here = outcome_valid and not victory \
            and str(o.get("killed_by_encounter") or "").startswith("ENCOUNTER")
        close_fight(0 if died_here else open_fight.get("last_hp"),
                    closed=died_here)
        if died_here:
            fights[-1]["died_here"] = True

    boss_entry_hp = {f["act"]: f["hp_start"] for f in fights if f["is_boss"]}

    def label(row: dict) -> dict:
        a, fl, sq = row.get("act"), row.get("floor"), row.get("seq")
        nxt = [f["hp_delta"] for f in fights
               if f["seq_start"] is not None and sq is not None
               and f["seq_start"] > sq and f["hp_delta"] is not None]
        row.update({
            "outcome_valid": outcome_valid,
            "victory": victory if outcome_valid else None,
            "floors_survived": (final_floor - fl)
            if (outcome_valid and fl is not None and final_floor is not None)
            else None,
            "beat_act_boss": (victory or (final_act or 0) > a)
            if (outcome_valid and a is not None) else None,
            "act_boss": boss_by_act.get(a),
            "hp_boss_entry": boss_entry_hp.get(a),
            "hp_delta_next3": sum(nxt[:3]) if nxt else None,
            "config_hash": meta.get("config_hash"),
        })
        return row

    for f in fights:
        f["outcome_valid"] = outcome_valid
        f["victory"] = victory if outcome_valid else None
        f["config_hash"] = meta.get("config_hash")
        f.pop("last_hp", None)

    run_row = {
        "run_id": run_id,
        "started_at": meta.get("started_at"),
        "config_hash": meta.get("config_hash"),
        "policy": meta.get("policy"),
        "character": o.get("character"),
        "ascension": o.get("ascension"),
        "status": o.get("status") if o else None,
        "outcome_valid": outcome_valid,
        "victory": victory if outcome_valid else None,
        "final_act": final_act,
        "final_floor": final_floor,
        "killed_by": (str(o.get("killed_by_encounter") or "")
                      .replace("ENCOUNTER.", "")) or None,
        "seed": o.get("seed"),
        "build_id": o.get("build_id"),
        "boss_by_act": {str(k): v for k, v in sorted(boss_by_act.items())},
        "n_fights": len(fights),
        "n_drafts": len(drafts),
        "n_decisions": o.get("decisions"),
    }
    return {
        "runs": [run_row],
        "drafts": [label(d) for d in drafts],
        "events": [label(e) for e in events],
        "rests": [label(x) for x in rests],
        "fights": fights,
    }


def build(runs_dir: Path, out_dir: Path, limit: int | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dirs = sorted(d for d in runs_dir.iterdir()
                  if d.is_dir() and (d / "meta.json").is_file())
    if limit:
        dirs = dirs[-limit:]
    tables = ("runs", "drafts", "events", "rests", "fights")
    handles = {t: (out_dir / f"{t}.jsonl").open("w", encoding="utf-8")
               for t in tables}
    counts = dict.fromkeys(tables, 0)
    parse_errors: list[str] = []
    try:
        for i, d in enumerate(dirs):
            rows = parse_run(d)
            if rows is None:
                parse_errors.append(d.name)
                continue
            for t in tables:
                for row in rows[t]:
                    handles[t].write(
                        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                        + "\n")
                counts[t] += len(rows[t])
            if (i + 1) % 250 == 0:
                print(f"  {i + 1}/{len(dirs)} runs...")
    finally:
        for h in handles.values():
            h.close()
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "runs_dir": str(runs_dir),
        "n_run_dirs": len(dirs),
        "parse_errors": parse_errors,
        "rows": counts,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", type=Path, default=LOGS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--limit", type=int, default=None,
                    help="only the latest N runs (smoke tests)")
    args = ap.parse_args()
    manifest = build(args.runs_dir, args.out, args.limit)
    print(f"wrote {manifest['rows']} to {args.out} "
          f"({len(manifest['parse_errors'])} parse errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
