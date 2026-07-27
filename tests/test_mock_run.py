"""End-to-end: trivial policy completes a full scripted run, with full logging."""

import json
import sqlite3
from pathlib import Path

from mock_game import FakeClient, build_doc_script

from sts2bot.orchestrator.loop import AgentLoop, LoopConfig
from sts2bot.policy.trivial import TrivialRouter

COMPENDIUM = {
    "profile_id": 2,
    "sections": {
        "run_history": {
            "status": "exposed",
            "entry_count": 1,
            "entries": [
                {
                    "id": "1",
                    "run_id": "modded:profile2:1",
                    "players": [{"id": 1, "character": "CHARACTER.IRONCLAD"}],
                    "ascension": 0,
                    "win": False,
                    "run_time": 1234,
                }
            ],
        }
    },
}


def run_scripted(tmp_path: Path):
    game = build_doc_script()
    client = FakeClient(game, compendium=COMPENDIUM)
    loop = AgentLoop(
        client=client,
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, character="IRONCLAD"),
    )
    return game, loop.play_one_run()


def test_full_scripted_run_completes(tmp_path: Path) -> None:
    game, outcome = run_scripted(tmp_path)

    assert game.current == "menu_end"
    assert outcome.status == "completed"
    assert outcome.victory is False  # from scripted compendium run history
    assert outcome.character == "The Ironclad"
    assert outcome.act == 2 and outcome.floor == 24  # from the game_over state
    assert outcome.decisions == 19
    # every scripted transition was exercised exactly once
    assert [s for s, _ in game.history][:4] == [
        "menu_main",
        "menu_sp",
        "char_select",
        "char_select_picked",
    ]
    assert len(game.history) == 19


def test_run_logs_written(tmp_path: Path) -> None:
    run_scripted(tmp_path)

    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    lines = (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    actions = [r for r in records if r["action"] is not None]
    assert len(actions) == 19
    assert all(r["result"]["status"] == "ok" for r in actions)
    assert all(r["rationale"] for r in records)
    # decision records carry the full state for replay (C6 / FR-5.3)
    combat_records = [r for r in actions if r["state_type"] == "monster"]
    assert combat_records and "player" in combat_records[0]["state"]
    assert actions[-1]["action"] == {"action": "menu_select", "option": "main_menu"}

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["outcome"]["status"] == "completed"
    assert meta["ended_at"] >= meta["started_at"]

    conn = sqlite3.connect(tmp_path / "index.sqlite")
    rows = conn.execute(
        "SELECT character, ascension, victory, decisions, status FROM runs"
    ).fetchall()
    conn.close()
    assert rows == [("The Ironclad", 0, 0, 19, "completed")]


def test_unexpected_action_errors_halt_the_loop(tmp_path: Path) -> None:
    game = build_doc_script()
    # Sabotage: remove the transition out of the rest site so every action errors.
    game.transitions["rest"] = []
    client = FakeClient(game, compendium=COMPENDIUM)
    loop = AgentLoop(
        client=client,
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, error_streak_limit=3),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "error"
    assert outcome.error is not None and "consecutive action errors" in outcome.error


def test_duplicate_submission_debounce(tmp_path: Path) -> None:
    """Regression (Owl Magistrate death 2026-07-13): an ACCEPTED action whose state
    hasn't applied yet must not be resubmitted every tick — a doubled play wedged an
    engine hook and broke a computed lethal. With the state frozen after ok-results,
    the loop holds duplicates (retrying only after duplicate_debounce_ticks) until the
    stall rail ends the run: a handful of accepted acts, not one per tick."""
    from mock_game import ScriptedGame, fixture

    game = ScriptedGame(
        states={"menu_main": fixture("menu_main")},
        transitions={"menu_main": [({}, "menu_main")]},  # accept anything, never change
        start="menu_main",
    )
    loop = AgentLoop(
        client=FakeClient(game, compendium=COMPENDIUM),
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stall_threshold=30,
                          duplicate_debounce_ticks=20),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "error" and "state unchanged" in (outcome.error or "")
    # without the debounce this is ~30 accepted duplicates; with it, the initial act
    # plus at most one post-debounce retry
    assert len(game.history) <= 3


def test_selection_actions_exempt_from_debounce(tmp_path: Path) -> None:
    """Regression (Cruelty forfeit 2026-07-16): a card_select choose the game hasn't
    applied yet must keep RESUBMITTING — selection-screen retry is the designed
    recovery path (Discovery/Toolbox 2026-07-14), and the debounce was starving it:
    the policy's retry budget burned on decides-without-submits, hit its cap in ~4s,
    and the cancel valve forfeited a Power-Potion Cruelty. Selection actions bypass
    the debounce; the stall rail remains the backstop."""
    from mock_game import ScriptedGame, fixture

    game = ScriptedGame(
        states={"card_select_transform": fixture("card_select_transform")},
        transitions={"card_select_transform": [({}, "card_select_transform")]},
        start="card_select_transform",
    )
    loop = AgentLoop(
        client=FakeClient(game, compendium=COMPENDIUM),
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stall_threshold=30,
                          duplicate_debounce_ticks=20),
    )
    loop.play_one_run()
    # selection submissions must NOT be held to <=3 like the debounced menu case
    assert len(game.history) > 3
    assert all((payload.get("action") or "").startswith(("select_", "confirm_", "cancel_"))
               for _state, payload in game.history)


def test_pause_for_resume_returns_when_signal_present(tmp_path: Path) -> None:
    """The resume mechanism: _pause_for_resume blocks until the signal file appears,
    then consumes it. With the signal already present it returns immediately."""
    sig = tmp_path / "resume.signal"
    sig.write_text("go", encoding="utf-8")
    loop = AgentLoop(
        client=FakeClient(build_doc_script()),
        router=TrivialRouter(),
        log_root=tmp_path,
        config=LoopConfig(poll_interval=0, resume_signal_path=sig),
    )
    loop._pause_for_resume(5)  # returns at once (signal present)
    assert not sig.exists()  # consumed


def test_fight_end_pause_ignores_in_combat_card_select() -> None:
    """Regression (live 2026-06-15): a potion's `card_select` modal mid-fight must
    NOT count as a fight end, or the loop hard-hangs in _pause_for_resume. The
    pause fires once, only when the fight reaches its `rewards` screen."""
    fight_end = AgentLoop._fight_end_pause
    fight_in_progress = False
    pauses = 0
    # one fight that pops a potion card-select mid-combat, then resolves to loot
    sequence = ["monster", "card_select", "monster", "rewards", "card_reward", "map"]
    for state_type in sequence:
        should_pause, fight_in_progress = fight_end(state_type, fight_in_progress)
        pauses += should_pause
    assert pauses == 1  # only at `rewards`, never at the mid-fight `card_select`


def test_observe_pause_fires_once_per_screen_entry() -> None:
    """Observation mode pauses once per *entry* into draft/shop/event screens, not every poll, and
    re-pauses on a fresh entry (owner request 2026-06-25: shop + Ancient-event pauses)."""
    observe = AgentLoop._observe_pause
    paused = None
    labels = []
    # draft (2 polls) -> map -> shop (2 polls) -> Ancient event -> back to combat -> event again
    sequence = ["card_reward", "card_reward", "map", "shop", "shop", "event", "monster", "event"]
    for state_type in sequence:
        label, paused = observe(state_type, paused)
        if label:
            labels.append(label)
    # one pause each: first draft poll, first shop poll, first event, and the re-entered event
    assert labels == ["at card draft", "at shop", "at event", "at event"]
def test_record_session_observes_and_logs(tmp_path: Path) -> None:
    """The `record` command logs a state trace per run for human-vs-bot comparison, and never
    acts. A human advances the game, so the fake advances on each poll (not on act)."""
    from sts2bot.orchestrator.recorder import record_session

    player = {"character": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
              "energy": 3, "max_energy": 3, "hand": [], "status": [], "relics": [],
              "potions": [], "max_potion_slots": 3}
    battle = {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []}
    run = {"act": 1, "floor": 1, "ascension": 0}
    seq = [
        {"state_type": "menu", "menu_screen": "main"},
        {"state_type": "monster", "run": run, "player": player, "battle": battle},
        {"state_type": "monster", "run": run, "player": {**player, "hp": 72}, "battle": battle},
        {"state_type": "menu", "menu_screen": "main"},
    ]

    class SeqClient:
        def __init__(self):
            self.i = 0

        def get_state_raw(self):
            s = seq[min(self.i, len(seq) - 1)]
            self.i += 1
            return s

        def act(self, action):
            raise AssertionError("the recorder must never act")

    n = record_session(
        SeqClient(), log_root=str(tmp_path), poll_interval=0, nav_poll_interval=0, runs=1
    )
    assert n == 1
    run_dir = next((tmp_path / "runs").iterdir())
    lines = (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert records  # the in-run states were captured
    assert all(r["action"] is None and r["rationale"] == "human play" for r in records)


def test_fight_end_pause_state_transitions() -> None:
    fight_end = AgentLoop._fight_end_pause
    assert fight_end("monster", False) == (False, True)  # enter combat -> armed
    assert fight_end("card_select", True) == (False, True)  # in-fight modal: no pause
    assert fight_end("rewards", True) == (True, False)  # fight over -> pause once
    assert fight_end("card_reward", False) == (False, False)  # already paused: no repeat
    assert fight_end("map", False) == (False, False)  # between fights: nothing


def test_stop_at_floor_hands_off_without_acting(tmp_path: Path) -> None:
    """`--stop-at-floor N` stops cleanly at the fight on floor N *without acting*, leaving the
    live game at the player's turn so a human can play it with the bot-built deck (the 2026-06-16
    Ovicopter/Obscura hypothesis test)."""
    player = {"character": "The Ironclad", "hp": 50, "max_hp": 80, "block": 0,
              "energy": 3, "max_energy": 3, "hand": [], "status": [], "relics": [],
              "potions": [], "max_potion_slots": 3}
    monster = {"state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
               "player": player,
               "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []}}

    class StuckClient:
        def get_state_raw(self):
            return monster

        def act(self, action):
            raise AssertionError("the bot must not act once stop_at_floor is reached")

    loop = AgentLoop(
        StuckClient(), TrivialRouter(), log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stop_at_floor=22),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "stopped"  # handed off, did not flail or finish
    assert outcome.floor == 22


def test_stop_at_floor_follow_records_human_half(tmp_path: Path) -> None:
    """The tactical A/B instrument (2026-07-24): after the handoff, the loop keeps
    polling (never acting) and logs the human's play into the SAME run log until the
    run returns to a menu — bot half + human half in one decisions.jsonl."""
    player = {"character": "The Ironclad", "hp": 50, "max_hp": 80, "block": 0,
              "energy": 3, "max_energy": 3, "hand": [], "status": [], "relics": [],
              "potions": [], "max_potion_slots": 3}
    fight = {"state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
             "player": player,
             "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []}}
    fight_r3 = json.loads(json.dumps(fight))
    fight_r3["battle"]["round"] = 3
    fight_r3["player"]["hp"] = 31
    menu = {"state_type": "menu", "message": "Main menu.", "menu_screen": "main",
            "options": ["singleplayer", "quit"]}
    seq = [fight, fight_r3, menu]

    class SeqClient:
        def __init__(self):
            self.i = 0

        def get_state_raw(self):
            s = seq[min(self.i, len(seq) - 1)]
            self.i += 1
            return s

        def act(self, action):
            raise AssertionError("the bot must never act during a handoff follow")

    loop = AgentLoop(
        SeqClient(), TrivialRouter(), log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stop_at_floor=22, handoff_follow=True,
                          handoff_nav_poll_interval=0),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "stopped"
    run_dir = next((tmp_path / "runs").iterdir())
    lines = (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    human = [json.loads(x) for x in lines
             if json.loads(x).get("rationale") == "human play (handoff)"]
    assert len(human) >= 2  # the fight state at handoff + the human's round-3 state
    assert all(r["action"] is None for r in human)


def test_stop_on_map_hands_off_at_the_map_screen(tmp_path: Path) -> None:
    """Act-2 elite A/B mode: the bot's own gate never routes into an act-2 elite, so
    --stop-at-map hands off at the MAP screen — the human picks the door too."""
    map_state = {"state_type": "map", "run": {"act": 2, "floor": 18, "ascension": 0},
                 "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                            "status": [], "relics": [], "potions": [],
                            "max_potion_slots": 3},
                 "map": {"next_options": [
                     {"index": 0, "col": 1, "row": 1, "type": "Monster", "leads_to": []},
                     {"index": 1, "col": 2, "row": 1, "type": "Elite", "leads_to": []},
                 ]}}

    class StuckClient:
        def get_state_raw(self):
            return map_state

        def act(self, action):
            raise AssertionError("must not act: map handoff leaves the door choice human")

    outcome = AgentLoop(
        StuckClient(), TrivialRouter(), log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stop_at_floor=18, stop_on_map=True),
    ).play_one_run()
    assert outcome.status == "stopped"
    assert outcome.floor == 18


def test_stop_at_floor_resets_time_scale_for_the_human(tmp_path: Path) -> None:
    """Batches run at 4x; the handoff must hand the owner a playable 1x game
    (the owner has had to ask for speed resets twice — automate it)."""
    player = {"character": "The Ironclad", "hp": 50, "max_hp": 80, "block": 0,
              "energy": 3, "max_energy": 3, "hand": [], "status": [], "relics": [],
              "potions": [], "max_potion_slots": 3}
    fight = {"state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
             "player": player,
             "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []}}

    class ScaleClient:
        def __init__(self):
            self.scales = []

        def get_state_raw(self):
            return fight

        def act(self, action):
            payload = action.payload()
            assert payload.get("action") == "set_time_scale", (
                f"only speed resets allowed at handoff, got {payload}")
            self.scales.append(payload.get("scale"))

            class R:
                ok = True
                detail = "ok"

                def model_dump(self, **kw):
                    return {"ok": True}

            return R()

    client = ScaleClient()
    loop = AgentLoop(
        client, TrivialRouter(), log_root=tmp_path,
        config=LoopConfig(poll_interval=0, stop_at_floor=22, time_scale=4.0),
    )
    outcome = loop.play_one_run()
    assert outcome.status == "stopped"
    assert client.scales[-1] == 1.0  # last speed action hands back a 1x game


def test_loop_retries_transient_malformed_state(tmp_path: Path) -> None:
    """A transient mod error-object (no state_type) mid event-transition — the live
    'Failed to read GardenerResponse' that halted a late-Act-2 run at the fake merchant — is
    re-polled, not treated as fatal; the loop recovers to the next clean state. If it persists
    past the retry budget it still fails safe."""
    monster = {"state_type": "monster", "run": {"act": 2, "floor": 22, "ascension": 0},
               "player": {"character": "The Ironclad", "hp": 50, "max_hp": 80, "block": 0,
                          "energy": 3, "max_energy": 3, "hand": [], "status": [], "relics": [],
                          "potions": [], "max_potion_slots": 3},
               "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []}}
    transient = {"error": "Failed to read GardenerResponse response"}  # no state_type
    seq = [transient, transient, transient, monster]

    class FlakyClient:
        def __init__(self):
            self.i = 0

        def get_state_raw(self):
            s = seq[min(self.i, len(seq) - 1)]
            self.i += 1
            return s

        def act(self, action):
            raise AssertionError("must not act: recovers to a stop_at_floor handoff")

    # 5 retries clears the 3 transient errors -> reaches the floor-22 monster -> clean stop
    recovered = AgentLoop(
        FlakyClient(), TrivialRouter(), log_root=tmp_path / "ok",
        config=LoopConfig(poll_interval=0, stop_at_floor=22, malformed_state_retries=5),
    ).play_one_run()
    assert recovered.status == "stopped"

    # too few retries -> the transient run of errors outlasts the budget -> fail safe
    failed = AgentLoop(
        FlakyClient(), TrivialRouter(), log_root=tmp_path / "fail",
        config=LoopConfig(poll_interval=0, stop_at_floor=22, malformed_state_retries=2),
    ).play_one_run()
    assert failed.status == "error"


def test_foul_thrown_blind_in_the_shopkeeper_window(tmp_path: Path) -> None:
    """Probe-proven 2026-07-25: the Foul merchant-throw only works on the SHOPKEEPER
    screen, which /state polling auto-advances past. The loop must fire the throw
    BLIND between the accepted shop travel and the next state poll."""
    map_state = {"state_type": "map", "run": {"act": 1, "floor": 5, "ascension": 0},
                 "player": {"character": "The Ironclad", "hp": 60, "max_hp": 80,
                            "status": [], "relics": [],
                            "potions": [{"id": "FOUL_POTION", "name": "Foul Potion",
                                         "description": "Deal 10 damage to EVERYONE.",
                                         "slot": 2, "can_use_in_combat": True,
                                         "target_type": "None", "keywords": []}],
                            "max_potion_slots": 3},
                 "map": {"next_options": [
                     {"index": 0, "col": 1, "row": 5, "type": "Shop", "leads_to": []},
                 ]}}

    class SeqClient:
        def __init__(self):
            self.events = []

        def get_state_raw(self):
            self.events.append("poll")
            return map_state

        def act(self, action):
            self.events.append(action.payload().get("action"))

            class R:
                ok = True
                detail = "ok"

                def model_dump(self, **kw):
                    return {"ok": True}

            return R()

    client = SeqClient()
    loop = AgentLoop(client, TrivialRouter(), log_root=tmp_path,
                     config=LoopConfig(poll_interval=0, max_decisions=1))
    loop.play_one_run()
    # the throw must come immediately after the travel, BEFORE any further poll
    i = client.events.index("choose_map_node")
    assert client.events[i + 1] == "use_potion", client.events
    assert "poll" not in client.events[i:i + 2], client.events
