"""Test configuration file collection."""

# Standard Library
import tempfile
from pathlib import Path

# Third Party
import pytest

# Project
from hyperglass.settings import Settings
from hyperglass.exceptions.private import ConfigError

# Local
from ..load import load_config

TOML = """
test = "from toml"
"""

YAML = """
test: from yaml
"""

JSON = """
{"test": "from json"}
"""

PY_VARIABLE = """
MAIN = {'test': 'from python variable'}
"""

PY_FUNCTION = """
def main():
    return {'test': 'from python function'}
"""

PY_COROUTINE = """
async def main():
    return {'test': 'from python coroutine'}
"""

CASES = (
    ("test.toml", "from toml", TOML),
    ("test.yaml", "from yaml", YAML),
    ("test_py_variable.py", "from python variable", PY_VARIABLE),
    ("test_py_function.py", "from python function", PY_FUNCTION),
    ("test_py_coroutine.py", "from python coroutine", PY_COROUTINE),
)


def test_collect(monkeypatch):
    with tempfile.TemporaryDirectory() as directory_name:
        directory = Path(directory_name)
        monkeypatch.setattr(Settings, "app_path", directory)
        for name, value, data in CASES:
            path = directory / Path(name)
            with path.open("w") as p:
                p.write(data)
            loaded = load_config(path.stem, required=True)
            assert loaded.get("test") is not None
            assert loaded["test"] == value


PY_COROUTINE_ERROR = """
async def main():
    raise ConnectionError("config API unreachable")
"""

PY_FUNCTION_ERROR = """
def main():
    raise ConnectionError("config API unreachable")
"""

PY_MODULE_ERROR = """
raise ConnectionError("config API unreachable")
"""

PY_FUNCTION_NONE = """
def main():
    config = {'test': 'missing return'}
"""


@pytest.mark.parametrize(
    "data,message",
    (
        (PY_COROUTINE_ERROR, "ConnectionError: config API unreachable"),
        (PY_FUNCTION_ERROR, "ConnectionError: config API unreachable"),
        (PY_MODULE_ERROR, "ConnectionError: config API unreachable"),
        (PY_FUNCTION_NONE, "'main' is not a dictionary"),
    ),
)
def test_python_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: str, message: str):
    """Errors in a Python configuration must never result in an empty (default) configuration."""
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    (tmp_path / "config.py").write_text(data)
    with pytest.raises(ConfigError, match=message):
        load_config("config", required=False)


def test_empty_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    (tmp_path / "config.json").write_text("\n")
    assert load_config("config", required=False) == {}
    (tmp_path / "devices.json").write_text("")
    with pytest.raises(ConfigError, match="it is empty"):
        load_config("devices", required=True)


@pytest.mark.parametrize(
    "name,data,message",
    (
        ("config.json", '{"test": }', "Expecting value"),
        # Parser errors containing braces must be reported, not cause another error.
        ("config.yaml", "test: {a: [}\n", "found '}'"),
    ),
)
def test_invalid_syntax(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, data: str, message: str
):
    monkeypatch.setattr(Settings, "app_path", tmp_path)
    (tmp_path / name).write_text(data)
    with pytest.raises(ConfigError, match=message):
        load_config("config", required=False)
