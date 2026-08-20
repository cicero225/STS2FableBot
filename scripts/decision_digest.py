"""Print the bot's card drafts, shop purchases, and event choices at scale.

Owner exercise (2026-08-19): "there's a lot of latent information there I
could potentially comment on." One compact line per decision, grouped by run,
showing what was OFFERED, what was PICKED, and the bot's stated reason --
reviewable in bulk, greppable by card/event name.

Usage: python scripts/decision_digest.py [--runs N] [--out FILE]
Default output: logs/reports/decision_digest_<latest-run-stamp>.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"


def _fmt_card(c: dict) -> str:
    up = "+" if c.get("is_upgraded") else ""
    return f"{c.get('name') or c.get('id') or '?'}{up}"


def digest_run(run_dir: Path) -> list[str]:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    o = meta.get("outcome") or {}
    kb = (str(o.get("killed_by_encounter") or "")).replace("ENCOUNTER.", "")
    head = (f"## {run_dir.name} | A{o.get('act', '?')} f{o.get('floor', '?')} "
            f"{'WIN' if o.get('victory') else 'loss'}"
            f"{' (' + kb + ')' if kb and kb != 'NONE.NONE' else ''} "
            f"| seed {o.get('seed', '?')}")
    lines = [head]
    for raw in (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        r = json.loads(raw)
        st = r.get("state") or {}
        stype = r.get("state_type")
        act = r.get("action") or {}
        ra = (r.get("rationale") or "").strip()
        floor = (st.get("run") or {}).get("floor", "?")

        if stype == "card_reward":
            cards = (st.get("card_reward") or {}).get("cards") or []
            opts = " | ".join(_fmt_card(c) for c in cards)
            lines.append(f"- f{floor} DRAFT  [{opts}]  -> {ra}")
        elif stype == "shop" and act.get("action") == "shop_purchase":
            lines.append(f"- f{floor} SHOP   {ra}")
        elif stype == "shop" and act.get("action") == "proceed":
            gold = (st.get("player") or {}).get("gold")
            items = [
                i for i in ((st.get("shop") or {}).get("items") or [])
                if i.get("is_stocked")
            ]
            def label(i):
                nm = (i.get("card_name") or i.get("relic_name")
                      or i.get("potion_name") or i.get("category"))
                p = i.get("gold_price")
                return f"{nm} {p}g" if p is not None else f"{nm}"
            left = ", ".join(label(i) for i in items[:10])
            lines.append(f"- f{floor} SHOP   leave with {gold}g; left behind: {left or '-'}")
        elif stype == "event" and act.get("action") == "choose_event_option":
            ev = st.get("event") or {}
            options = ev.get("options") or []
            titles = " | ".join((op.get("title") or "?") for op in options
                                if not op.get("is_proceed"))
            idx = act.get("index")
            pick = next((op.get("title") for op in options
                         if op.get("index") == idx), "?")
            if titles and not (len(options) == 1 and options[0].get("is_proceed")):
                lines.append(f"- f{floor} EVENT  {ev.get('event_name') or '?'}: "
                             f"[{titles}]  -> {pick}  ({ra})")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=40)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    dirs = sorted((d for d in LOGS.glob("*/") if (d / "meta.json").is_file()),
                  key=lambda d: (d / "meta.json").stat().st_mtime)[-args.runs:]
    out_lines = [f"# Decision digest — latest {len(dirs)} runs", ""]
    for d in dirs:
        try:
            out_lines.extend(digest_run(d))
            out_lines.append("")
        except Exception as e:  # a malformed run log must not kill the digest
            out_lines.append(f"## {d.name} — digest error: {e}")
    dest = Path(args.out) if args.out else (
        ROOT / "logs" / "reports" / f"decision_digest_{dirs[-1].name[:15]}.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out_lines), encoding="utf-8")
    n_dec = sum(1 for line in out_lines if line.startswith("- "))
    print(f"wrote {n_dec} decisions across {len(dirs)} runs to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
