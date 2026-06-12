"""One-off session-2 verification: set_ascension behavior at character select.

Expected on a profile with no ascension unlocks: state shows ascension/max_ascension,
set_ascension 1 refuses politely (max 0), set_ascension 0 is accepted. Backs out to
the main menu afterwards; starts no run.
"""

import sys
import time

from sts2bot.client import Sts2Client
from sts2bot.client.actions import MenuSelect, SetAscension


def main() -> int:
    client = Sts2Client()

    def show(label: str, result) -> None:
        print(f"{label}: {result.status} - {result.detail}")

    for _ in range(30):
        raw = client.get_state_raw()
        screen = raw.get("menu_screen")
        if raw.get("state_type") != "menu":
            print(f"not in menu (state={raw.get('state_type')}); aborting")
            return 1
        if screen == "main":
            show("open singleplayer", client.act(MenuSelect(option="singleplayer")))
        elif screen == "singleplayer":
            show("standard", client.act(MenuSelect(option="standard")))
        elif screen == "character_select":
            if raw.get("selection_busy"):
                print("selection busy (unlock animation); waiting")
                time.sleep(1.0)
                continue
            if (raw.get("selected_character") or "").upper() != "IRONCLAD":
                show("select IRONCLAD", client.act(MenuSelect(option="IRONCLAD")))
                time.sleep(0.5)
                continue
            print(f"state ascension={raw.get('ascension')} max={raw.get('max_ascension')}")
            show("set_ascension 1 (expect refusal)", client.act(SetAscension(level=1)))
            show("set_ascension 0 (expect ok)", client.act(SetAscension(level=0)))
            show("back to main", client.act(MenuSelect(option="back")))
            client.close()
            return 0
        time.sleep(0.5)
    print("never reached character select")
    client.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
