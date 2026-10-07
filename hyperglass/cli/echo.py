"""Helper functions for CLI message printing."""

# Standard Library
import typing as t

# Third Party
from rich.markup import escape

# Project
from hyperglass.log import HyperglassConsole


class Echo:
    """Container for console-printing functions."""

    _console = HyperglassConsole

    def _fmt(self, message: t.Any, *args: t.Any, **kwargs: t.Any) -> t.Any:
        if isinstance(message, str):
            # Text such as paths (e.g. `[/path]`) must not be interpreted as markup.
            message = escape(message)
            if not args and not kwargs:
                # Messages without values may contain braces, e.g. a search pattern.
                return message
            args = (f"[bold]{escape(str(arg))}[/bold]" for arg in args)
            kwargs = {k: f"[bold]{escape(str(v))}[/bold]" for k, v in kwargs.items()}
            return message.format(*args, **kwargs)
        return message

    def error(self, message: str, *args, **kwargs):
        """Print an error message."""
        return self._console.print(self._fmt(message, *args, **kwargs), style="error")

    def info(self, message: str, *args, **kwargs):
        """Print an informational message."""
        return self._console.print(self._fmt(message, *args, **kwargs), style="info")

    def warning(self, message: str, *args, **kwargs):
        """Print a warning message."""
        return self._console.print(self._fmt(message, *args, **kwargs), style="warning")

    def success(self, message: str, *args, **kwargs):
        """Print a success message."""
        return self._console.print(self._fmt(message, *args, **kwargs), style="success")

    def plain(self, message: str, *args, **kwargs):
        """Print an unformatted message."""
        return self._console.print(self._fmt(message, *args, **kwargs))


echo = Echo()
