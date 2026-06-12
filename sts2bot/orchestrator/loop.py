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


class GameClient(Protocol):
    """What the loop needs from a client (real Sts2Client or a test fake)."""

    def get_state_raw(self) -> dict[str, Any]: ...
    def act(self, action: Action) -> ActionResult: ...


class LoopConfig(BaseModel):
    poll_interval: float = 0.5
    stall_threshold: int = 60  # consecutive unchanged-state ticks before giving up
    manual_stall_threshold: int = 600  # generous rail while waiting on owner (MANUAL waits)
    error_streak_limit: int = 8  # consecutive rejected actions before giving up
    max_decisions: int = 3000  # hard safety cap per run
    character: str = "IRONCLAD"
    ascension: int = 0
    profile_id: int | None = None
    # game save history dirs for authoritative outcome records ([] = skip)
    history_dirs: list[Path] = []


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
        logger = RunLogger(self.log_root, character_hint=cfg.character)
        index = RunIndex(self.log_root / "index.sqlite")
        run_id = index.start_run(str(logger.run_dir), logger.started_at)
        outcome = RunOutcome(ascension=None)
        loop_start_epoch = time.time()

        last_fp: str | None = None
        stall = 0
        error_streak = 0
        phase = "to_run"  # -> "post_over" -> done
        last_wait_reason: str | None = None
        manual_announced = False

        try:
            while True:
                raw = self.client.get_state_raw()
                state = parse_state(raw)

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
                logger.log_decision(
                    raw,
                    decision.action.payload(),
                    decision.rationale,
                    result.model_dump(exclude_none=True),
                    decision.scores,
                )
                error_streak = 0 if result.ok else error_streak + 1
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
            if outcome.status == "completed":
                self._enrich_from_run_record(outcome, loop_start_epoch)
                if outcome.victory is None:
                    outcome.victory = self._resolve_victory(outcome)
            logger.finalize(outcome)
            index.finish_run(run_id, _now_iso(), outcome)
            index.close()

        return outcome

    # ------------------------------------------------------------------ helpers

    def _track_progress(self, state: GameState, ctx: LoopContext, outcome: RunOutcome) -> None:
        if state.run is not None:
            ctx.run_started = True
            outcome.act = state.run.act
            outcome.floor = state.run.floor
            outcome.ascension = state.run.ascension
        if state.player is not None:
            outcome.character = state.player.character

    def _enrich_from_run_record(self, outcome: RunOutcome, since_epoch: float) -> None:
        """Pull the authoritative outcome from the game's own .run history record
        (win flag, seed, build_id, killed_by) — verified live in P0.7."""
        if not self.config.history_dirs:
            return
        from sts2bot.runlog.runfile import latest_run_summary

        record = latest_run_summary(self.config.history_dirs, since_epoch=since_epoch)
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
