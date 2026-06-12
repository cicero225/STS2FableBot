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


@app.command()
def play(
    runs: int = typer.Option(1, help="How many runs to play before stopping."),
    character: str = typer.Option("IRONCLAD", help="Character ID to select."),
    profile: int = typer.Option(None, help="Bot profile slot (1-3); never the owner's."),
    log_root: str = typer.Option("logs", help="Directory for run logs + index."),
    base_url: str = DEFAULT_BASE_URL,
    poll_interval: float = typer.Option(0.5, help="Seconds between state polls."),
) -> None:
    """Play run(s) with the current policy (P0: trivial policy). Attended use only
    for now — keep an eye on it (REQUIREMENTS FR-4.4)."""
    from sts2bot.orchestrator.loop import AgentLoop, LoopConfig
    from sts2bot.policy.trivial import TrivialRouter

    config = LoopConfig(poll_interval=poll_interval, character=character, profile_id=profile)
    with Sts2Client(base_url=base_url) as client:
        for i in range(runs):
            typer.echo(f"--- run {i + 1}/{runs} (character={character}) ---")
            loop = AgentLoop(client, TrivialRouter(), log_root=log_root, config=config)
            outcome = loop.play_one_run()
            typer.echo(
                f"  status={outcome.status} victory={outcome.victory} "
                f"act={outcome.act} floor={outcome.floor} decisions={outcome.decisions}"
            )
            if outcome.error:
                typer.echo(f"  error: {outcome.error}")
            if outcome.status != "completed":
                typer.echo("  stopping: run did not complete cleanly (C5).")
                break


if __name__ == "__main__":
    app()
