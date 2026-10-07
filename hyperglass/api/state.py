"""hyperglass state dependencies."""

# Project
from hyperglass.state import HyperglassState, use_state


async def get_state() -> HyperglassState:
    """Get hyperglass state as a dependency.

    Dependencies' parameters become request parameters, so this must not accept any.
    """
    return use_state()


async def get_params():
    """Get hyperglass params as FastAPI dependency."""
    return use_state("params")


async def get_devices():
    """Get hyperglass devices as FastAPI dependency."""
    return use_state("devices")


async def get_ui_params():
    """Get hyperglass ui_params as FastAPI dependency."""
    return use_state("ui_params")
