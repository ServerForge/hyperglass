"""Test the hyperglass CLI."""

# Standard Library
import typing as t
from pathlib import Path

# Third Party
import typer
import pytest
from typer.testing import CliRunner

# Project
from hyperglass.state import HyperglassState, use_state
from hyperglass.settings import Settings
from hyperglass.models.directive import Directives
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices

# Local
from ..echo import echo
from ..main import cli

runner = CliRunner()


def _device(name: str) -> t.Dict[str, t.Any]:
    return {
        "name": name,
        "address": "127.0.0.1",
        "credential": {"username": "", "password": ""},
        "platform": "juniper",
        "directives": ["juniper_bgp_route"],
    }


def _use_state_uncached(attr: t.Optional[str] = None) -> t.Any:
    """`use_state()` without its per-process caching, so these tests' devices don't persist."""
    _state = HyperglassState(settings=Settings)
    if attr is None:
        return _state
    return getattr(_state, attr)


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> t.Generator["HyperglassState", None, None]:
    # Commands import `use_state` when run.
    monkeypatch.setattr("hyperglass.state.use_state", _use_state_uncached)
    _state = use_state()
    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", Params())
        pipeline.set(
            "directives",
            Directives.new(
                {"juniper_bgp_route": {"name": "BGP Route", "field": {"description": "test"}}}
            ),
        )
    _state.cache.set(
        "devices", Devices(_device("Chicago 1"), _device("Chicago 2"), _device("New York"))
    )
    yield _state
    _state.clear()


def test_search_all_matches(state: "HyperglassState"):
    result = runner.invoke(cli, ["devices", "chicago"])
    assert result.exit_code == 0
    assert "Chicago 1" in result.output
    assert "Chicago 2" in result.output
    assert "New York" not in result.output


@pytest.mark.parametrize("command", ("devices", "directives", "plugins"))
def test_search_no_matches(state: "HyperglassState", command: str):
    # Regular expressions with braces are valid search patterns, not format strings.
    result = runner.invoke(cli, [command, "x{2}"])
    assert result.exit_code == 1
    assert f"No {command} matching x{{2}}" in result.output


def test_search_invalid_pattern(state: "HyperglassState"):
    result = runner.invoke(cli, ["devices", "chicago("])
    assert result.exit_code == 1
    assert "Invalid search pattern chicago(" in result.output


@pytest.mark.parametrize(
    "command,description",
    (
        ("devices", "Show all configured devices"),
        ("directives", "Show all configured directives"),
        ("plugins", "Show all registered plugins"),
    ),
)
def test_help(command: str, description: str):
    result = runner.invoke(cli, [command, "--help"])
    assert result.exit_code == 0
    assert description in result.output


def test_echo_markup_and_braces(capsys: pytest.CaptureFixture):
    echo.error("Error building UI: {!s}", "failed to write [/etc/hyperglass] {x}")
    echo.warning("No such file [/etc/hyperglass/x{2}]")
    output = capsys.readouterr().out
    assert "Error building UI: failed to write [/etc/hyperglass] {x}" in output
    assert "No such file [/etc/hyperglass/x{2}]" in output


def test_setup_keeps_user_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Local
    from .. import util, installer

    monkeypatch.setattr(Settings, "app_path", tmp_path)
    monkeypatch.setattr(installer.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(util, "build_ui", lambda timeout: True)
    images = tmp_path / "static" / "images"
    images.mkdir(parents=True)
    user_files = {
        images / "logo.png": b"user logo",
        images / "favicon.png": b"user favicon",
        images / "hyperglass-light.svg": b"modified asset",
    }
    for path, content in user_files.items():
        path.write_bytes(content)

    result = runner.invoke(cli, ["setup"])

    assert result.exit_code == 0, result.output
    for path, content in user_files.items():
        assert path.read_bytes() == content
    for asset in installer.ASSET_DIR.iterdir():
        assert (images / asset.name).exists()
    assert (images / "favicons").is_dir()


def test_setup_ui_build_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Local
    from .. import util, installer

    def build_ui(timeout: int) -> bool:
        echo.error("Error building UI: {!s}", "next build failed")
        raise typer.Exit(1)

    monkeypatch.setattr(Settings, "app_path", tmp_path)
    monkeypatch.setattr(installer.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(util, "build_ui", build_ui)

    result = runner.invoke(cli, ["setup"])

    assert result.exit_code == 1
    # The build error is shown, rather than captured & discarded.
    assert "Error building UI: next build failed" in result.output
