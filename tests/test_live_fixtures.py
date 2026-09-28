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


def test_open_timeline_screen_is_hands_off() -> None:
    """Found live: the bot's back-out reflex kicked the owner off the Timeline screen
    mid-epoch-reveal. Any open Timeline belongs to the owner."""
    state = parse_state(
        {
            "state_type": "menu",
            "menu_screen": "timeline",
            "message": "Timeline.",
            "options": ["advance", "back"],
        }
    )
    decision = TrivialRouter().decide(state, LoopContext())
    assert isinstance(decision, Wait)
    assert decision.reason.startswith("MANUAL:")


def test_blocked_epoch_menu_waits_for_owner() -> None:
    """Observed live: after first death, main menu loses 'singleplayer' until the
    owner manually reveals a Timeline epoch (mod refuses to automate it)."""
    state = parse_state(
        json.loads((LIVE_DIR / "menu_blocked_epoch.json").read_text(encoding="utf-8"))
    )
    decision = TrivialRouter().decide(state, LoopContext())
    assert isinstance(decision, Wait)
    assert decision.reason.startswith("MANUAL:")
    assert "NEOW_EPOCH" in decision.reason


def test_unclaimable_reward_is_abandoned_after_two_attempts() -> None:
    """Observed live: potion reward with a full belt claims 'ok' but no-ops forever."""
    router = TrivialRouter()
    ctx = LoopContext()
    stuck = {
        "state_type": "rewards",
        "run": {"act": 1, "floor": 6, "ascension": 0},
        "player": {
            "character": "The Regent",
            "hp": 50,
            "max_hp": 75,
            "status": [],
            "relics": [],
            "potions": [
                {"id": "BLOCK_POTION", "name": "Block Potion", "slot": 0},
                {"id": "DEX_POTION", "name": "Dexterity Potion", "slot": 1},
                {"id": "FLEX_POTION", "name": "Flex Potion", "slot": 2},
            ],
            "max_potion_slots": 3,
        },
        "rewards": {
            "items": [
                {
                    "index": 0,
                    "type": "potion",
                    "description": "Energy Potion",
                    "potion_id": "ENERGY_POTION",
                    "potion_name": "Energy Potion",
                }
            ],
            "can_proceed": True,
        },
    }
    state = parse_state(stuck)
    first = router.decide(state, ctx)
    second = router.decide(state, ctx)
    for d in (first, second):
        assert not isinstance(d, Wait)
        assert d.action.payload() == {"action": "claim_reward", "index": 0}
    third = router.decide(state, ctx)
    assert not isinstance(third, Wait)
    assert third.action.payload() == {"action": "proceed"}


def _charselect_state(
    selected: str | None,
    busy: bool = False,
    confirm: bool = True,
    ascension: int | None = None,
    max_ascension: int | None = None,
):
    payload = {
        "state_type": "menu",
        "menu_screen": "character_select",
        "selected_character": selected,
        "selection_busy": busy,
        "options": [
            {"name": "IRONCLAD", "enabled": True},
            {"name": "SILENT", "enabled": True},
            {"name": "REGENT", "enabled": False},
            {"name": "confirm", "enabled": confirm},
            {"name": "embark", "enabled": confirm},
            {"name": "back", "enabled": True},
        ],
    }
    if ascension is not None:
        payload["ascension"] = ascension
    if max_ascension is not None:
        payload["max_ascension"] = max_ascension
    return parse_state(payload)


def test_charselect_waits_during_unlock_animation() -> None:
    """Found live: the unlock animation Select()s the new character ~1s after the
    screen opens, overwriting earlier picks. Fork exposes selection_busy."""
    decision = TrivialRouter().decide(_charselect_state(None, busy=True), LoopContext())
    assert isinstance(decision, Wait) and "unlock animation" in decision.reason


def test_charselect_reselects_until_verified_then_embarks() -> None:
    router = TrivialRouter()
    ctx = LoopContext(character="IRONCLAD")
    # screen holds the wrong character -> re-select, repeatedly if needed
    for _ in range(2):
        d = router.decide(_charselect_state("SILENT"), ctx)
        assert not isinstance(d, Wait)
        assert d.action.payload()["option"] == "IRONCLAD"
    # verified -> embark exactly once, then wait
    d = router.decide(_charselect_state("IRONCLAD"), ctx)
    assert not isinstance(d, Wait) and d.action.payload()["option"] == "confirm"
    d = router.decide(_charselect_state("IRONCLAD"), ctx)
    assert isinstance(d, Wait)


def test_charselect_verified_but_confirm_disabled_waits() -> None:
    d = TrivialRouter().decide(
        _charselect_state("IRONCLAD", confirm=False), LoopContext(character="IRONCLAD")
    )
    assert isinstance(d, Wait) and "confirm" in d.reason


def test_charselect_locked_request_surfaces_manual() -> None:
    d = TrivialRouter().decide(_charselect_state("IRONCLAD"), LoopContext(character="REGENT"))
    assert isinstance(d, Wait) and d.reason.startswith("MANUAL:")


def test_charselect_sets_ascension_before_embark() -> None:
    router = TrivialRouter()
    ctx = LoopContext(character="IRONCLAD", ascension=2)
    # verified character, wrong ascension -> set_ascension
    d = router.decide(_charselect_state("IRONCLAD", ascension=0, max_ascension=5), ctx)
    assert not isinstance(d, Wait)
    assert d.action.payload() == {"action": "set_ascension", "level": 2}
    # ascension now matches -> embark
    d = router.decide(_charselect_state("IRONCLAD", ascension=2, max_ascension=5), ctx)
    assert not isinstance(d, Wait)
    assert d.action.payload()["option"] == "confirm"


def test_charselect_locked_ascension_surfaces_manual() -> None:
    d = TrivialRouter().decide(
        _charselect_state("IRONCLAD", ascension=0, max_ascension=1),
        LoopContext(character="IRONCLAD", ascension=5),
    )
    assert isinstance(d, Wait) and d.reason.startswith("MANUAL:")


def test_ascension_zero_skips_set_ascension() -> None:
    d = TrivialRouter().decide(
        _charselect_state("IRONCLAD", ascension=0, max_ascension=5),
        LoopContext(character="IRONCLAD", ascension=0),
    )
    assert not isinstance(d, Wait)
    assert d.action.payload()["option"] == "confirm"


def test_requested_ascension_zero_overrides_a_remembered_level() -> None:
    """2026-09-28: the picker REMEMBERS the last level and climbs after wins;
    a requested A0 never overrode it (`if ctx.ascension and ...`), so three
    batches ran at A3..A8 unnoticed. A requested 0 must set 0."""
    d = TrivialRouter().decide(
        _charselect_state("IRONCLAD", ascension=6, max_ascension=8),
        LoopContext(character="IRONCLAD", ascension=0),
    )
    assert not isinstance(d, Wait)
    assert d.action.payload() == {"action": "set_ascension", "level": 0}


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


def test_treasure_waits_through_opening_transition() -> None:
    # The chest's transitional "Opening chest..." state -- can_proceed defaults True, so without a
    # guard the bot fires a premature proceed before the relic appears, racing the animation and
    # freezing the map node (War Paint on a ?-node, ZWSK88UNQN). Must WAIT till the message clears.
    router = TrivialRouter()

    def tstate(treasure):
        return parse_state({"state_type": "treasure",
                            "run": {"act": 1, "floor": 14, "ascension": 0},
                            "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80},
                            "treasure": treasure})

    opening = tstate({"message": "Opening chest...", "relics": []})
    assert isinstance(router.decide(opening, LoopContext()), Wait)  # do not act mid-open

    claimable = tstate({"relics": [{"index": 0, "id": "WAR_PAINT", "name": "War Paint"}]})
    ctx = LoopContext()
    claim = None
    for _ in range(5):  # settle-dwell polls precede the claim (black-screen fix)
        d = router.decide(claimable, ctx)
        if not isinstance(d, Wait):
            claim = d.action.payload()["action"]
            break
    assert claim == "claim_treasure_relic"

    done = tstate({"relics": [], "can_proceed": True})
    assert router.decide(done, LoopContext()).action.payload()["action"] == "proceed"


def test_three_identical_potion_rewards_all_claimed() -> None:
    """Owner catch 2026-08-03 (f20, 3x Foul Potion, empty belt): identical items
    hash to one attempts-key as indices shift to 0, so two SUCCESSFUL claims
    counted as attempts and the third was abandoned. Remaining-count in the key
    gives each success a fresh counter; true no-ops (list unchanged) still cap."""
    router = TrivialRouter()
    ctx = LoopContext()

    def rewards_state(n):
        return parse_state({
            "state_type": "rewards",
            "run": {"act": 2, "floor": 20, "ascension": 0},
            "player": {"character": "The Ironclad", "hp": 50, "max_hp": 75,
                       "status": [], "potions": [], "max_potion_slots": 3},
            "rewards": {"items": [
                {"index": i, "type": "potion", "description": "Foul Potion",
                 "potion_id": "FOUL_POTION", "potion_name": "Foul Potion"}
                for i in range(n)], "can_proceed": True},
        })

    for remaining in (3, 2, 1):  # each successful claim shrinks the list
        d = router.decide(rewards_state(remaining), ctx)
        assert d.action.payload() == {"action": "claim_reward", "index": 0}, remaining
    done = router.decide(rewards_state(0), ctx)
    assert done.action.payload() == {"action": "proceed"}
