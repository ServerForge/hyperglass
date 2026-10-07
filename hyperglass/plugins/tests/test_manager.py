"""Plugin manager tests."""

# Standard Library
import typing as t
from types import SimpleNamespace
from ipaddress import ip_network

# Third Party
import pytest

# Project
from hyperglass.models.api.query import SimpleQuery
from hyperglass.exceptions.private import InputValidationError
from hyperglass.defaults.directives import init_builtin_directives

# Local
from .. import InputPlugin, OutputPlugin, InputPluginManager, OutputPluginManager
from ..main import init_builtin_plugins
from .._builtin import RemoveCommand, ValidateBGPCommunity, BGPRoutePluginJuniper


class Redact(OutputPlugin):
    """Redact secrets."""

    def process(self, *, output, query):
        """Redact secrets."""
        return tuple(o.replace("secret", "<redacted>") for o in output)


class FrrOnly(OutputPlugin):
    """Mark output from FRR devices."""

    platforms: t.Sequence[str] = ("frr",)

    def process(self, *, output, query):
        """Mark output from FRR devices."""
        return tuple(f"{o} (frr)" for o in output)


class Allow(InputPlugin):
    """Permit any target."""

    def validate(self, query):
        """Permit any target."""
        return True


class DenyProtected(InputPlugin):
    """Deny targets in a protected network."""

    def validate(self, query):
        """Deny targets in a protected network."""
        if ip_network(query.query_target).subnet_of(ip_network("198.51.100.0/24")):
            self.failure_reason = "Protected network"
            return False
        return None


class TransformToMask(InputPlugin):
    """Transform a prefix to a network address & mask."""

    def transform(self, query):
        """Transform a prefix to a network address & mask."""
        network = ip_network(query.query_target)
        return f"{network.network_address} {network.netmask}"


class ValidateOnly(InputPlugin):
    """Validate, without transforming, targets."""

    def validate(self, query):
        """Validate targets, without an opinion."""
        return None


class Query(SimpleNamespace):
    """Query with only the attributes used by plugin managers."""

    def summary(self) -> SimpleQuery:
        """Summarize the query."""
        return SimpleQuery(
            query_location="test", query_target=self.query_target, query_type=self.directive.id
        )


def _query(target: str = "192.0.2.0/24", directive: str = "test", platform: str = "juniper"):
    return Query(
        query_target=target,
        directive=SimpleNamespace(id=directive, plugins=[]),
        device=SimpleNamespace(platform=platform, driver="netmiko"),
    )


def test_directive_output_plugin():
    # A plugin attached to a directive applies to the directive on any platform.
    manager = OutputPluginManager()
    manager.register(Redact, directives=("test",))
    assert manager.execute(output=("a secret",), query=_query()) == ("a <redacted>",)
    assert manager.execute(output=("a secret",), query=_query(directive="other")) == ("a secret",)


def test_platform_output_plugin():
    manager = OutputPluginManager()
    manager.register(FrrOnly, directives=("test",))
    assert manager.execute(output=("a",), query=_query()) == ("a",)
    assert manager.execute(output=("a",), query=_query(platform="frr")) == ("a (frr)",)


def test_common_output_plugin():
    manager = OutputPluginManager()
    manager.register(Redact, common=True)
    assert manager.execute(output=("a secret",), query=_query(directive="other")) == (
        "a <redacted>",
    )


def test_input_validation_order():
    manager = InputPluginManager()
    manager.register(Allow, common=True)
    manager.register(DenyProtected, common=True)
    # A plugin that permits the target doesn't skip a later plugin that denies it.
    with pytest.raises(InputValidationError) as err:
        manager.validate(_query("198.51.100.0/24"))
    assert err.value.kwargs["error"] == "Protected network"
    assert manager.validate(_query("192.0.2.0/24")) is True


def test_input_transform_chain():
    manager = InputPluginManager()
    manager.register(TransformToMask, common=True)
    manager.register(ValidateOnly, common=True)
    # A later plugin that doesn't transform the target doesn't undo an earlier transformation.
    assert manager.transform(query=_query("192.0.2.0/24")) == "192.0.2.0 255.255.255.0"


def test_unregister():
    manager = OutputPluginManager()
    manager.register(Redact, common=True)
    manager.register(FrrOnly, common=True)
    assert [p.name for p in manager] == ["FrrOnly", "Redact"]
    manager.unregister(Redact)
    assert [p.name for p in manager] == ["FrrOnly"]
    manager.unregister(manager.plugins()[0])
    assert list(manager) == []


def test_builtin_plugins():
    init_builtin_plugins()
    assert any(isinstance(p, ValidateBGPCommunity) for p in InputPluginManager().plugins())
    output_plugins = OutputPluginManager().plugins()
    assert any(isinstance(p, RemoveCommand) for p in output_plugins)
    assert any(isinstance(p, BGPRoutePluginJuniper) for p in output_plugins)


def test_bgp_community_directives():
    # BGP community targets are validated for every built-in BGP community directive, except BIRD's,
    # which uses BIRD's own community syntax.
    directives = {
        d.id for d in init_builtin_directives() if "_bgp_community" in d.id and "_bird_" not in d.id
    }
    assert directives == set(ValidateBGPCommunity().directives)
