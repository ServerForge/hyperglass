"""hyperglass API."""

# Standard Library
import typing as t

if t.TYPE_CHECKING:
    # Third Party
    from litestar import Litestar

__all__ = ("app",)


def __getattr__(name: str) -> "Litestar":
    """Create the app on first access, so submodules can be imported without initialized state."""
    if name == "app":
        # Local
        from .app import app

        # Importing the `app` submodule binds the module to this package's `app` attribute, so
        # later lookups would return the module instead of calling this function. Replace it with
        # the application, so `hyperglass.api:app` resolves to the application every time.
        globals()["app"] = app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
