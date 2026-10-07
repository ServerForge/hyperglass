"""Test bgp.tools interactions."""

# Standard Library
import time
import socket
import asyncio

# Third Party
import pytest

# Project
from hyperglass.state import use_state

# Local
from .. import bgptools
from ..bgptools import run_whois, parse_whois, network_info

WHOIS_OUTPUT = """AS    | IP      | BGP Prefix | CC | Registry | Allocated  | AS Name
13335 | 1.1.1.1 | 1.1.1.0/24 | US | ARIN     | 2010-07-14 | Cloudflare, Inc."""


# Ignore asyncio deprecation warning about loop
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_network_info():
    checks = (
        ("192.0.2.1", {"asn": "None", "rir": "Private Address"}),
        ("127.0.0.1", {"asn": "None", "rir": "Loopback Address"}),
        ("fe80:dead:beef::1", {"asn": "None", "rir": "Link Local Address"}),
        ("2001:db8::1", {"asn": "None", "rir": "Private Address"}),
        ("1.1.1.1", {"asn": "13335", "rir": "ARIN"}),
    )
    for addr, fields in checks:
        info = asyncio.run(network_info(addr))
        assert addr in info
        for key, expected in fields.items():
            assert info[addr][key] == expected


# Ignore asyncio deprecation warning about loop
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_whois():
    addr = "192.0.2.1"
    response = asyncio.run(run_whois([addr]))
    assert isinstance(response, str)
    assert response != ""


def test_whois_parser():
    addr = "1.1.1.1"
    result = parse_whois(WHOIS_OUTPUT, [addr])
    assert isinstance(result, dict)
    assert addr in result, "Address missing"
    assert result[addr]["asn"] == "13335"
    assert result[addr]["rir"] == "ARIN"
    assert result[addr]["org"] == "Cloudflare, Inc."

    # Lines that aren't results are ignored.
    result = parse_whois("Error: no data\n" + WHOIS_OUTPUT, [addr])
    assert result[addr]["asn"] == "13335"


def test_whois_timeout(monkeypatch):
    # A server that accepts connections, but never responds.
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        open_connection = asyncio.open_connection

        async def connect(*args, **kwargs):
            return await open_connection("127.0.0.1", port)

        monkeypatch.setattr(bgptools.asyncio, "open_connection", connect)
        monkeypatch.setattr(bgptools, "WHOIS_TIMEOUT", 0.5)
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(run_whois(["9.9.9.9"]))
        assert time.monotonic() - start < 2


def test_network_info_cache(monkeypatch):
    queries = []

    async def run_whois(targets):
        queries.append(targets)
        return "64496 | 9.9.9.9 | 9.9.9.0/24 | US | ARIN | 2010-07-14 | Example"

    monkeypatch.setattr(bgptools, "run_whois", run_whois)
    cache = use_state("cache")
    name = bgptools._cache_name(cache, "9.9.9.9")
    cache.instance.delete(name)
    try:
        for _ in range(2):
            info = asyncio.run(network_info("9.9.9.9"))
            assert info["9.9.9.9"]["asn"] == "64496"
        # Network info is cached, & expires.
        assert queries == [["9.9.9.9"]]
        assert 0 < cache.instance.ttl(name) <= bgptools.CACHE_TIMEOUT
    finally:
        cache.instance.delete(name)
