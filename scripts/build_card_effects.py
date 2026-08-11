"""Harvest card id -> rules text from the bot's own combat logs.

Full card descriptions appear only where cards are visible in a fight (`player.hand` in combat
records); map `DeckCard`s and the compendium omit them. The §5-C capability estimate needs them to
price a deck *on the map* (the elite gate), so harvest them here, keyed by id + upgrade state
(an upgraded Strike hits for more). Output: data/card_effects.json {"<id>|<0|1>": description}.

Re-run as runs accumulate; coverage grows toward the cards the bot actually plays.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "runs"
DEST = ROOT / "data" / "card_effects.json"


def main() -> int:
    # MAJORITY VOTE per key, not last-seen (owner catch 2026-08-10): live card
    # text carries RUN-SPECIFIC riders -- enchants ("Draw 2 cards the first
    # time this is played", Replay N) and fight effects (the Three Knights'
    # "Ethereal.", per owner). Last-seen-wins let one enchanted sighting poison
    # the canonical entry (BULLY|1 / INFERNAL_BLADE / LETHALITY / MAD_SCIENCE
    # all shipped with phantom Ethereal; Lethality also a Swift rider). The
    # unmodified text is overwhelmingly the most common sighting. Weight by
    # RUN, not poll (one long fight would out-vote many clean runs).
    votes: dict[str, Counter[str]] = {}
    runs = 0
    for f in sorted(LOGS.glob("*/decisions.jsonl")):
        runs += 1
        per_run: dict[str, set[str]] = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            st = json.loads(line).get("state") or {}
            hand = (st.get("player") or {}).get("hand") or []
            for c in hand:
                cid, desc = c.get("id"), c.get("description")
                if cid and desc:
                    key = f"{cid}|{1 if c.get('is_upgraded') else 0}"
                    per_run.setdefault(key, set()).add(desc)
        for key, descs in per_run.items():
            for d in descs:
                votes.setdefault(key, Counter())[d] += 1
    table = {key: cnt.most_common(1)[0][0] for key, cnt in votes.items()}
    DEST.write_text(json.dumps(table, indent=0, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(table)} card descriptions from {runs} runs to {DEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
