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


class GameClient(Protocol):
    """What the loop needs from a client (real Sts2Client or a test fake)."""

    def get_state_raw(self) -> dict[str, Any]: ...
    def act(self, action: Action) -> ActionResult: ...


class LoopConfig(BaseModel):
    poll_interval: float = 0.5
    stall_threshold: int = 60  # consecutive unchanged-state ticks before giving up
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
        phase = "to_run"  # -> "post_over" -> done
        last_wait_reason: str | None = None
        manual_announced = False
        fight_in_progress = False
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
                    and state.state_type in ("monster", "elite", "boss")
                ):
                    outcome.status = "stopped"
                    print(
                        f"\n*** STOPPING at floor {state.run.floor} ({state.state_type}) for "
                        "manual takeover — play it out, the bot will NOT act. ***",
                        flush=True,
                    )
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
            self._enrich_from_run_record(outcome, record_watermark)
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

    def _pause_for_resume(self, floor: int | None) -> None:
        """Block until the resume signal file appears (owner says 'go'), then clear it."""
        sig = self.config.resume_signal_path
        if sig is None:
            return
        sig_path = Path(sig)
        print(
            f"\n*** PAUSED after fight (floor {floor}) — say 'go' to continue ***",
            flush=True,
        )
        while not sig_path.exists():
            time.sleep(1.0)
        sig_path.unlink(missing_ok=True)
        print("*** resumed ***", flush=True)

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

    def _enrich_from_run_record(self, outcome: RunOutcome, record_watermark: float) -> None:
        """Pull the authoritative outcome from the game's own .run history record
        (win flag, seed, build_id, killed_by) — only records written AFTER this
        loop started (strict watermark; grace matching once cross-attributed)."""
        if not self.config.history_dirs:
            return
        from sts2bot.runlog.runfile import latest_run_summary

        record = latest_run_summary(self.config.history_dirs, newer_than_mtime=record_watermark)
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
