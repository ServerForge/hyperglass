"""Test webhooks, sent to a local HTTP server."""

# Standard Library
import json
import time
import typing as t
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Third Party
import pytest

# Project
from hyperglass.models.webhook import Webhook as WebhookModel
from hyperglass.exceptions.private import ExternalError
from hyperglass.models.config.logging import Http

# Local
from ..webhooks import Webhook

QUERY = {
    "query_location": "router01",
    "query_type": "bgp_route",
    "query_target": "192.0.2.0/24",
    "headers": {
        "user-agent": "<!channel> & friends",
        "referer": None,
        "accept-encoding": None,
        "accept-language": None,
        "x-real-ip": None,
        "x-forwarded-for": None,
    },
    "source": "198.51.100.1",
    "network": {"asn": "64496", "prefix": "198.51.100.0/24", "org": "Example", "country": "US"},
    "timestamp": "2026-10-06 20:00:00",
}


class Recorder(BaseHTTPRequestHandler):
    """Record requests, and respond after `delay` seconds."""

    requests: t.List[t.Dict[str, t.Any]] = []
    delay: float = 0

    def do_POST(self):  # noqa: N802
        """Record the request."""
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        self.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        time.sleep(self.delay)
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args: t.Any) -> None:
        """Don't log requests."""


@pytest.fixture
def server() -> t.Generator[t.Tuple[str, t.Type[Recorder]], None, None]:
    """Run a local HTTP server, on a port other than 443."""
    handler = type("Handler", (Recorder,), {"requests": [], "delay": 0})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", handler
    httpd.shutdown()
    httpd.server_close()


def send(config: Http) -> t.Any:
    async def _send():
        async with Webhook(config) as hook:
            return await hook.send(query=QUERY)

    return asyncio.run(_send())


def test_webhook_model():
    webhook = WebhookModel(**QUERY)
    assert webhook.network.asn == "64496"

    # Network info is reset for local sources.
    webhook = WebhookModel(**{**QUERY, "source": "127.0.0.1"})
    assert webhook.network.asn == "Unknown"


def test_generic_webhook(server):
    url, handler = server
    config = Http(
        provider="generic",
        host=f"{url}/hook?token=a%2Fb",
        headers={"x-special-header": "special"},
        params={"source": "hyperglass"},
        authentication={"mode": "basic", "username": "user", "password": "pass"},
    )
    send(config)

    (request,) = handler.requests
    # The configured URL, including its port & query string, is used.
    assert request["path"] == "/hook?token=a%2Fb&source=hyperglass"
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["x-special-header"] == "special"
    assert headers["authorization"] == "Basic dXNlcjpwYXNz"
    assert headers["user-agent"].startswith("hyperglass/")
    body = json.loads(request["body"])
    assert body["query_target"] == "192.0.2.0/24"
    assert body["network"]["asn"] == "64496"


def test_generic_webhook_api_key(server):
    url, handler = server
    config = Http(
        provider="generic",
        host=f"{url}/hook",
        authentication={"mode": "api_key", "password": "secret"},
    )
    send(config)

    (request,) = handler.requests
    headers = {k.lower(): v for k, v in request["headers"].items()}
    assert headers["x-api-key"] == "secret"
    assert "authorization" not in headers


def test_webhook_timeout(server):
    url, handler = server
    handler.delay = 3
    config = Http(provider="generic", host=f"{url}/hook", timeout=0.5)
    start = time.monotonic()
    with pytest.raises(ExternalError):
        send(config)
    assert time.monotonic() - start < 2


def test_slack_webhook(server):
    url, handler = server
    config = Http(provider="slack", host=f"{url}/services/T000/B000/XXXX")
    send(config)

    (request,) = handler.requests
    assert request["path"] == "/services/T000/B000/XXXX"
    body = request["body"].decode()
    # Request values can't mention users or channels.
    assert "<!channel>" not in body
    assert "&lt;!channel&gt; &amp; friends" in body


def test_msteams_webhook(server):
    url, handler = server
    config = Http(provider="msteams", host=f"{url}/webhookb2/abc/IncomingWebhook/def?x=1")
    send(config)

    (request,) = handler.requests
    assert request["path"] == "/webhookb2/abc/IncomingWebhook/def?x=1"
    assert json.loads(request["body"])["@type"] == "MessageCard"
