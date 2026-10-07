"""Test query targets as interpolated into built-in directive commands."""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.models.api import Query
from hyperglass.configuration import init_ui_params
from hyperglass.exceptions.public import InputInvalid
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices
from hyperglass.defaults.directives import init_builtin_directives
from hyperglass.execution.drivers._construct import Construct

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState

DEVICES = (
    {
        "name": "openbgpd",
        "address": "127.0.0.1",
        "credential": {"username": "", "password": ""},
        "platform": "openbgpd",
        "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
    },
    {
        "name": "juniper",
        "address": "127.0.0.1",
        "credential": {"username": "", "password": ""},
        "platform": "juniper",
        "structured_output": False,
        "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
    },
)


@pytest.fixture
def state() -> t.Generator["HyperglassState", None, None]:
    _state = use_state()
    params = Params()
    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", params)
        pipeline.set("directives", init_builtin_directives())

    devices = Devices(*(dict(device) for device in DEVICES))
    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", devices)
        pipeline.set("ui_params", init_ui_params(params=params, devices=devices))

    yield _state
    _state.clear()


def commands(
    state: "HyperglassState", location: str, query_type: str, target: t.Union[str, t.List[str]]
) -> t.List[str]:
    query = Query(queryLocation=location, queryType=query_type, queryTarget=target)
    return Construct(device=state.devices[location], query=query).queries()


def test_openbgpd_quotes_free_form_targets(state):
    assert commands(state, "openbgpd", "__hyperglass_openbgpd_bgp_aspath__", "65000") == [
        "bgpctl show rib inet as '65000'",
        "bgpctl show rib inet6 as '65000'",
    ]
    assert commands(state, "openbgpd", "__hyperglass_openbgpd_bgp_community__", "65000:1") == [
        "bgpctl show rib inet community '65000:1'",
        "bgpctl show rib inet6 community '65000:1'",
    ]


def test_brace_quantifier(state):
    assert commands(state, "juniper", "__hyperglass_juniper_bgp_aspath__", "65000{1,2} .*") == [
        'show route protocol bgp table inet.0 aspath-regex "65000{1,2} .*"',
        'show route protocol bgp table inet6.0 aspath-regex "65000{1,2} .*"',
    ]


@pytest.mark.parametrize("target", ("65000|(id)", "65000|.?/x", "{/system reboot}"))
def test_unsafe_target(state, target: str):
    with pytest.raises(InputInvalid):
        commands(state, "openbgpd", "__hyperglass_openbgpd_bgp_aspath__", target)


@pytest.mark.parametrize(
    "query_type", ("__hyperglass_openbgpd_bgp_route__", "__hyperglass_openbgpd_bgp_aspath__")
)
def test_empty_target(state, query_type: str):
    with pytest.raises(InputInvalid):
        commands(state, "openbgpd", query_type, [])
