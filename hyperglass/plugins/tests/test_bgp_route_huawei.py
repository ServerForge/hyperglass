"""Huawei BGP Route Input Plugin Tests."""

# Standard Library
from types import SimpleNamespace

# Third Party
import pytest

# Local
from .._builtin.bgp_route_huawei import BGPRoutePluginHuawei


@pytest.mark.parametrize(
    "target,expected",
    (
        # A string target, as sent to the API.
        ("192.0.2.0/24", "192.0.2.0 24"),
        # A list target, as sent by the UI.
        (["192.0.2.0/24"], "192.0.2.0 24"),
        (["2001:db8::/32"], "2001:db8:: 32"),
        ("192.0.2.1", "192.0.2.1"),
    ),
)
def test_huawei_transform(target, expected):
    plugin = BGPRoutePluginHuawei()
    assert plugin.transform(SimpleNamespace(query_target=target)) == expected
