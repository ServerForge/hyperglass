"""Remove Command Plugin Tests."""

# Standard Library
from types import SimpleNamespace

# Project
from hyperglass.models.directive import Directive

# Local
from ._fixtures import MockDevice
from .._builtin.remove_command import RemoveCommand, remove_command

COMMAND = "show bgp ipv4 unicast {target} | exclude pathid:|Epoch"
OUTPUT = "BGP routing table entry for 192.0.2.0/24\n  65001 65002"


def _query() -> SimpleNamespace:
    device = MockDevice(
        name="Test Device",
        address="127.0.0.1",
        credential={"username": "", "password": ""},
        platform="cisco_ios",
        attrs={"source4": "192.0.2.1", "source6": "2001:db8::1"},
    )
    directive = Directive(
        id="test", name="Test", rules=[{"condition": "*", "command": COMMAND}], field=None
    )
    directive.validate_target("192.0.2.0/24")
    return SimpleNamespace(
        device=device, directive=directive, query_target="192.0.2.0/24", query_type="test"
    )


def test_remove_command():
    commands = ["show version"]
    assert remove_command("router#show version\nVersion 1", commands) == "Version 1"
    # Output without the command isn't changed.
    assert remove_command(" #  DST-ADDRESS\n 0  192.0.2.0/24\n", commands) == (
        " #  DST-ADDRESS\n 0  192.0.2.0/24\n"
    )


def test_remove_rendered_command():
    # The echoed command is matched with its target rendered.
    plugin = RemoveCommand()
    echoed = f"router#{COMMAND.format(target='192.0.2.0/24')}\n{OUTPUT}"
    assert plugin.process(output=(echoed,), query=_query()) == (OUTPUT,)
    assert plugin.process(output=(OUTPUT,), query=_query()) == (OUTPUT,)


def test_remove_command_http():
    # Responses from HTTP devices are left as-is.
    plugin = RemoveCommand()
    echoed = f"{COMMAND.format(target='192.0.2.0/24')}\n{OUTPUT}"
    query = SimpleNamespace(device=SimpleNamespace(driver="hyperglass_http_client"))
    assert plugin.process(output=(echoed,), query=query) == (echoed,)
