"""Scripted fake game for end-to-end loop testing without the real client.

ScriptedGame is a tiny state machine: named states (raw API payloads) with
transitions keyed by action-payload subsets. FakeClient implements the loop's
GameClient protocol against it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from sts2bot.client.actions import Action
from sts2bot.client.http import ActionResult

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "doc_states.json").read_text(encoding="utf-8")
)


def fixture(name: str) -> dict[str, Any]:
    return copy.deepcopy(FIXTURES[name])


class ScriptedGame:
    def __init__(
        self,
        states: dict[str, dict[str, Any]],
        transitions: dict[str, list[tuple[dict[str, Any], str]]],
        start: str,
    ):
        self.states = states
        self.transitions = transitions
        self.current = start
        self.history: list[tuple[str, dict[str, Any]]] = []

    def state(self) -> dict[str, Any]:
        return copy.deepcopy(self.states[self.current])

    def apply(self, payload: dict[str, Any]) -> ActionResult:
        for subset, next_state in self.transitions.get(self.current, []):
            if all(payload.get(k) == v for k, v in subset.items()):
                self.history.append((self.current, payload))
                self.current = next_state
                return ActionResult(status="ok", message=f"-> {next_state}")
        return ActionResult(
            status="error",
            error=f"unexpected action {payload} in state {self.current}",
        )


class FakeClient:
    def __init__(self, game: ScriptedGame, compendium: dict[str, Any] | None = None):
        self.game = game
        self.compendium = compendium or {}

    def get_state_raw(self) -> dict[str, Any]:
        return self.game.state()

    def act(self, action: Action) -> ActionResult:
        return self.game.apply(action.payload())

    def get_compendium(self) -> dict[str, Any]:
        return copy.deepcopy(self.compendium)


def build_doc_script() -> ScriptedGame:
    """A full synthetic run: menus -> Neow -> map -> combat -> rewards (incl. card
    reward) -> rest -> game over -> back to main menu."""
    states: dict[str, dict[str, Any]] = {}
    transitions: dict[str, list[tuple[dict[str, Any], str]]] = {}

    def add(name: str, payload: dict[str, Any], *trans: tuple[dict[str, Any], str]) -> None:
        states[name] = payload
        transitions[name] = list(trans)

    # --- menus into the run (fresh profile: no saved run, so no "continue" option)
    menu_main = fixture("menu_main")
    menu_main["options"] = [o for o in menu_main["options"] if o != "continue"]
    add(
        "menu_main",
        menu_main,
        ({"action": "menu_select", "option": "singleplayer"}, "menu_sp"),
    )
    add(
        "menu_sp",
        {
            "state_type": "menu",
            "message": "Choose run type.",
            "menu_screen": "singleplayer",
            "options": ["standard", "daily", "custom", "back"],
        },
        ({"action": "menu_select", "option": "standard"}, "char_select"),
    )
    add(
        "char_select",
        fixture("menu_character_select"),
        ({"action": "menu_select", "option": "IRONCLAD"}, "char_select_picked"),
    )
    picked = fixture("menu_character_select")
    picked["message"] = "Character selected: The Ironclad."
    add(
        "char_select_picked",
        picked,
        ({"action": "menu_select", "option": "confirm"}, "neow"),
    )

    # --- Neow-style start event, then first map choice
    add(
        "neow",
        fixture("event_neow"),
        ({"action": "choose_event_option", "index": 0}, "map1"),
    )
    add("map1", fixture("map"), ({"action": "choose_map_node", "index": 0}, "combat1"))

    # --- combat: strike (targeted), defend (untargeted), then only-unplayable -> end turn
    combat1 = fixture("combat_monster")
    add(
        "combat1",
        combat1,
        (
            {"action": "play_card", "card_index": 0, "target": "JAW_WORM_0"},
            "combat2",
        ),
    )

    combat2 = fixture("combat_monster")
    combat2["battle"]["enemies"][0]["hp"] = 35
    hand = combat2["player"]["hand"]
    combat2["player"]["hand"] = [
        {**hand[1], "index": 0},  # Defend (Self target)
        {**hand[2], "index": 1},  # Bash, still unplayable
    ]
    combat2["player"]["discard_pile_count"] = 3
    add("combat2", combat2, ({"action": "play_card", "card_index": 0}, "combat3"))

    combat3 = fixture("combat_monster")
    combat3["battle"]["enemies"][0]["hp"] = 35
    combat3["player"]["block"] = 5
    combat3["player"]["energy"] = 1
    combat3["player"]["hand"] = [{**hand[2], "index": 0}]  # only unplayable Bash
    add("combat3", combat3, ({"action": "end_turn"}, "rewards1"))

    # --- rewards: gold, potion, card (opens card_reward), then proceed
    rewards1 = fixture("rewards")
    add("rewards1", rewards1, ({"action": "claim_reward", "index": 0}, "rewards2"))

    rewards2 = fixture("rewards")
    rewards2["rewards"]["items"] = [
        {**rewards1["rewards"]["items"][1], "index": 0},
        {**rewards1["rewards"]["items"][2], "index": 1},
    ]
    add("rewards2", rewards2, ({"action": "claim_reward", "index": 0}, "rewards3"))

    rewards3 = fixture("rewards")
    rewards3["rewards"]["items"] = [{**rewards1["rewards"]["items"][2], "index": 0}]
    add("rewards3", rewards3, ({"action": "claim_reward", "index": 0}, "card_reward"))

    add(
        "card_reward",
        fixture("card_reward"),
        ({"action": "select_card_reward", "card_index": 0}, "rewards4"),
    )

    rewards4 = fixture("rewards")
    rewards4["rewards"]["items"] = []
    add("rewards4", rewards4, ({"action": "proceed"}, "map2"))

    # --- second map step into a rest site
    map2 = fixture("map")
    map2["map"]["current_position"] = {"col": 2, "row": 3, "type": "RestSite"}
    add("map2", map2, ({"action": "choose_map_node", "index": 0}, "rest"))

    add("rest", fixture("rest_site"), ({"action": "choose_rest_option", "index": 0}, "rest_done"))

    rest_done = fixture("rest_site")
    for option in rest_done["rest_site"]["options"]:
        option["is_enabled"] = False
    rest_done["rest_site"]["can_proceed"] = True
    add("rest_done", rest_done, ({"action": "proceed"}, "map3"))

    map3 = fixture("map")
    map3["map"]["current_position"] = {"col": 2, "row": 4, "type": "Monster"}
    add("map3", map3, ({"action": "choose_map_node", "index": 0}, "game_over"))

    # --- death and dismissal
    add(
        "game_over",
        fixture("game_over"),
        ({"action": "menu_select", "option": "main_menu"}, "menu_end"),
    )
    menu_end = fixture("menu_main")
    menu_end["message"] = "Back at the main menu."
    menu_end["options"] = [o for o in menu_end["options"] if o != "continue"]
    add("menu_end", menu_end)

    return ScriptedGame(states, transitions, start="menu_main")
