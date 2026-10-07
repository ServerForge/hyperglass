"""Test BGP route data models."""

# Standard Library
import typing as t

# Third Party
import pytest

# Local
from ..data import bgp_route
from ..data.bgp_route import BGPRoute, BGPRouteTable
from ..config.params import Params

COMMUNITIES = ["65000:2345", "65000:23456", "1234:1", "1234:100"]


def route(prefix: str, as_path: t.List[int], **kwargs: t.Any) -> t.Dict[str, t.Any]:
    return {
        "prefix": prefix,
        "active": True,
        "age": 1,
        "weight": 1,
        "med": 0,
        "local_preference": 100,
        "as_path": as_path,
        "communities": [],
        "next_hop": "192.0.2.1",
        "source_as": 64496,
        "source_rid": "192.0.2.1",
        "peer_rid": "192.0.2.1",
        "rpki_state": 1,
        **kwargs,
    }


@pytest.fixture
def params(monkeypatch) -> t.Callable[..., Params]:
    """Validate routes with the given parameters."""

    def use_params(**kwargs: t.Any) -> Params:
        _params = Params(**kwargs)
        monkeypatch.setattr(bgp_route, "use_state", lambda attr=None: _params)
        return _params

    return use_params


def test_communities_deny(params):
    params(structured={"communities": {"mode": "deny", "items": ["65000:2345", r"^1234:1\d+$"]}})
    result = BGPRoute(**route("198.51.100.0/24", [64496], communities=COMMUNITIES))
    assert result.communities == ["65000:23456", "1234:1"]


def test_communities_permit(params):
    params(structured={"communities": {"mode": "permit", "items": ["1234:1", "^65000:.*$"]}})
    result = BGPRoute(**route("198.51.100.0/24", [64496], communities=COMMUNITIES))
    assert result.communities == ["65000:2345", "65000:23456", "1234:1"]


def test_external_rpki(params, monkeypatch):
    params(structured={"rpki": {"mode": "external"}})
    lookups = []

    def rpki_states(routes):
        lookups.append(list(routes))
        return [0 for _ in routes]

    monkeypatch.setattr(bgp_route, "rpki_states", rpki_states)
    table = BGPRouteTable(
        vrf="default",
        winning_weight="high",
        routes=[
            route("1.1.1.0/24", [64496, 13335]),
            # Internal route.
            route("8.8.8.0/24", []),
            # Not a global prefix.
            route("192.0.2.0/24", [64496]),
            # Not a valid network.
            route("9.9.9.9/24", [64496]),
            route("2606:4700::/32", [64496, 13335]),
        ],
    )
    # Origin ASNs of global prefixes are validated at once.
    assert lookups == [[("1.1.1.0/24", 13335), ("2606:4700::/32", 13335)]]
    assert {r.prefix: r.rpki_state for r in table.routes} == {
        "1.1.1.0/24": 0,
        "8.8.8.0/24": 3,
        "192.0.2.0/24": 1,
        "9.9.9.9/24": 3,
        "2606:4700::/32": 0,
    }


def test_router_rpki(params, monkeypatch):
    params()
    monkeypatch.setattr(bgp_route, "rpki_states", lambda routes: pytest.fail("Unexpected lookup"))
    table = BGPRouteTable(
        vrf="default", winning_weight="high", routes=[route("1.1.1.0/24", [13335], rpki_state=2)]
    )
    assert table.routes[0].rpki_state == 2
