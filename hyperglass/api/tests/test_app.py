"""Test loading the API application."""

# Standard Library
import os
import typing as t
from pathlib import Path

# Third Party
import pytest
from litestar import Litestar
from uvicorn.importer import import_from_string

# Project
from hyperglass import log
from hyperglass.state import use_state
from hyperglass.configuration import init_ui_params
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices
from hyperglass.defaults.directives import init_builtin_directives

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState


@pytest.fixture
def state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> t.Generator["HyperglassState", None, None]:
    # Logging is already configured in this process.
    monkeypatch.setattr(log, "_configured_pid", os.getpid())
    _state = use_state()
    _params = Params(logging={"directory": tmp_path})
    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", _params)
        pipeline.set("directives", init_builtin_directives())
    _devices = Devices(
        {
            "name": "Router 01",
            "address": "127.0.0.1",
            "credential": {"username": "test", "password": "test"},
            "platform": "juniper",
            "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
        }
    )
    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", init_ui_params(params=_params, devices=_devices))
    yield _state
    _state.clear()


def test_import_app(state: "HyperglassState"):
    # With one worker, uvicorn imports the app twice; each import must return the application.
    # Importing `hyperglass.api:app` must work in the same way, before the app module is imported.
    apps = [import_from_string(i) for i in ("hyperglass.api:app",) * 2]
    apps += [import_from_string(i) for i in ("hyperglass.api.app:app",) * 2]
    assert all(isinstance(app, Litestar) for app in apps)
    assert all(app is apps[0] for app in apps)
