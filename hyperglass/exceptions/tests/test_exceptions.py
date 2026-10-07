"""Test hyperglass exceptions."""

# Standard Library
import typing as t
from types import SimpleNamespace

# Third Party
import pytest
from pydantic import BaseModel, ValidationError

# Project
from hyperglass.log import log
from hyperglass.state import use_state
from hyperglass.models.config.params import Params

# Local
from ..public import RestError, ScrapeError, InputInvalid, DeviceTimeout, ResponseEmpty
from ..private import PluginError, ParsingError, ConfigInvalid, InputValidationError
from .._common import safe_format

DEVICE = SimpleNamespace(name="Router 01", proxy=None)
PROXIED_DEVICE = SimpleNamespace(
    name="Router 01",
    proxy=SimpleNamespace(address="192.0.2.10", credential="username='secret-user'"),
)
QUERY = SimpleNamespace(query_type="bgp_route", query_target="192.0.2.0/24")


@pytest.fixture
def params() -> t.Dict[str, t.Any]:
    return {}


@pytest.fixture(autouse=True)
def state(params: t.Dict[str, t.Any]) -> t.Generator[None, None, None]:
    _state = use_state()
    _state.cache.set("params", Params(**params))
    yield
    _state.clear()


@pytest.mark.parametrize(
    "template,args,kwargs,expected",
    (
        ("{a} and {b}", (), {"a": 1, "b": "2"}, "1 and 2"),
        ("{a} and {missing}", (), {"a": 1}, "1 and {missing}"),
        ("{master}\nerror: syntax error", (), {"device": "x"}, "{master}\nerror: syntax error"),
        ('{"detail": "x"} {', (), {}, '{"detail": "x"} {'),
        ("{} then {}", ("one",), {}, "one then {}"),
        ("{1} {0}", ("a", "b"), {}, "b a"),
    ),
)
def test_safe_format(template: str, args: t.Tuple, kwargs: t.Dict[str, t.Any], expected: str):
    assert safe_format(template, *args, **kwargs) == expected


@pytest.mark.parametrize("exc", (ScrapeError, RestError))
def test_connection_error(exc: t.Type[ScrapeError]):
    error = exc(error=ConnectionRefusedError("Connection refused"), device=DEVICE)
    assert error.message == "Error connecting to Router 01: Connection refused"
    assert error.status_code == 500


def test_device_error_keywords():
    error = DeviceTimeout(error=TimeoutError("timed out"), device=PROXIED_DEVICE)
    assert error.message == "Request timed out. (timed out)"
    # Values not displayed in the message (e.g. proxy details) must not be exposed.
    assert sorted(error.keywords) == ["timed out"]


@pytest.mark.parametrize(
    "params",
    [{"messages": {"connection_error": "Error connecting to {device}: {error} via {proxy}"}}],
)
def test_legacy_template_fields(params: t.Dict[str, t.Any]):
    error = ScrapeError(error=ConnectionRefusedError("refused"), device=PROXIED_DEVICE)
    assert error.message == "Error connecting to Router 01: refused via 192.0.2.10"


def test_error_text_with_braces():
    error = ScrapeError(error=RuntimeError("{master}\nerror: syntax error"), device=DEVICE)
    assert error.message == "Error connecting to Router 01: {master}\nerror: syntax error"


def test_error_template():
    error = InputInvalid(error="No rules matched target '{target}'", target="192.0.2.0/24")
    assert error.message == "192.0.2.0/24 is not valid. (No rules matched target '192.0.2.0/24')"


@pytest.mark.parametrize("error", (None, ""))
def test_no_error(error: t.Optional[str]):
    exc = ResponseEmpty(error=error, query=QUERY)
    assert exc.message == "The query completed, but no matching results were found."


def test_input_validation_error_not_logged():
    # It has no message; the `InputInvalid` error raised from it is logged instead.
    messages = []
    sink = log.add(messages.append, level="DEBUG")
    try:
        InputValidationError(error="Target contains invalid characters", target="x")
    finally:
        log.remove(sink)
    assert messages == []


def test_private_error_args():
    assert str(PluginError("Plugin '{}' is invalid", "x")) == "Plugin 'x' is invalid"
    assert str(ParsingError('Error from device: "{}"', "{master}")) == (
        'Error from device: "{master}"'
    )
    assert str(ParsingError("{key} was not found", key="rt")) == "rt was not found"
    assert str(ParsingError(["not", "a", "string"])) == "['not', 'a', 'string']"


def test_parsing_error_validation_error():
    class Model(BaseModel):
        value: int

    with pytest.raises(ValidationError) as exc_info:
        Model(value="x")

    error = ParsingError(exc_info.value)
    assert "value" in error.message


def test_config_invalid():
    class Model(BaseModel):
        value: int

    with pytest.raises(ValidationError) as exc_info:
        Model(value="x")

    error = ConfigInvalid(errors=exc_info.value.errors())
    assert "Field: value" in error.message
