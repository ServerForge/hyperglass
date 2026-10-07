"""Plugin test fixtures."""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.models.directive import Directives
from hyperglass.models.config.params import Params

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState


@pytest.fixture(autouse=True)
def params_state() -> t.Generator["HyperglassState", None, None]:
    """Store default parameters, which plugins & parsed responses use, and no directives."""
    state = use_state()
    with state.cache.pipeline() as pipeline:
        pipeline.set("params", Params())
        pipeline.set("directives", Directives())
    yield state
    state.clear()
