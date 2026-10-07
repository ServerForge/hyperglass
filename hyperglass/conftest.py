"""Shared test configuration."""

# Third Party
import pytest

# Project
from hyperglass.state.hooks import _use_state


@pytest.fixture(autouse=True)
def reset_state_cache():
    """Don't share state between tests through `use_state()`, which caches state per process."""
    _use_state.cache_clear()
    yield
    _use_state.cache_clear()
