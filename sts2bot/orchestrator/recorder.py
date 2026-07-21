"""Record a human-played session: poll game state, log every change, segment by run.

Pure observation — the bot does NOT decide or act. Two uses: (1) human-vs-bot
comparison (same log format as the agent loop, so the same analysis scripts read it);
(2) let the owner play toward the Act-3 wins that unlock custom (seeded) mode. Each run
is written to its own dir under log_root and finalized (with seed/outcome from the game's
.run record) when play returns to a menu.
"""

from __future__ import annotations

import time

from sts2bot.client.models import MenuState, parse_state
from sts2bot.orchestrator.loop import GameClient, _fingerprint
from sts2bot.runlog.logger import RunLogger, RunOutcome

_COMBAT_SCREENS = ("monster", "elite", "boss", "hand_select")


def record_session(
    client: GameClient,
    log_root: str = "logs/manual",
    history_dirs: list | None = None,
    poll_interval: float = 0.5,
    nav_poll_interval: float = 4.0,
    runs: int | None = None,
) -> int:
    """Block, recording human play, until `runs` runs are captured (None = until interrupted).
    Returns the number of runs recorded.

    The mod re-renders the current screen on each `/state` read, which fights a human's in-game
    "leave"/select click (the bot never hits this — it acts via the API, not clicks). So we poll
    combat fast (to capture card plays) but non-combat screens slowly (`nav_poll_interval`) to
    leave the owner room to navigate shops/maps/rewards. Not a full fix (an unlucky poll can
    still interrupt) — the real fix is making the mod's state read passive."""
    history_dirs = history_dirs or []
    from sts2bot.runlog.runfile import latest_run_summary, newest_record_mtime

    watermark = newest_record_mtime(history_dirs) if history_dirs else 0.0
    logger: RunLogger | None = None
    last_fp: str | None = None
    was_in_run = False
    recorded = 0

    def finalize(lg: RunLogger) -> None:
        nonlocal watermark
        outcome = RunOutcome(status="completed")
        if history_dirs:
            # The game writes its .run record on its own schedule; finalize fires the
            # INSTANT play returns to menu, and losing that race nulls the whole
            # outcome (A/B #4, 2026-07-18: a clean WIN recorded as all-null while the
            # owner was already on the timeline screen). Retry briefly before giving up.
            rec = None
            for _ in range(10):
                rec = latest_run_summary(history_dirs, newer_than_mtime=watermark)
                if rec is not None:
                    break
                time.sleep(1.0)
            if rec is not None:
                outcome.victory = rec.win
                outcome.seed = rec.seed
                outcome.build_id = rec.build_id
                outcome.killed_by_encounter = rec.killed_by_encounter
                outcome.killed_by_event = rec.killed_by_event
                outcome.was_abandoned = rec.was_abandoned
                if rec.ascension is not None:
                    outcome.ascension = rec.ascension
            watermark = newest_record_mtime(history_dirs)
        lg.finalize(outcome)
        print(
            f"recorded run: seed={outcome.seed} victory={outcome.victory} "
            f"killed_by={outcome.killed_by_encounter}",
            flush=True,
        )

    try:
        while True:
            raw = client.get_state_raw()
            state = parse_state(raw)
            in_run = state.run is not None and not isinstance(state, MenuState)
            if in_run and logger is None:
                char = (state.player.character if state.player else None) or "MANUAL"
                logger = RunLogger(log_root, character_hint=char, header={"mode": "manual"})
                print(f"recording run -> {logger.run_dir.name}", flush=True)
                last_fp = None
            fp = _fingerprint(raw)
            if logger is not None and fp != last_fp:
                logger.log_decision(raw, None, "human play", None)
            if was_in_run and logger is not None and isinstance(state, MenuState):
                finalize(logger)
                logger = None
                recorded += 1
                if runs is not None and recorded >= runs:
                    break
            was_in_run = in_run
            last_fp = fp
            combat = state.state_type in _COMBAT_SCREENS
            time.sleep(poll_interval if combat else nav_poll_interval)
    except KeyboardInterrupt:
        if logger is not None:
            finalize(logger)
            recorded += 1
        raise
    return recorded
