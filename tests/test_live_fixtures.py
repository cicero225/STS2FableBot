"""Regressions from live-game observations (P0.7). Live captures live in
fixtures/live/ and every one of them must always parse."""

import json
from pathlib import Path

import pytest

from sts2bot.client import parse_state
from sts2bot.client.models import CombatState
from sts2bot.policy.base import LoopContext, Wait
from sts2bot.policy.trivial import TrivialRouter

LIVE_DIR = Path(__file__).parent / "fixtures" / "live"
LIVE_FILES = sorted(LIVE_DIR.glob("*.json"))


@pytest.mark.parametrize("path", LIVE_FILES, ids=lambda p: p.stem)
def test_live_capture_parses(path: Path) -> None:
    parse_state(json.loads(path.read_text(encoding="utf-8")))


def test_live_combat_capture_has_battle() -> None:
    state = parse_state(json.loads((LIVE_DIR / "combat_live.json").read_text(encoding="utf-8")))
    assert isinstance(state, CombatState)
    assert state.battle is not None and state.battle.enemies


def test_combat_without_battle_block_waits() -> None:
    """Observed live: 'monster' state with no battle while the room loads."""
    state = parse_state(
        {
            "state_type": "monster",
            "run": {"act": 1, "floor": 1, "ascension": 0},
            "player": {
                "character": "The Ironclad",
                "hp": 80,
                "max_hp": 80,
                "status": [],
                "relics": [],
                "potions": [],
                "max_potion_slots": 3,
            },
        }
    )
    assert isinstance(state, CombatState) and state.battle is None
    decision = TrivialRouter().decide(state, LoopContext())
    assert isinstance(decision, Wait)


def test_embark_is_sent_only_once() -> None:
    """Observed live: character_select lingers after embark; re-confirming errors."""
    router = TrivialRouter()
    ctx = LoopContext(character="IRONCLAD")
    screen = {
        "state_type": "menu",
        "menu_screen": "character_select",
        "options": ["IRONCLAD", "SILENT", "confirm", "embark", "back"],
    }
    first = router.decide(parse_state(screen), ctx)
    assert not isinstance(first, Wait) and first.action.payload()["option"] == "IRONCLAD"
    second = router.decide(parse_state(screen), ctx)
    assert not isinstance(second, Wait) and second.action.payload()["option"] == "confirm"
    third = router.decide(parse_state(screen), ctx)
    assert isinstance(third, Wait)
