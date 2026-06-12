"""Command-line entry point. Subcommands grow as phases land (see PLAN.md)."""

import typer

import sts2bot

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the bot version."""
    typer.echo(f"sts2bot {sts2bot.__version__}")


if __name__ == "__main__":
    app()
