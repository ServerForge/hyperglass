"""Arista BGP Route Parsing Tests."""

# flake8: noqa
# Standard Library
import json
import time
from pathlib import Path

# Third Party
import pytest

# Project
from hyperglass.models.config.devices import Device
from hyperglass.models.data.bgp_route import BGPRouteTable
from hyperglass.exceptions.private import ParsingError

# Local
from ._fixtures import MockDevice
from .._builtin.bgp_route_arista import BGPRoutePluginArista, parse_arista

DEPENDS_KWARGS = {
    "depends": [
        "hyperglass/models/tests/test_util.py::test_check_legacy_fields",
        "hyperglass/external/tests/test_rpki.py::test_rpki",
    ],
    "scope": "session",
}

SAMPLE = Path(__file__).parent.parent.parent.parent / ".samples" / "arista_route.json"


def _tester(sample: str):
    plugin = BGPRoutePluginArista()

    device = MockDevice(
        name="Test Device",
        address="127.0.0.1",
        group="Test Network",
        credential={"username": "", "password": ""},
        platform="arista",
        structured_output=True,
        directives=["__hyperglass_arista_eos_bgp_route_table__"],
        attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"},
    )

    query = type("Query", (), {"device": device})

    result = plugin.process(output=(sample,), query=query)
    assert isinstance(result, BGPRouteTable), "Invalid parsed result"
    assert hasattr(result, "count"), "BGP Table missing count"
    assert result.count > 0, "BGP Table count is 0"


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_route_sample():
    with SAMPLE.open("r") as file:
        sample = file.read()
    return _tester(sample)


def _sample() -> dict:
    with SAMPLE.open("r") as file:
        return json.load(file)


def _path(sample: dict) -> dict:
    """Get the sample's route path."""
    return sample["vrfs"]["default"]["bgpRouteEntries"]["198.18.2.0/24"]["bgpRoutePaths"][0]


def _parse(sample: dict) -> BGPRouteTable:
    return parse_arista((json.dumps(sample),))


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_no_route_detail():
    # BGP AS Path and BGP Community queries don't include the routeDetail block or timestamp.
    sample = _sample()
    del _path(sample)["routeDetail"]
    del _path(sample)["timestamp"]
    route = _parse(sample).routes[0]
    assert route.communities == []
    # The route is shown as having been received now, not when hyperglass was started.
    assert 0 <= route.age <= 2


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_route_age(monkeypatch: pytest.MonkeyPatch):
    # The route's age doesn't depend on the server's timezone.
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    try:
        sample = _sample()
        _path(sample)["timestamp"] = int(time.time()) - 60
        assert 60 <= _parse(sample).routes[0].age <= 62
    finally:
        monkeypatch.undo()
        time.tzset()


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_as_path():
    sample = _sample()
    _path(sample)["asPathEntry"]["asPath"] = "65002 {65003,65004}"
    route = _parse(sample).routes[0]
    assert route.as_path == [65002, 65003, 65004]
    # The source (origin) AS is the last AS in the path, not the neighbor AS.
    assert route.source_as == 65004

    _path(sample)["asPathEntry"]["asPath"] = "(65010 65011) 65002"
    assert _parse(sample).routes[0].as_path == [65010, 65011, 65002]

    # Internal routes have an empty AS path, and are sourced from the router's AS.
    _path(sample)["asPathEntry"]["asPath"] = ""
    route = _parse(sample).routes[0]
    assert route.as_path == []
    assert route.source_as == 65001


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_communities():
    sample = _sample()
    _path(sample)["routeDetail"]["extCommunityList"] = ["Route-Target-AS:65000:1"]
    _path(sample)["routeDetail"]["largeCommunityList"] = ["65000:1:1"]
    assert _parse(sample).routes[0].communities == [
        "65002:1",
        "Route-Target-AS:65000:1",
        "65000:1:1",
    ]


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_no_routes():
    assert _parse({"vrfs": {}}) is None


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_arista_parsing_error():
    sample = _sample()
    del _path(sample)["peerEntry"]
    with pytest.raises(ParsingError) as err:
        _parse(sample)
    assert "peerEntry" in str(err.value)
