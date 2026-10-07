"""FRR BGP Route Parsing Tests."""

# flake8: noqa
# Standard Library
import copy
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
from .._builtin.bgp_route_frr import BGPRoutePluginFrr, parse_frr

DEPENDS_KWARGS = {
    "depends": [
        "hyperglass/models/tests/test_util.py::test_check_legacy_fields",
        "hyperglass/external/tests/test_rpki.py::test_rpki",
    ],
    "scope": "session",
}

SAMPLE = Path(__file__).parent.parent.parent.parent / ".samples" / "frr_bgp_route.json"


def _tester(sample: str):
    plugin = BGPRoutePluginFrr()

    device = MockDevice(
        name="Test Device",
        address="127.0.0.1",
        group="Test Network",
        credential={"username": "", "password": ""},
        platform="frr",
        structured_output=True,
        directives=["__hyperglass_frr_bgp_route_table__"],
        attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"},
    )

    query = type("Query", (), {"device": device})

    result = plugin.process(output=(sample,), query=query)
    assert isinstance(result, BGPRouteTable), "Invalid parsed result"
    assert hasattr(result, "count"), "BGP Table missing count"
    assert result.count > 0, "BGP Table count is 0"


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_route_sample():
    with SAMPLE.open("r") as file:
        sample = file.read()
    return _tester(sample)


def _sample(**path_overrides) -> dict:
    """Get the sample response with only its first path, updated with `path_overrides`."""
    with SAMPLE.open("r") as file:
        sample = json.load(file)
    path = copy.deepcopy(sample["paths"][0])
    path.update(path_overrides)
    return {**sample, "paths": [path]}


def _parse(sample: dict) -> BGPRouteTable:
    return parse_frr((json.dumps(sample),))


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_prefix_not_found():
    # FRR responds with an empty object if the prefix isn't in the table.
    assert parse_frr(("{}",)) is None
    result = parse_frr(("{}", json.dumps(_sample())))
    assert result.count == 1


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_as_path_segments():
    local = _sample(aspath={"string": "Local", "segments": [], "length": 0})
    assert _parse(local).routes[0].as_path == []

    confed = _sample(
        aspath={
            "string": "(65010 65011) 65001",
            "segments": [
                {"type": "as-confed-sequence", "list": [65010, 65011]},
                {"type": "as-sequence", "list": [65001]},
            ],
            "length": 1,
        }
    )
    assert _parse(confed).routes[0].as_path == [65010, 65011, 65001]

    as_set = _sample(
        aspath={
            "string": "174 13335 {64512,64513}",
            "segments": [
                {"type": "as-sequence", "list": [174, 13335]},
                {"type": "as-set", "list": [64512, 64513]},
            ],
            "length": 3,
        }
    )
    assert _parse(as_set).routes[0].as_path == [174, 13335, 64512, 64513]


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_ipv6_next_hops():
    # The global next hop has no `used` key, and the link-local next hop has no `metric`.
    sample = _sample(
        nexthops=[
            {"ip": "2001:db8:1::1", "afi": "ipv6", "scope": "global", "metric": 0, "accessible": True},
            {"ip": "fe80::1", "afi": "ipv6", "scope": "link-local", "accessible": True, "used": True},
        ]
    )
    sample["prefix"] = "2001:db8::/32"
    assert _parse(sample).routes[0].next_hop == "2001:db8:1::1"


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_invalid_path():
    sample = _sample()
    del sample["paths"][0]["valid"]
    assert _parse(sample).count == 1


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_communities():
    sample = _sample(
        community={"string": "65000:1", "list": ["65000:1"]},
        extendedCommunity={"string": "RT:65000:2 LB:65000:12500000 (100.000 Mbps)"},
        largeCommunity={"string": "65000:3:3", "list": ["65000:3:3"]},
    )
    assert _parse(sample).routes[0].communities == [
        "65000:1",
        "RT:65000:2",
        "LB:65000:12500000 (100.000 Mbps)",
        "65000:3:3",
    ]


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_route_age(monkeypatch: pytest.MonkeyPatch):
    # The route's age doesn't depend on the server's timezone.
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    try:
        sample = _sample(lastUpdate={"epoch": int(time.time()) - 60, "string": ""})
        assert 60 <= _parse(sample).routes[0].age <= 62
    finally:
        monkeypatch.undo()
        time.tzset()


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_frr_parsing_error():
    sample = _sample()
    del sample["paths"][0]["peer"]
    with pytest.raises(ParsingError) as err:
        _parse(sample)
    assert "paths.0.peer" in str(err.value)
