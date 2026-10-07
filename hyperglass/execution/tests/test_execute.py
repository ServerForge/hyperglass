"""Test query execution."""

# Standard Library
import time
import ssl
import socket
import typing as t
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

# Third Party
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.models.api import Query
from hyperglass.configuration import init_ui_params
from hyperglass.models.directive import Directives
from hyperglass.exceptions.public import RestError, ScrapeError, DeviceTimeout, ResponseEmpty
from hyperglass.compat._sshtunnel import HandlerSSHTunnelForwarderError
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices

# Local
from .. import main
from ..drivers import ssh, Connection

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState


def closed_port() -> int:
    """Get a local port nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def device(name: str, **kwargs: t.Any) -> t.Dict[str, t.Any]:
    return {
        "name": name,
        "address": "127.0.0.1",
        "credential": {"username": "user", "password": "pass"},
        "platform": "juniper",
        "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
        "directives": ["test_directive"],
        **kwargs,
    }


def http_device(name: str, port: int, **http: t.Any) -> t.Dict[str, t.Any]:
    return device(name, port=port, platform="http", http={"scheme": "http", "path": "/lg", **http})


class HTTPDevice(BaseHTTPRequestHandler):
    """Respond to queries like an HTTP device, recording requests."""

    paths: t.List[str] = []

    def do_GET(self):  # noqa: N802
        """Respond with route output, or an error for `/denied`."""
        self.paths.append(self.path)
        if self.path.startswith("/denied"):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"route output")

    def log_message(self, *args: t.Any) -> None:
        """Don't log requests."""


@pytest.fixture
def http_server() -> t.Generator[t.Tuple[int, t.Type[HTTPDevice]], None, None]:
    handler = type("Handler", (HTTPDevice,), {"paths": []})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield httpd.server_address[1], handler
    httpd.shutdown()
    httpd.server_close()


DIRECTIVES = [
    {
        "test_directive": {
            "name": "Test",
            "rules": [{"condition": None, "command": "show route {target}"}],
            "field": {"description": "test"},
        }
    }
]


@pytest.fixture
def state(request, http_server) -> t.Generator["HyperglassState", None, None]:
    """Initialize Redis store with test devices.

    - `test1`: an SSH device.
    - `test2`: an SSH device behind an unreachable SSH proxy.
    - `http1`, `http2`: HTTP devices served by `http_server`, with query parameter templates.
    - `http3`: an unreachable HTTP device.
    """
    _state = use_state()
    port, _ = http_server

    _params = Params(
        # Exceptions' messages are tested separately.
        messages={"connection_error": "Error connecting: {error}"},
        **getattr(request, "param", {}),
    )
    proxy = {
        "address": "127.0.0.1",
        "port": closed_port(),
        "credential": {"username": "user", "password": "pass"},
        "platform": "linux_ssh",
    }

    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", _params)
        pipeline.set("directives", Directives.new(*DIRECTIVES))

    _devices = Devices(
        device("test1"),
        device("test2", proxy=proxy),
        http_device(
            "http1",
            port,
            query={"q": "{query_target}", "loc": "{query_location}", "type": "{query_type}"},
        ),
        http_device(
            "http2",
            port,
            attribute_map={"query_target": "prefix"},
            query={"a": "{prefix}", "b": "{query_target}", "c": "static"},
        ),
        http_device("http3", closed_port()),
        http_device("http4", port, path="/denied", query={"key": "s3cr3t", "q": "{query_target}"}),
        http_device("http5", port, query={"filter": '{"prefix": "{query_target}"}', "v": "{vrf}"}),
    )

    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", init_ui_params(params=_params, devices=_devices))

    _state.reset_plugins("output")
    yield _state
    _state.clear()


class Parser:
    """Stand-in for output plugins, which takes `delay` seconds to parse output."""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def execute(self, *, output: t.Any, query: t.Any) -> t.Any:
        """Block, like slow parsing."""
        time.sleep(self.delay)
        return output


def fake_driver(output: t.Any, parse_delay: float = 0) -> t.Type[Connection]:
    """Create a driver that returns `output` without connecting to a device."""

    class FakeConnection(Connection):
        def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
            super().__init__(*args, **kwargs)
            if parse_delay:
                self.plugin_manager = Parser(parse_delay)

        def setup_proxy(self) -> t.NoReturn:
            raise NotImplementedError

        async def collect(self, *args: t.Any) -> t.Any:
            return output

    return FakeConnection


def query(location: str = "test1") -> Query:
    return Query(queryLocation=location, queryTarget="192.0.2.0/24", queryType="test_directive")


async def max_loop_delay(coro: t.Awaitable) -> t.Tuple[t.Any, float]:
    """Await `coro`, and measure the longest time the event loop was blocked."""
    delays = []

    async def tick():
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            delays.append(now - last)
            last = now

    ticker = asyncio.create_task(tick())
    try:
        return await coro, max(delays)
    finally:
        ticker.cancel()


@pytest.mark.parametrize("output", [(), ("",), ("", "\n"), " \n"])
def test_empty_response(state, monkeypatch, output):
    monkeypatch.setattr(main, "map_driver", lambda _: fake_driver(output))
    with pytest.raises(ResponseEmpty):
        asyncio.run(main.execute(query()))


def test_response(state, monkeypatch):
    monkeypatch.setattr(main, "map_driver", lambda _: fake_driver(("output 1", "output 2")))
    assert asyncio.run(main.execute(query())) == "output 1\n\noutput 2"


def test_parse_off_event_loop(state, monkeypatch):
    monkeypatch.setattr(main, "map_driver", lambda _: fake_driver(("output",), parse_delay=0.5))
    result, delay = asyncio.run(max_loop_delay(main.execute(query())))
    assert result == "output"
    assert delay < 0.25


@pytest.mark.parametrize("state", [{"request_timeout": 2}], indirect=True)
def test_parse_timeout(state, monkeypatch):
    monkeypatch.setattr(main, "map_driver", lambda _: fake_driver(("output",), parse_delay=1.5))

    async def timed_execute() -> float:
        start = time.monotonic()
        with pytest.raises(DeviceTimeout):
            await main.execute(query())
        return time.monotonic() - start

    # Parsing is included in the request timeout (request_timeout - 1).
    assert asyncio.run(timed_execute()) < 1.4


def test_proxy_unreachable(state):
    with pytest.raises(ScrapeError, match="Could not establish session to SSH gateway"):
        asyncio.run(main.execute(query("test2")))


class Tunnel:
    """Stand-in for an SSH tunnel, which takes `delay` seconds to start, recording events."""

    local_bind_host = "127.0.0.1"
    local_bind_port = 2222

    def __init__(self, delay: float = 0, error: t.Optional[Exception] = None) -> None:
        self.delay = delay
        self.error = error
        self.events: t.List[str] = []

    def start(self) -> None:
        """Start the tunnel."""
        time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.events.append("started")

    def stop(self) -> None:
        """Stop the tunnel."""
        self.events.append("stopped")


@pytest.mark.parametrize("state", [{"request_timeout": 2}], indirect=True)
def test_proxy_stopped_after_timeout(state, monkeypatch):
    tunnel = Tunnel(delay=1.5)
    monkeypatch.setattr(ssh, "open_tunnel", lambda *args, **kwargs: tunnel)

    async def run() -> None:
        with pytest.raises(DeviceTimeout):
            await main.execute(query("test2"))
        # The tunnel is still starting when the request times out.
        assert tunnel.events == []
        await asyncio.sleep(1)

    asyncio.run(run())
    assert tunnel.events == ["started", "stopped"]


def test_proxy_stopped_after_error(state, monkeypatch):
    # E.g. the device isn't reachable from the proxy, after connecting to the proxy.
    tunnel = Tunnel(error=HandlerSSHTunnelForwarderError("An error occurred while opening tunnels"))
    monkeypatch.setattr(ssh, "open_tunnel", lambda *args, **kwargs: tunnel)
    with pytest.raises(ScrapeError, match="opening tunnels"):
        asyncio.run(main.execute(query("test2")))
    assert tunnel.events == ["stopped"]


def test_http_query_template(state, http_server):
    _, handler = http_server
    # The device's port is used.
    assert asyncio.run(main.execute(query("http1"))) == "route output"

    (path,) = handler.paths
    assert urlsplit(path).path == "/lg"
    assert parse_qs(urlsplit(path).query) == {
        "q": ["192.0.2.0/24"],
        "loc": ["http1"],
        "type": ["test_directive"],
    }


def test_http_query_template_attribute_map(state, http_server):
    _, handler = http_server
    assert asyncio.run(main.execute(query("http2"))) == "route output"

    (path,) = handler.paths
    assert parse_qs(urlsplit(path).query) == {
        "a": ["192.0.2.0/24"],
        "b": ["192.0.2.0/24"],
        "c": ["static"],
    }


def test_http_query_template_braces(state, http_server):
    _, handler = http_server
    assert asyncio.run(main.execute(query("http5"))) == "route output"

    (path,) = handler.paths
    # Only known placeholders are replaced.
    assert parse_qs(urlsplit(path).query) == {
        "filter": ['{"prefix": "192.0.2.0/24"}'],
        "v": ["{vrf}"],
    }


def test_http_error_hides_query(state):
    with pytest.raises(RestError) as exc_info:
        asyncio.run(main.execute(query("http4")))
    # The query string may contain credentials, so it isn't shown to users.
    assert "403 Forbidden" in exc_info.value.message
    assert "s3cr3t" not in exc_info.value.message


def test_http_unreachable(state):
    with pytest.raises(RestError):
        asyncio.run(main.execute(query("http3")))


@pytest.mark.parametrize(
    "verify_ssl,verify_mode", [(True, ssl.CERT_REQUIRED), (False, ssl.CERT_NONE)]
)
def test_http_verify_ssl(state, verify_ssl: bool, verify_mode: ssl.VerifyMode):
    _device = Devices(http_device("https1", 8443, verify_ssl=verify_ssl))["https1"]
    client = _device.http.create_client(device=_device)
    # SSL must be configured on the transport; a client ignores `verify` if given a transport.
    assert client._transport._pool._ssl_context.verify_mode == verify_mode


def test_http_ipv6_address(state):
    _device = Devices({**http_device("http6", 8080), "address": "2001:db8::1"})["http6"]
    client = _device.http.create_client(device=_device)
    assert str(client.base_url) == "http://[2001:db8::1]:8080"
