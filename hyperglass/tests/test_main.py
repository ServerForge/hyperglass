"""Test starting hyperglass."""

# Standard Library
import sys
import typing as t
import importlib

# Third Party
import pytest
from typer.testing import CliRunner

# Project
from hyperglass import main
from hyperglass.log import log
from hyperglass.state import use_state
from hyperglass.cli.main import cli
from hyperglass.models.config.params import Params


@pytest.fixture(autouse=True)
def restore_logging() -> t.Generator[None, None, None]:
    yield
    log.remove()
    log.add(sys.stderr)


def test_import_without_node(monkeypatch: pytest.MonkeyPatch):
    def missing() -> t.NoReturn:
        raise FileNotFoundError("node")

    monkeypatch.setattr("hyperglass.util.get_node_version", missing)
    # NodeJS is only required for the UI, so hyperglass can start without it if the UI is disabled.
    importlib.reload(main)
    monkeypatch.undo()
    importlib.reload(main)


@pytest.mark.parametrize(
    "version,error",
    (
        ((20, 1, 0), None),
        ((16, 0, 0), "version 16.0.0 installed"),
        (None, "required for the UI"),
        (FileNotFoundError("node"), "could not be run: node"),
    ),
)
def test_check_node_version(
    version: t.Any, error: t.Optional[str], monkeypatch: pytest.MonkeyPatch
):
    def get_node_version() -> t.Tuple[int, int, int]:
        if isinstance(version, Exception):
            raise version
        return version

    monkeypatch.setattr(main, "get_node_version", get_node_version)
    if error is None:
        main.check_node_version()
    else:
        with pytest.raises(RuntimeError, match=error):
            main.check_node_version()


def test_run_failure(monkeypatch: pytest.MonkeyPatch):
    def init_user_config() -> None:
        use_state().cache.set("params", Params())

    def start(**kwargs: t.Any) -> t.NoReturn:
        # e.g. uvicorn can't bind to the port.
        sys.exit(3)

    monkeypatch.setattr("hyperglass.configuration.init_user_config", init_user_config)
    monkeypatch.setattr(main, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "start", start)
    with pytest.raises(SystemExit) as exc_info:
        main.run()
    assert exc_info.value.code == 3


@pytest.mark.parametrize("error,exit_code", ((SystemExit(3), 3), (KeyboardInterrupt(), 0)))
def test_cli_start_exit_code(error: BaseException, exit_code: int, monkeypatch: pytest.MonkeyPatch):
    def run(*args: t.Any, **kwargs: t.Any) -> t.NoReturn:
        raise error

    monkeypatch.setattr(main, "run", run)
    # A failure to start must not exit with status 0, so a service manager can restart it.
    assert CliRunner().invoke(cli, ["start"]).exit_code == exit_code
