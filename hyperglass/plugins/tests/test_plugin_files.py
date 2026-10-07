"""Test plugin file references."""

# Standard Library
from pathlib import Path

# Third Party
import pytest

# Project
from hyperglass.log import log
from hyperglass.settings import Settings
from hyperglass.models.directive import Directive, BuiltinDirective, plugin_files
from hyperglass.exceptions.private import PluginError
from hyperglass.models.config.params import Params

# Local
from ..main import register_plugin


@pytest.fixture
def app_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "redact.py").write_text("")
    # A file with the same name, which isn't a plugin.
    (plugins / "redact.json").write_text("{}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "transform.py").write_text("")
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    return tmp_path


def test_plugin_files(app_path: Path):
    redact = str(app_path / "plugins" / "redact.py")
    transform = app_path / "elsewhere" / "transform.py"

    assert plugin_files(["redact"]) == [redact]
    assert plugin_files(["redact.py", "redact"]) == [redact]
    # Plugins may be referenced by path, as in the documentation's examples.
    assert plugin_files([str(transform)]) == [str(transform)]
    assert plugin_files([str(transform.with_suffix(""))]) == [str(transform)]
    # Missing plugins & non-Python files are skipped.
    assert plugin_files(["missing", "redact.json"]) == []

    directive = Directive(id="test", name="Test", plugins=["redact", str(transform)], field=None)
    assert directive.plugins == [redact, str(transform)]
    assert Params(plugins=["redact"]).plugins == [redact]


def test_missing_plugin_warning(app_path: Path):
    warnings = []
    handler = log.add(warnings.append, level="WARNING", format="{message}")
    try:
        Directive(id="test", name="Test", plugins=["missing"], field=None)
        assert warnings == ["Plugin file not found\n"]
        warnings.clear()
        # Built-in plugins are associated with built-in directives by the plugins themselves.
        directive = BuiltinDirective(
            id="test", name="Test", plugins=["bgp_route_huawei"], field=None, platforms=["huawei"]
        )
        assert directive.plugins == []
        assert warnings == []
    finally:
        log.remove(handler)


def test_register_non_python_plugin(app_path: Path):
    with pytest.raises(PluginError):
        register_plugin(app_path / "plugins" / "redact.json")
