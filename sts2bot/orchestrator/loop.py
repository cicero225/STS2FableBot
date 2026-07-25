"""Agent loop: poll state -> decide -> act -> log, with stall/error safety rails.

One `play_one_run()` call drives: main menu -> start run -> play to game over ->
dismiss -> back at main menu. Crash recovery across game relaunches is P2; here we
fail safe (finalize logs, raise) rather than flail (REQUIREMENTS C5).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from sts2bot.client.actions import Action
from sts2bot.client.http import ActionResult
from sts2bot.client.models import (
    GameOverState,
    GameState,
    MenuState,
    StateParseError,
    parse_state,
)
from sts2bot.policy.base import LoopContext, PolicyRouter, Wait
from sts2bot.runlog.index import RunIndex
from sts2bot.runlog.logger import RunLogger, RunOutcome, _now_iso

# Screens where the player is actively fighting. In-combat modals (e.g.
# `card_select` from potions / Discovery effects) are deliberately NOT here:
# the policy resolves them, and treating them as "fight over" hard-hung the
# pause-after-fight loop (observed live 2026-06-15 on a Skill/colorless potion).
_COMBAT_STATES = ("monster", "elite", "boss", "hand_select")
# Screens that mark a fight as genuinely finished (loot). Across 47 logged runs,
# a won fight transitions combat -> `rewards`; `card_select` also follows combat
# but is an in-fight modal, so it must never count as a fight end.
_POST_FIGHT_STATES = ("rewards", "card_reward")

# Observation mode pauses once per entry into each of these decision screens so the owner can audit
# the choice on-screen before the bot commits (the fight-end pause only covers the rewards screen).
# Ancient rooms surface as `event` (owner request 2026-06-25, alongside the shop pause).
_OBSERVE_PAUSE_LABELS = {"card_reward": "at card draft", "shop": "at shop", "event": "at event"}


class GameClient(Protocol):
    """What the loop needs from a client (real Sts2Client or a test fake)."""

    def get_state_raw(self) -> dict[str, Any]: ...
    def act(self, action: Action) -> ActionResult: ...


# Selection-overlay actions whose resubmission is the designed retry path — never
# debounced (see the debounce block in run(); Cruelty forfeit 2026-07-16).
_DEBOUNCE_EXEMPT = frozenset({
    "select_card", "confirm_selection", "cancel_selection",
    "select_bundle", "confirm_bundle_selection", "cancel_bundle_selection",
    "select_relic",
})


class LoopConfig(BaseModel):
    poll_interval: float = 0.5
    stall_threshold: int = 60  # consecutive unchanged-state ticks before giving up
    # Duplicate-submission debounce: after an ACCEPTED action, an unchanged state means
    # the game hasn't applied it yet — resubmitting the identical action can wedge an
    # engine hook (Owl Magistrate death 2026-07-13: a doubled Stampede+ play locked the
    # hand as BlockedByHook for the rest of the turn and broke a computed lethal). Hold
    # identical resubmits this many ticks; after that, one retry is allowed as a last
    # resort (the 60-tick stall rail remains the backstop).
    duplicate_debounce_ticks: int = 20
    manual_stall_threshold: int = 600  # generous rail while waiting on owner (MANUAL waits)
    error_streak_limit: int = 8  # consecutive rejected actions before giving up
    # the mod can briefly return an error-object (no state_type) mid event-transition (seen:
    # 'Failed to read GardenerResponse' rolling into the fake merchant); re-poll this many times
    # before treating an unparseable state as fatal — the next read is clean.
    malformed_state_retries: int = 5
    max_decisions: int = 3000  # hard safety cap per run
    character: str = "IRONCLAD"
    ascension: int = 0
    profile_id: int | None = None
    # game save history dirs for authoritative outcome records ([] = skip)
    history_dirs: list[Path] = []
    # attribution (FR-3.4): which policy + config produced this run
    policy_name: str = "trivial"
    config_hash: str | None = None
    # engine speed: re-asserted periodically because game cinematics reset
    # Engine.TimeScale to 1.0 (observed live at the Act 1 boss)
    time_scale: float | None = None
    time_scale_reassert_every: int = 25  # decisions
    # per-run modded-profile backup (C1; Steam Cloud reshuffled profiles once).
    # None disables; set a dir to snapshot the active profile after each run.
    profile_backup_root: Path | None = None
    profile_backup_keep: int = 50
    # observation mode: pause after each fight until resume_signal_path appears
    pause_after_fight: bool = False
    resume_signal_path: Path | None = None
    # one-shot manual takeover: stop cleanly (without acting) when a fight begins at
    # this floor, leaving the live game at the player's turn for a human to play it out
    stop_at_floor: int | None = None
    # stop_at_floor triggers on FIGHTS by default; stop_on_map hands off at the MAP
    # screen instead once floor >= stop_at_floor — for A/Bs where the human should
    # choose the door too (act-2 elite handoff: the bot's own gate would never
    # route into the elite, so the navigation is part of the human's half).
    stop_on_map: bool = False
    # After a stop_at_floor handoff: keep polling (NEVER acting) and log the human's
    # play into the SAME run log until the run ends — bot half and human half land in
    # one decisions.jsonl for turn-by-turn A/B diffing. Off by default so handoff
    # tests with stuck mock clients don't spin; the CLI turns it on with stop_at_floor.
    handoff_follow: bool = False
    # Post-handoff nav-screen poll cadence (recorder lesson: the mod's /state read
    # re-renders the screen and can fight a human's click, so poll non-combat slowly).
    handoff_nav_poll_interval: float = 4.0


class BotStalled(Exception):
    pass


def _fingerprint(raw: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()




class AgentLoop:
    def __init__(
        self,
        client: GameClient,
        router: PolicyRouter,
        log_root: Path | str = "logs",
        config: LoopConfig | None = None,
    ):
        self.client = client
        self.router = router
        self.log_root = Path(log_root)
        self.config = config or LoopConfig()

    # ------------------------------------------------------------------ run loop

    def play_one_run(self) -> RunOutcome:
        cfg = self.config
        ctx = LoopContext(
            character=cfg.character, ascension=cfg.ascension, profile_id=cfg.profile_id
        )
        logger = RunLogger(
            self.log_root,
            character_hint=cfg.character,
            header={"policy": cfg.policy_name, "config_hash": cfg.config_hash},
        )
        index = RunIndex(self.log_root / "index.sqlite")
        run_id = index.start_run(
            str(logger.run_dir),
            logger.started_at,
            policy=cfg.policy_name,
            config_hash=cfg.config_hash,
        )
        outcome = RunOutcome(ascension=None)
        record_watermark = 0.0
        if cfg.history_dirs:
            from sts2bot.runlog.runfile import newest_record_mtime

            record_watermark = newest_record_mtime(cfg.history_dirs)

        last_fp: str | None = None
        stall = 0
        error_streak = 0
        last_act_fp: str | None = None  # fingerprint of the state the last accepted action saw
        last_act_payload: dict | None = None
        dup_hold = 0
        phase = "to_run"  # -> "post_over" -> done
        last_wait_reason: str | None = None
        manual_announced = False
        fight_in_progress = False
        paused_screen: str | None = None  # observation mode: screen we've already paused on
        handoff_run_ended = False  # stop_at_floor follow saw the human finish the run
        if cfg.pause_after_fight and cfg.resume_signal_path:
            Path(cfg.resume_signal_path).unlink(missing_ok=True)  # clear stale
        self._assert_time_scale()

        try:
            while True:
                raw = self.client.get_state_raw()
                parse_tries = 0
                while True:
                    try:
                        state = parse_state(raw)
                        break
                    except StateParseError:
                        # transient mod error-object (no state_type) during an event transition;
                        # re-poll a few times before failing safe — the next read is usually clean.
                        parse_tries += 1
                        if parse_tries > cfg.malformed_state_retries:
                            raise
                        time.sleep(cfg.poll_interval)
                        raw = self.client.get_state_raw()

                fp = _fingerprint(raw)
                stall = stall + 1 if fp == last_fp else 0
                last_fp = fp
                waiting_on_owner = bool(last_wait_reason) and str(last_wait_reason).startswith(
                    "MANUAL:"
                )
                limit = cfg.manual_stall_threshold if waiting_on_owner else cfg.stall_threshold
                if stall >= limit:
                    detail = f"; last wait reason: {last_wait_reason}" if last_wait_reason else ""
                    raise BotStalled(
                        f"state unchanged for {stall} ticks (state_type="
                        f"{state.state_type}, phase={phase}){detail}"
                    )

                self._track_progress(state, ctx, outcome)


                # One-shot manual takeover: stop (without acting) at the fight on the
                # target floor so a human can play it out with the bot-built deck.
                if (
                    cfg.stop_at_floor is not None
                    and state.run is not None
                    and state.run.floor is not None
                    and state.run.floor >= cfg.stop_at_floor
                    and state.state_type
                    in (("map",) if cfg.stop_on_map else ("monster", "elite", "boss"))
                ):
                    outcome.status = "stopped"
                    if cfg.time_scale not in (None, 1.0):
                        # batches run at 4x; hand the owner a playable game
                        try:
                            from sts2bot.client.actions import SetTimeScale

                            self.client.act(SetTimeScale(scale=1.0))
                            print("time scale reset to 1x for manual play", flush=True)
                        except Exception:
                            print("WARNING: could not reset time scale — "
                                  "run `sts2bot speed 1` if the game is fast", flush=True)
                    print(
                        f"\n*** STOPPING at floor {state.run.floor} ({state.state_type}) for "
                        "manual takeover — play it out, the bot will NOT act. ***",
                        flush=True,
                    )
                    # the fight's opening position is the A/B baseline — keep it
                    logger.log_decision(raw, None, "human play (handoff)", None)
                    if cfg.handoff_follow:
                        handoff_run_ended = self._follow_human_play(logger, cfg, last_fp=fp)
                    break

                # Pause-after-fight (observation mode): hold only when a fight
                # genuinely ends at its reward screen. In-combat modals like
                # `card_select` (potion / Discovery card offers) briefly leave the
                # combat states; pausing on those falsely read as "fight over" and
                # hung the loop here (live 2026-06-15, Skill/colorless potions).
                should_pause, fight_in_progress = self._fight_end_pause(
                    state.state_type, fight_in_progress
                )
                if cfg.pause_after_fight and should_pause:
                    self._pause_for_resume(outcome.floor)
                # Observation mode: also pause once per entry into the draft / shop / Ancient-event
                # screens (the fight-end pause only fires on the rewards screen, so these fly by).
                pause_label, paused_screen = self._observe_pause(state.state_type, paused_screen)
                if cfg.pause_after_fight and pause_label:
                    self._pause_for_resume(outcome.floor, label=pause_label)

                if isinstance(state, GameOverState) and phase != "post_over":
                    phase = "post_over"
                    outcome.game_over_message = state.game_over.message
                if (
                    phase == "post_over"
                    and isinstance(state, MenuState)
                    and (state.menu_screen or "main") == "main"
                ):
                    outcome.status = "completed"
                    break

                decision = self.router.decide(state, ctx)
                if isinstance(decision, Wait):
                    last_wait_reason = decision.reason
                    if decision.reason.startswith("MANUAL:") and not manual_announced:
                        manual_announced = True
                        print(f"\n*** ATTENTION NEEDED *** {decision.reason}\n", flush=True)
                    if stall % 10 == 0:  # don't spam the log during animations
                        logger.log_decision(
                            {"state_type": state.state_type},
                            None,
                            f"wait: {decision.reason}",
                            None,
                        )
                    time.sleep(cfg.poll_interval)
                    continue

                # Debounce: same state we already acted on + same action = the game is
                # still applying the last submission; hammering it can wedge a hook.
                # EXEMPT selection-screen actions: their retry-on-unchanged-screen IS
                # the designed recovery mechanism (Discovery/Toolbox fix 2026-07-14),
                # and no engine-hook wedge class exists for UI overlays. Holding them
                # starved the policy's retry budget on decides-without-submits and
                # forfeited a Power-Potion Cruelty at the choose screen (2026-07-16).
                payload = decision.action.payload()
                if (
                    fp == last_act_fp
                    and payload == last_act_payload
                    and payload.get("action") not in _DEBOUNCE_EXEMPT
                    and dup_hold < cfg.duplicate_debounce_ticks
                ):
                    dup_hold += 1
                    if dup_hold % 10 == 1:
                        logger.log_decision(
                            {"state_type": state.state_type}, None,
                            f"debounce: holding duplicate {payload.get('action')} "
                            f"(tick {dup_hold}); state unchanged since last accept",
                            None,
                        )
                    time.sleep(cfg.poll_interval)
                    continue

                result = self.client.act(decision.action)
                ctx.decisions += 1
                if ctx.decisions % self.config.time_scale_reassert_every == 0:
                    self._assert_time_scale()
                logger.log_decision(
                    raw,
                    decision.action.payload(),
                    decision.rationale,
                    result.model_dump(exclude_none=True),
                    decision.scores,
                )
                if result.ok:
                    error_streak = 0
                    last_act_fp, last_act_payload, dup_hold = fp, payload, 0
                elif (
                    "actions are currently disabled" in result.detail
                    or "already queued" in result.detail
                ):
                    # transient in-game queuing/lockout states (scripted moments,
                    # potion effects resolving); wait them out, not streak-worthy
                    time.sleep(cfg.poll_interval)
                else:
                    error_streak += 1
                if error_streak >= cfg.error_streak_limit:
                    raise BotStalled(
                        f"{error_streak} consecutive action errors; last: {result.detail}"
                    )
                if ctx.decisions >= cfg.max_decisions:
                    outcome.status = "aborted"
                    outcome.error = f"max_decisions cap {cfg.max_decisions} reached"
                    break
                time.sleep(cfg.poll_interval)

        except KeyboardInterrupt:
            outcome.status = "aborted"
            outcome.error = "interrupted by user"
            raise
        except (BotStalled, StateParseError) as e:
            outcome.status = "error"
            outcome.error = str(e)
            if isinstance(e, StateParseError) and e.raw is not None:
                # Keep the offending payload for diagnosis/fixtures (C5: clear report).
                (logger.run_dir / "parse_error.json").write_text(
                    json.dumps(e.raw, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as e:  # connection loss, unexpected bugs: fail safe, keep logs
            outcome.status = "error"
            outcome.error = f"{type(e).__name__}: {e}"
        finally:
            outcome.decisions = ctx.decisions
            # Enrich even on errored loops: the run may have genuinely ended (e.g.
            # run 16 died to the Ovicopter, then the loop railed on its death
            # sequence) and the game's .run record is still authoritative.
            # A finished handoff run races the game's .run write the same way the
            # recorder did (A/B #4: clean WIN recorded as all-null) — retry briefly.
            self._enrich_from_run_record(
                outcome, record_watermark, retries=10 if handoff_run_ended else 0
            )
            if outcome.status == "completed" and outcome.victory is None:
                outcome.victory = self._resolve_victory(outcome)
            logger.finalize(outcome)
            index.finish_run(run_id, _now_iso(), outcome)
            index.close()
            if cfg.profile_backup_root is not None and cfg.history_dirs:
                from sts2bot.runlog.saves import backup_active_profile

                backup_active_profile(
                    cfg.history_dirs, cfg.profile_backup_root, cfg.profile_backup_keep
                )

        return outcome

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _fight_end_pause(state_type: str, fight_in_progress: bool) -> tuple[bool, bool]:
        """Detect a genuine end-of-fight for observation-mode pausing.

        Returns ``(should_pause, fight_in_progress_next)``. A fight is "in
        progress" from its first combat screen until it resolves to a reward
        screen. In-combat modals (`card_select` from potions / Discovery, etc.)
        leave the combat state_type briefly but keep the fight in progress, so
        they never trip the pause — which previously hard-hung the loop in
        ``_pause_for_resume`` (observed live 2026-06-15 on a Skill/colorless
        potion's card offer).
        """
        if state_type in _COMBAT_STATES:
            return False, True
        if fight_in_progress and state_type in _POST_FIGHT_STATES:
            return True, False
        return False, fight_in_progress

    @staticmethod
    def _observe_pause(
        state_type: str, paused_screen: str | None
    ) -> tuple[str | None, str | None]:
        """Observation mode: pause once per *entry* into a draft / shop / Ancient-event screen.

        Returns ``(label_or_None, paused_screen_next)``. ``label`` is set only on the first poll
        after entering a pausable screen (the caller pauses with it). ``paused_screen`` latches the
        screen we paused on so repeated polls don't re-pause; it clears once we leave the pausable
        screens, so a later entry pauses again.
        """
        label = _OBSERVE_PAUSE_LABELS.get(state_type)
        if label is None:
            return None, None
        if paused_screen == state_type:
            return None, paused_screen  # already paused on this entry
        return label, state_type

    def _pause_for_resume(self, floor: int | None, label: str = "after fight") -> None:
        """Block until the resume signal file appears (owner says 'go'), then clear it."""
        sig = self.config.resume_signal_path
        if sig is None:
            return
        sig_path = Path(sig)
        print(
            f"\n*** PAUSED {label} (floor {floor}) — say 'go' to continue ***",
            flush=True,
        )
        while not sig_path.exists():
            time.sleep(1.0)
        sig_path.unlink(missing_ok=True)
        print("*** resumed ***", flush=True)

    def _follow_human_play(
        self, logger: RunLogger, cfg: LoopConfig, last_fp: str | None = None
    ) -> bool:
        """Post-handoff passive follow: log the human's play (never acting) into the
        same run log until play returns to a menu, so the bot half and the human half
        of a tactical A/B land in ONE decisions.jsonl. Returns True if the run
        genuinely ended (menu reached); False on Ctrl+C. Combat polls fast; nav
        screens slowly (the mod's /state read re-renders and can fight human clicks).
        `last_fp` seeds dedupe with the already-logged handoff state."""
        was_in_run = False
        print("following: human play is being recorded into this run's log "
              "(Ctrl+C to stop early).", flush=True)
        try:
            while True:
                try:
                    raw = self.client.get_state_raw()
                    state = parse_state(raw)
                except StateParseError:
                    time.sleep(cfg.poll_interval)
                    continue
                if was_in_run and isinstance(state, MenuState):
                    print("run ended; handoff log finalized.", flush=True)
                    return True
                was_in_run = was_in_run or (
                    state.run is not None and not isinstance(state, MenuState)
                )
                fp = _fingerprint(raw)
                if fp != last_fp:
                    logger.log_decision(raw, None, "human play (handoff)", None)
                last_fp = fp
                combat = state.state_type in _COMBAT_STATES
                time.sleep(
                    cfg.poll_interval if combat else cfg.handoff_nav_poll_interval
                )
        except KeyboardInterrupt:
            print("\nhandoff follow interrupted; finalizing run log.", flush=True)
            return False

    def _assert_time_scale(self) -> None:
        """Re-apply the configured engine speed; cinematics reset it to 1.0."""
        if self.config.time_scale is None:
            return
        try:
            from sts2bot.client.actions import SetTimeScale

            self.client.act(SetTimeScale(scale=self.config.time_scale))
        except Exception:
            pass

    def _track_progress(self, state: GameState, ctx: LoopContext, outcome: RunOutcome) -> None:
        if state.run is not None:
            ctx.run_started = True
            outcome.act = state.run.act
            outcome.floor = state.run.floor
            outcome.ascension = state.run.ascension
        if state.player is not None:
            outcome.character = state.player.character

    def _enrich_from_run_record(
        self, outcome: RunOutcome, record_watermark: float, retries: int = 0
    ) -> None:
        """Pull the authoritative outcome from the game's own .run history record
        (win flag, seed, build_id, killed_by) — only records written AFTER this
        loop started (strict watermark; grace matching once cross-attributed).
        `retries` waits out the game's own write schedule (1s apart) when the run
        is known to have just ended, e.g. a finished stop_at_floor handoff."""
        if not self.config.history_dirs:
            return
        from sts2bot.runlog.runfile import latest_run_summary

        record = latest_run_summary(self.config.history_dirs, newer_than_mtime=record_watermark)
        for _ in range(retries):
            if record is not None:
                break
            time.sleep(1.0)
            record = latest_run_summary(
                self.config.history_dirs, newer_than_mtime=record_watermark
            )
        if record is None:
            return
        outcome.victory = record.win
        outcome.seed = record.seed
        outcome.build_id = record.build_id
        outcome.killed_by_encounter = record.killed_by_encounter
        outcome.killed_by_event = record.killed_by_event
        outcome.was_abandoned = record.was_abandoned
        if record.ascension is not None:
            outcome.ascension = record.ascension

    def _resolve_victory(self, outcome: RunOutcome) -> bool | None:
        """Fallback win detection when no .run record was found: profile run history
        via the API, then scanning the game-over message."""
        get_compendium = getattr(self.client, "get_compendium", None)
        if get_compendium is not None:
            try:
                compendium = get_compendium()
                entries = compendium.get("sections", {}).get("run_history", {}).get("entries", [])
                if entries:
                    win = entries[0].get("win")
                    if isinstance(win, bool):
                        return win
            except Exception:
                pass
        msg = (outcome.game_over_message or "").lower()
        if "victor" in msg or "you win" in msg:
            return True
        if "defeat" in msg or "died" in msg or "you lose" in msg:
            return False
        return None
