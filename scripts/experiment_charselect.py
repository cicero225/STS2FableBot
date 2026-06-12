"""One-off P0.7 experiment: does double-selecting the character before embark fix
the wrong-character-embark bug seen on game v0.103.3 + STS2MCP 0.4.0?

Protocol: navigate to character select, send IRONCLAD, re-send IRONCLAD once confirm
is enabled, embark, then poll until the run starts and report who we actually are.
Run attended; whoever it starts, the normal `sts2bot play` can finish the run.
"""

import sys
import time

from sts2bot.client import Sts2Client
from sts2bot.client.actions import MenuSelect


def step(client: Sts2Client, option: str) -> None:
    result = client.act(MenuSelect(option=option))
    print(f"  menu_select {option!r}: {result.status} - {result.detail}")


def main() -> int:
    client = Sts2Client()
    for _ in range(40):
        raw = client.get_state_raw()
        screen = raw.get("menu_screen")
        state_type = raw.get("state_type")
        print(f"state={state_type} screen={screen}")

        if state_type == "menu":
            if screen == "main":
                step(client, "singleplayer")
            elif screen == "singleplayer":
                step(client, "standard")
            elif screen == "character_select":
                options = {
                    o["name"] if isinstance(o, dict) else o: (
                        o.get("enabled", True) if isinstance(o, dict) else True
                    )
                    for o in raw.get("options", [])
                }
                if options.get("confirm"):
                    print("  confirm enabled -> RE-selecting IRONCLAD, then embark")
                    step(client, "IRONCLAD")
                    time.sleep(0.5)
                    step(client, "confirm")
                    break
                else:
                    step(client, "IRONCLAD")
            elif screen == "tutorial_prompt":
                step(client, "no")
            else:
                print(f"  (unhandled screen {screen}; waiting)")
        time.sleep(0.5)

    print("waiting for run to start...")
    for _ in range(60):
        raw = client.get_state_raw()
        player = raw.get("player") or {}
        if raw.get("run") is not None and player.get("character"):
            print(f"RUN STARTED AS: {player['character']}")
            client.close()
            return 0
        if raw.get("menu_screen") == "tutorial_prompt":
            step(client, "no")
        time.sleep(0.5)
    print("run did not start within 30s")
    client.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
