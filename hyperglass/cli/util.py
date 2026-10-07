"""CLI utility functions."""

# Standard Library
import sys
import asyncio

# Third Party
import typer

# Local
from .echo import echo


def build_ui(timeout: int) -> bool:
    """Create a new UI build.

    The UI is built without configuration, so this doesn't require configuration or Redis.
    Configuration is rendered into the UI when hyperglass starts.
    """
    # Project
    from hyperglass.frontend import build_ui as _build_ui

    try:
        asyncio.run(_build_ui(timeout=timeout, force=True))
        echo.success("Completed UI build")
        return True

    except Exception as e:
        if not sys.stdout.isatty():
            echo._console.print_exception(show_locals=True)
            raise typer.Exit(1)

        echo.error("Error building UI: {!s}", e)
        raise typer.Exit(1)
