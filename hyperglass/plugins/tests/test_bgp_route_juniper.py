"""Juniper BGP Route Parsing Tests."""

# flake8: noqa
# Standard Library
from pathlib import Path

# Third Party
import pytest

# Project
from hyperglass.models.data.bgp_route import BGPRouteTable
from hyperglass.exceptions.private import ParsingError

# Local
from ._fixtures import MockDevice
from .._builtin.bgp_route_juniper import BGPRoutePluginJuniper, parse_juniper

DEPENDS_KWARGS = {
    "depends": [
        "hyperglass/models/tests/test_util.py::test_check_legacy_fields",
        "hyperglass/external/tests/test_rpki.py::test_rpki",
    ],
    "scope": "session",
}

DIRECT = Path(__file__).parent.parent.parent.parent / ".samples" / "juniper_route_direct.xml"
INDIRECT = Path(__file__).parent.parent.parent.parent / ".samples" / "juniper_route_indirect.xml"
AS_PATH = Path(__file__).parent.parent.parent.parent / ".samples" / "juniper_route_aspath.xml"


def _tester(sample: str):
    plugin = BGPRoutePluginJuniper()

    device = MockDevice(
        name="Test Device",
        address="127.0.0.1",
        group="Test Network",
        credential={"username": "", "password": ""},
        platform="juniper",
        structured_output=True,
        directives=[],
        attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"},
    )

    query = type("Query", (), {"device": device})

    result = plugin.process(output=(sample,), query=query)
    assert isinstance(result, BGPRouteTable), "Invalid parsed result"
    assert hasattr(result, "count"), "BGP Table missing count"
    assert result.count > 0, "BGP Table count is 0"


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_bgp_route_direct():
    with DIRECT.open("r") as file:
        sample = file.read()
    return _tester(sample)


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_bgp_route_indirect():
    with INDIRECT.open("r") as file:
        sample = file.read()
    return _tester(sample)


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_bgp_route_aspath():
    with AS_PATH.open("r") as file:
        sample = file.read()
    return _tester(sample)


def _rt_entry(as_path: str = "65001 65002 I", communities: str = "") -> str:
    return f"""<rt-entry>
<active-tag>*</active-tag>
<protocol-name>BGP</protocol-name>
<preference>170</preference>
<nh><to>192.0.2.1</to><via>xe-0/0/0.0</via></nh>
<peer-as>65001</peer-as>
<age junos:seconds="100">1:40</age>
<validation-state>valid</validation-state>
<bgp-path-attributes>
<attr-as-path-effective><attr-value>{as_path}</attr-value></attr-as-path-effective>
</bgp-path-attributes>
<communities>{communities}</communities>
<local-preference>100</local-preference>
<peer-id>192.0.2.1</peer-id>
</rt-entry>"""


def _response(table: str, routes: str = "") -> str:
    """Create a response with a `{master}` banner, as shown on routers with multiple REs."""
    rt = ""
    if routes:
        rt = f"""<rt junos:style="detail">
<rt-destination>{"2001:db8::" if table == "inet6.0" else "192.0.2.0"}</rt-destination>
<rt-prefix-length>{"32" if table == "inet6.0" else "24"}</rt-prefix-length>
<rt-entry-count junos:format="1 entry">1</rt-entry-count>
<rt-announced-count>1</rt-announced-count>
{routes}
</rt>"""
    return f"""<rpc-reply xmlns:junos="http://xml.juniper.net/junos/18.2R3/junos">
<route-information xmlns="http://xml.juniper.net/junos/18.2R3/junos-routing">
<route-table>
<table-name>{table}</table-name>
<destination-count>1</destination-count>
<total-route-count>1</total-route-count>
<active-route-count>1</active-route-count>
<holddown-route-count>0</holddown-route-count>
<hidden-route-count>0</hidden-route-count>
{rt}
</route-table>
</route-information>
<cli><banner>{{master}}</banner></cli>
</rpc-reply>

{{master}}"""


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_ipv6_after_empty_ipv4():
    # AS path & community queries run a command per address family. If no IPv4 routes match,
    # IPv6 routes are still shown.
    result = parse_juniper((_response("inet.0"), _response("inet6.0", _rt_entry())))
    assert [r.prefix for r in result.routes] == ["2001:db8::/32"]
    assert parse_juniper((_response("inet.0"), _response("inet6.0"))) is None


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_as_path():
    def as_path(value: str) -> list:
        return parse_juniper((_response("inet.0", _rt_entry(as_path=value)),)).routes[0].as_path

    # The AS set isn't removed along with the `{master}` banner.
    assert as_path("65001 65002 {65003 65004} I") == [65001, 65002, 65003, 65004]
    assert as_path("(65010 65011) 65001 I") == [65010, 65011, 65001]
    # The local AS isn't part of the received path.
    assert as_path("[65000] 65001 I") == [65001]
    assert as_path("I") == []


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_communities():
    communities = (
        "<community>65000:1</community>"
        "<extended-community>target:65000:2</extended-community>"
        "<community>large:65000:3:3</community>"
    )
    response = _response("inet.0", _rt_entry(communities=communities))
    route = parse_juniper((response,)).routes[0]
    assert sorted(route.communities) == ["65000:1", "large:65000:3:3", "target:65000:2"]


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_device_error():
    response = """<rpc-reply xmlns:junos="http://xml.juniper.net/junos/18.2R3/junos">
<xnm:error xmlns="http://xml.juniper.net/xnm/1.1/xnm" xmlns:xnm="http://xml.juniper.net/xnm/1.1/xnm">
<source-daemon>routing</source-daemon>
<message>invalid community: foo</message>
</xnm:error>
<cli><banner></banner></cli>
</rpc-reply>"""
    with pytest.raises(ParsingError) as err:
        parse_juniper((response,))
    assert str(err.value) == 'Error from device: "invalid community: foo"'


@pytest.mark.dependency(**DEPENDS_KWARGS)
def test_juniper_parsing_error():
    response = _response("inet.0", _rt_entry()).replace("<preference>170</preference>", "")
    with pytest.raises(ParsingError) as err:
        parse_juniper((response,))
    assert "rt_entry.0.preference" in str(err.value)
