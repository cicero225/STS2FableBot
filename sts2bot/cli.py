"""Command-line entry point. Subcommands grow as phases land (see PLAN.md)."""

import typer

import sts2bot
from sts2bot.client import Sts2Client, Sts2ConnectionError
from sts2bot.client.http import DEFAULT_BASE_URL

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the bot version."""
    typer.echo(f"sts2bot {sts2bot.__version__}")


@app.command()
def doctor(base_url: str = DEFAULT_BASE_URL) -> None:
    """Check connectivity to the STS2MCP mod API and report what it sees."""
    with Sts2Client(base_url=base_url, connect_retries=0) as client:
        try:
            raw = client.get_state_raw()
        except Sts2ConnectionError as e:
            typer.echo(f"NOT CONNECTED: {e}")
            typer.echo(
                "Is the game running with mods enabled, and is STS2_MCP installed "
                "in the game's mods/ folder?"
            )
            raise typer.Exit(code=1) from None
        typer.echo(f"Connected to {base_url}")
        typer.echo(f"  state_type:  {raw.get('state_type')}")
        if raw.get("menu_screen"):
            typer.echo(f"  menu_screen: {raw.get('menu_screen')}")
        if raw.get("run"):
            typer.echo(f"  run:         {raw['run']}")
        try:
            profiles = client.list_profiles()
            typer.echo(f"  profiles:    {profiles}")
        except Sts2ConnectionError:
            typer.echo("  profiles:    (endpoint unavailable)")


def _build_router(policy: str):
    if policy == "trivial":
        from sts2bot.policy.trivial import TrivialRouter

        return TrivialRouter(), None
    if policy == "standard":
        from sts2bot.kb.config import load_policy_config
        from sts2bot.policy.standard import StandardRouter

        config = load_policy_config()
        return StandardRouter(config), config.config_hash
    if policy == "fuzz":
        # owner experiment (PLAN: prediction fuzzing, 2026-08-06): random legal
        # combat plays with per-play prediction logging; ATTENDED ONLY -- the
        # safety rail pauses for owner savescums instead of dying
        from sts2bot.kb.config import load_policy_config
        from sts2bot.policy.fuzz import FuzzRouter

        config = load_policy_config()
        return FuzzRouter(config), config.config_hash
    raise typer.BadParameter(f"unknown policy '{policy}' (trivial|standard|fuzz)")


@app.command()
def replay(
    policy: str = typer.Option("standard", help="Policy to replay: trivial|standard."),
    log_root: str = typer.Option("logs", help="Directory holding runs/ to replay against."),
) -> None:
    """Run a policy over every logged state (no game needed) and report sanity."""
    from sts2bot.replay.smoke import replay_smoke

    router, _ = _build_router(policy)
    report = replay_smoke(router, log_root)
    typer.echo(
        f"states={report.states} decisions={report.decisions} waits={report.waits} "
        f"skipped={report.skipped} errors={len(report.errors)}"
    )
    for error in report.errors[:20]:
        typer.echo(f"  ERROR {error}")
    raise typer.Exit(code=0 if report.ok else 1)


@app.command()
def play(
    runs: int = typer.Option(1, help="How many runs to play before stopping."),
    policy: str = typer.Option("standard", help="Policy: trivial|standard."),
    character: str = typer.Option("IRONCLAD", help="Character ID to select."),
    ascension: int = typer.Option(0, help="Ascension level (must be unlocked)."),
    speed: float = typer.Option(
        None, help="Engine time scale (e.g. 3.0 for fast mode; persists until game restart)."
    ),
    profile: int = typer.Option(None, help="Bot profile slot (1-3); never the owner's."),
    log_root: str = typer.Option("logs", help="Directory for run logs + index."),
    base_url: str = DEFAULT_BASE_URL,
    poll_interval: float = typer.Option(
        None, help="Seconds between state polls (default 0.5, scaled down with --speed)."
    ),
    backup: bool = typer.Option(
        True, help="Snapshot the bot save profile after each run (C1 safety)."
    ),
    pause_after_fight: bool = typer.Option(
        False, help="Observation mode: pause after each fight until you resume it."
    ),
    stop_at_floor: int = typer.Option(
        None, help="Stop (without acting) when a fight starts at this floor, for manual takeover."
    ),
    stop_at_map: bool = typer.Option(
        False, help="With --stop-at-floor: hand off at the MAP screen instead of the "
        "fight, so the human picks the door too (act-2 elite A/Bs)."
    ),
) -> None:
    """Play run(s) with the current policy (P0: trivial policy). Attended use only
    for now — keep an eye on it (REQUIREMENTS FR-4.4)."""
    from pathlib import Path

    from sts2bot.client.actions import SetTimeScale
    from sts2bot.orchestrator.loop import AgentLoop, LoopConfig
    from sts2bot.runlog.runfile import discover_history_dirs

    if poll_interval is None:
        # faster game -> poll faster, else the loop becomes the bottleneck
        poll_interval = 0.5 if speed is None else max(0.15, 0.5 / speed)

    router, config_hash = _build_router(policy)
    history_dirs = discover_history_dirs()
    config = LoopConfig(
        poll_interval=poll_interval,
        character=character,
        ascension=ascension,
        profile_id=profile,
        history_dirs=history_dirs,
        policy_name=policy,
        config_hash=config_hash,
        time_scale=speed,
        profile_backup_root=Path("backups/profile_snapshots") if backup else None,
        pause_after_fight=pause_after_fight,
        resume_signal_path=Path("logs/resume.signal") if pause_after_fight else None,
        stop_at_floor=stop_at_floor,
        stop_on_map=stop_at_map,
        # tactical A/B: after the handoff, keep recording the human's play into the
        # same run log (one decisions.jsonl = bot half + human half, diff-ready)
        handoff_follow=stop_at_floor is not None,
    )
    with Sts2Client(base_url=base_url) as client:
        try:
            client.get_state_raw()
        except Sts2ConnectionError as e:
            typer.echo(f"NOT CONNECTED: {e}")
            typer.echo("Is the game running with mods enabled? (sts2bot doctor to check)")
            raise typer.Exit(code=1) from None
        if speed is not None:
            result = client.act(SetTimeScale(scale=speed))
            typer.echo(f"time scale {speed}x: {result.detail} (re-asserted during runs)")
        # Catalog-drift guard (2026-08-19; root cause of the stale-catalog week:
        # cards discovered after the last build_card_catalog run priced as
        # unknowns in every draft — Inferno sat unpriced in ~half of all reward
        # screens). Warn loudly; rebuilding stays a deliberate step because it
        # makes ~500 wiki calls against the live game.
        try:
            import json

            comp = client.get_compendium()
            discovered = set(
                (comp.get("sections", {}).get("card_library", {}) or {})
                .get("discovered_ids") or []
            )
            cat_path = Path("data/card_catalog.json")
            if discovered and cat_path.is_file():
                have = set(json.loads(cat_path.read_text(encoding="utf-8")))
                stale = sorted(discovered - have)
                if stale:
                    typer.echo(
                        f"CATALOG STALE: {len(stale)} discovered cards missing "
                        f"(e.g. {', '.join(stale[:5])}) — run "
                        f"scripts/build_card_catalog.py + build_draft_tags.py"
                    )
        except Exception:
            pass  # advisory only; never block a batch on it
        for i in range(runs):
            typer.echo(f"--- run {i + 1}/{runs} (policy={policy} character={character}) ---")
            loop = AgentLoop(client, router, log_root=log_root, config=config)
            outcome = loop.play_one_run()
            typer.echo(
                f"  status={outcome.status} victory={outcome.victory} "
                f"act={outcome.act} floor={outcome.floor} decisions={outcome.decisions}"
            )
            if outcome.seed:
                killers = [
                    k
                    for k in (outcome.killed_by_encounter, outcome.killed_by_event)
                    if k and k != "NONE.NONE"
                ]
                typer.echo(
                    f"  seed={outcome.seed} build={outcome.build_id} "
                    f"killed_by={killers[0] if killers else None}"
                )
            if outcome.error:
                typer.echo(f"  error: {outcome.error}")
            if outcome.status == "stopped":
                typer.echo("  handoff done: bot + human halves are in this run's log.")
                break
            if outcome.status != "completed":
                # Fork-mod batch resilience (2026-08-10, after the treasure wedge
                # killed two 40-run batches in 24h): abandon_run is a direct
                # RunManager teardown that bypasses the wedged action queue. On
                # pre-fork builds the action errors and we halt exactly as before.
                typer.echo("  run did not complete cleanly (C5); "
                           "attempting abandon-to-menu recovery...")
                if _try_abandon_recovery(client):
                    typer.echo("  recovered to main menu; batch continues.")
                    continue
                typer.echo("  stopping: abandon recovery unavailable or failed (C5).")
                break


def _try_abandon_recovery(client: Sts2Client, timeout_s: float = 45.0) -> bool:
    """Recover a stall-aborted run to the main menu via the fork mod's abandon_run
    (direct RunManager.Abandon teardown -- works where UI clicks are void because it
    never enters the wedged action queue). Returns True once the menu is reached.
    Pre-fork mod builds answer 'Unknown action' -> False, batch halts as before.
    Caveat recorded up front: a HARD engine freeze (frames stopped) may swallow
    even this; the stall-abort report + manual force-close remains the backstop."""
    import time as _time

    from sts2bot.client import actions as act

    try:
        res = client.act(act.AbandonRun())
    except Exception:
        return False
    if getattr(res, "status", None) != "ok":
        return False
    deadline = _time.monotonic() + timeout_s
    while _time.monotonic() < deadline:
        try:
            st = client.get_state()
        except Exception:
            _time.sleep(1.0)
            continue
        stt = getattr(st, "state_type", None)
        if stt == "menu":
            return True
        if stt == "game_over":
            # Abandon lands on the game-over screen; step through to the menu
            import contextlib

            with contextlib.suppress(Exception):
                client.act(act.MenuSelect(option="main_menu"))
        _time.sleep(1.0)
    return False


@app.command()
def record(
    out: str = typer.Option("logs/manual", help="Directory for manual-play run logs."),
    poll_interval: float = typer.Option(0.5, help="Seconds between polls during combat."),
    nav_poll_interval: float = typer.Option(
        4.0, help="Seconds between polls on non-combat screens (slower so the mod's "
        "screen re-render doesn't fight your shop/map navigation)."
    ),
    base_url: str = DEFAULT_BASE_URL,
) -> None:
    """Record a human-played session (a state trace per run, same format as bot runs) for
    human-vs-bot comparison. Start this, then play normally; Ctrl+C to stop. The bot never acts."""
    from sts2bot.orchestrator.recorder import record_session
    from sts2bot.runlog.runfile import discover_history_dirs

    with Sts2Client(base_url=base_url) as client:
        try:
            client.get_state_raw()
        except Sts2ConnectionError as e:
            typer.echo(f"NOT CONNECTED: {e}")
            raise typer.Exit(code=1) from None
        typer.echo("Recording manual play. Play normally; Ctrl+C to stop. The bot will NOT act.")
        try:
            n = record_session(
                client,
                log_root=out,
                history_dirs=discover_history_dirs(),
                poll_interval=poll_interval,
                nav_poll_interval=nav_poll_interval,
            )
            typer.echo(f"recorded {n} run(s).")
        except KeyboardInterrupt:
            typer.echo("\nstopped recording.")


if __name__ == "__main__":
    app()
