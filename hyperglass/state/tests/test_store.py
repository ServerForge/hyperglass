"""Test state storage."""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.models.config.params import Params

# Local
from ..hooks import use_state

if t.TYPE_CHECKING:
    # Local
    from ..store import HyperglassState

OTHER_KEYS = ("other-app:key", "hyperglass_other", "other.hyperglass.key")


@pytest.fixture
def state() -> t.Generator["HyperglassState", None, None]:
    _state = use_state()
    _state.clear()
    _state.cache.set("params", Params())
    _state.cache.set(("plugins", "output"), [])
    _state.cache.set_map_item("hyperglass.query.abc123", "output", "cached output")
    _state.cache.set_map_item("hyperglass.external.rpki", "192.0.2.0/24@65000", 1)
    _state.cache.instance.set("hyperglass.rate_limit:192.0.2.1", 1)
    for key in OTHER_KEYS:
        _state.cache.instance.set(key, "other")
    yield _state
    _state.clear()
    _state.cache.instance.delete(*OTHER_KEYS)


def test_clear(state: "HyperglassState"):
    state.clear()
    assert state.cache.instance.keys("hyperglass.*") == []
    # Other applications' keys in the same database aren't deleted.
    assert all(state.cache.instance.get(key) == b"other" for key in OTHER_KEYS)


def test_clear_cache(state: "HyperglassState"):
    assert state.clear_cache() == 2
    assert state.cache.get_map("hyperglass.query.abc123", "output") is None
    assert state.cache.get_map("hyperglass.external.rpki", "192.0.2.0/24@65000") is None
    # State & rate limits aren't deleted, so a running instance isn't affected.
    assert isinstance(state.params, Params)
    assert state.plugins("output") == []
    assert state.cache.instance.get("hyperglass.rate_limit:192.0.2.1") == b"1"
    assert all(state.cache.instance.get(key) == b"other" for key in OTHER_KEYS)


def test_delete_prefix_literal(state: "HyperglassState"):
    state.cache.instance.set("hyperglass.state.query.x*y", 1)
    state.cache.instance.set("hyperglass.state.query.xzy", 1)
    # Glob characters in the prefix are matched literally.
    assert state.cache.delete_prefix("hyperglass.state.query.x*") == 1
    assert state.cache.instance.exists("hyperglass.state.query.xzy")
