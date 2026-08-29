"""Render a per-round fight tape from a run log — bot halves show plans and
rationales; human halves (recorder/handoff-follow) reconstruct plays from
hand diffs between polls. Built for the owner's bot-vs-human Aeonglass
commentary (2026-08-29); generic over boss name.

Usage: python scripts/fight_tape.py <run_dir_name> <boss substring> [--out FILE]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tape(run_dir: str, boss: str) -> list[str]:
    lines: list[str] = []
    prev_hand: list[str] | None = None
    prev_pots = None
    prev_energy = None
    cur_round = None
    for raw in (ROOT / "logs" / "runs" / run_dir / "decisions.jsonl").open(
            encoding="utf-8"):
        if boss not in raw:
            continue
        try:
            r = json.loads(raw)
        except json.JSONDecodeError:
            continue
        st = r.get("state") or {}
        b = st.get("battle") or {}
        bodies = [e for e in b.get("enemies") or []
                  if boss in (e.get("name") or "")]
        if not bodies:
            continue
        p = st.get("player") or {}
        rnd = b.get("round")
        hand = [c.get("name") or c.get("id") for c in p.get("hand") or []]
        boss_e = bodies[0]
        if rnd != cur_round:
            cur_round = rnd
            withers = sum(1 for h in hand if "Wither" in (h or ""))
            intents = [i.get("label") for e in b.get("enemies") or []
                       for i in e.get("intents") or []]
            lines.append(
                f"\n**Round {rnd}** — player {p.get('hp')}/{p.get('max_hp')} "
                f"block {p.get('block')} energy {p.get('energy')} | "
                f"{boss_e.get('name')} {boss_e.get('hp')}/{boss_e.get('max_hp')} "
                f"block {boss_e.get('block')} | intents {intents} | "
                f"withers in hand: {withers}")
            lines.append(f"  hand: {hand}")
            prev_hand = hand
        act = r.get("action") or {}
        if act.get("action") == "play_card":
            ci = act.get("card_index")
            nm = hand[ci] if ci is not None and ci < len(hand) else "?"
            ra = (r.get("rationale") or "")[:110]
            lines.append(f"  PLAY {nm}"
                         + (f" -> {act.get('target')}" if act.get("target") else "")
                         + (f"   [{ra}]" if ra else ""))
        elif act.get("action") == "use_potion":
            lines.append(f"  POTION slot {act.get('slot')} "
                         f"[{(r.get('rationale') or '')[:80]}]")
        elif act.get("action") == "end_turn":
            lines.append(f"  END TURN [{(r.get('rationale') or '')[:60]}]")
        elif not act:
            # recorder/human half: full per-poll deltas. Hand-shrinkage alone
            # missed draw-replacing plays (owner catch 2026-08-29: Offering+
            # exhausts itself and draws 5 — the hand GREW, the play vanished
            # from the tape) and potions entirely (belt never diffed).
            gone = list(prev_hand or [])
            for h in hand:
                if h in gone:
                    gone.remove(h)
            arrived = list(hand)
            for h in prev_hand or []:
                if h in arrived:
                    arrived.remove(h)
            pots = [q.get("id") for q in p.get("potions") or []]
            drunk = [q for q in (prev_pots if prev_pots is not None else pots)
                     if q not in pots]
            de = (p.get("energy") or 0) - (prev_energy or 0)
            bits = []
            if gone:
                bits.append(f"left: {gone}")
            if arrived:
                bits.append(f"drew/got: {arrived}")
            if drunk:
                bits.append(f"POTION drunk: {drunk}")
            if de and (gone or arrived or drunk):
                bits.append(f"energy {'+' if de > 0 else ''}{de}")
            if bits:
                # v3 (owner misread 2026-08-29: four r5 plays scanned as
                # noise): carry running block/hp so plays are visible as
                # state changes, not bare departures
                bits.append(f"[hp {p.get('hp')} blk {p.get('block')}]")
                lines.append("  (human) " + " | ".join(bits))
            prev_pots = pots
            prev_energy = p.get("energy")
            prev_hand = hand
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("boss")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    lines = [f"# Fight tape: {args.run_dir} vs {args.boss}", *tape(args.run_dir, args.boss)]
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(lines)} lines)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
