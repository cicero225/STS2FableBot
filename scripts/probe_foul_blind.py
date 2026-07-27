"""Blind foul-throw probe: fire use_potion with NO state reads.

Variant 2 of the foul-throw diagnostic: the mod's /state read re-renders (and the
first probe's polling appears to have auto-advanced the shopkeeper screen — it
serialized as 'unknown' and then opened itself). So: the owner clicks the shop node
manually and HOLDS the shopkeeper screen; this fires a single UsePotion for the
given slot with zero state polls before it. If it lands, the window exists and our
polling was the killer; if it errors on the held screen, the game's usability check
refuses API potion-use there and the throw needs a dedicated fork action.

Run: .venv/Scripts/python scripts/probe_foul_blind.py <slot>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2bot.client import Sts2Client
from sts2bot.client.actions import UsePotion


def main() -> None:
    slot = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    with Sts2Client() as client:
        r = client.act(UsePotion(slot=slot, target=None))
        print(f"blind throw slot {slot} ->", r.model_dump(exclude_none=True))


if __name__ == "__main__":
    main()
