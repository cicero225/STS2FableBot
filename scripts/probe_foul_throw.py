"""Live probe: WHEN is the Foul-potion merchant throw usable via the API?

Proven (win run 2026-07-25): use_potion on the shop screen errors — the game's
own PassesCustomUsabilityCheck rejects it there. Owner: the in-game throw happens
BEFORE the shop opens. This probe finds the window empirically.

Setup (owner): a run on the BOT profile holding a Foul, standing on the MAP with a
Shop as one of the next options. Savescum (quit to menu before buying) to retry.

It will, in order, printing every result:
  1. try the throw on the MAP screen (before choosing the node)
  2. choose the Shop node
  3. spam the throw during the transition polls (fast, ~10 attempts)
  4. try once on the first SHOP state (the known-fail baseline)
It buys nothing and stops there.

Run: .venv/Scripts/python scripts/probe_foul_throw.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2bot.client import Sts2Client
from sts2bot.client.actions import ChooseMapNode, UsePotion
from sts2bot.client.models import parse_state


def foul_slot(state) -> int | None:
    for p in (state.player.potions if state.player else []) or []:
        if "FOUL" in f"{p.id or ''} {p.name or ''}".upper():
            return p.slot
    return None


def main() -> None:
    with Sts2Client() as client:
        state = parse_state(client.get_state_raw())
        if state.state_type != "map":
            print(f"not on a map screen (state={state.state_type}); "
                  "stand on the map one node before the shop and rerun")
            return
        slot = foul_slot(state)
        if slot is None:
            print("no Foul in the belt; setup incomplete")
            return
        shop_opt = next((o for o in state.map.next_options
                         if (o.type or "").lower() == "shop"), None)
        if shop_opt is None:
            print("no Shop among next options; setup incomplete")
            return

        print(f"[1] throw on MAP screen (slot {slot}):")
        r = client.act(UsePotion(slot=slot, target=None))
        print("    ->", r.model_dump(exclude_none=True))

        print(f"[2] choosing Shop node index {shop_opt.index}")
        r = client.act(ChooseMapNode(index=shop_opt.index))
        print("    ->", r.model_dump(exclude_none=True))

        print("[3] spamming throw during transition:")
        for i in range(10):
            raw = client.get_state_raw()
            st = parse_state(raw)
            r = client.act(UsePotion(slot=slot, target=None))
            d = r.model_dump(exclude_none=True)
            print(f"    poll {i} state={st.state_type}: {d}")
            if d.get("status") == "ok" and "cannot" not in str(d).lower():
                print("    ^^^ WINDOW FOUND")
            if st.state_type == "shop":
                break
            time.sleep(0.25)

        print("[4] baseline throw on SHOP screen:")
        r = client.act(UsePotion(slot=slot, target=None))
        print("    ->", r.model_dump(exclude_none=True))
        print("done — no purchases made; savescum to retry.")


if __name__ == "__main__":
    main()
