"""Test API background tasks."""

# Standard Library
import typing as t
import asyncio
from types import SimpleNamespace

# Third Party
import pytest

# Local
from .. import tasks


class Hook:
    """Stand-in for `Webhook`, which records sent queries."""

    sent: t.List[t.Dict[str, t.Any]]

    def __init__(self, config: t.Any) -> None:
        pass

    async def __aenter__(self) -> "Hook":
        """Enter session."""
        return self

    async def __aexit__(self, *args: t.Any) -> None:
        """Exit session."""

    async def send(self, query: t.Dict[str, t.Any]) -> None:
        """Record the query."""
        self.sent.append(query)


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> t.Type[Hook]:
    async def network_info(*targets: str) -> t.Dict[str, t.Any]:
        return {}

    recorder = type("Recorder", (Hook,), {"sent": []})
    monkeypatch.setattr(tasks.bgptools, "network_info", network_info)
    monkeypatch.setattr(tasks, "Webhook", recorder)
    return recorder


def test_webhook_source_ignores_client_headers(hook: t.Type[Hook]):
    params = SimpleNamespace(logging=SimpleNamespace(http=SimpleNamespace(enable=True)))
    # Proxy headers from untrusted clients aren't applied to `request.client` by the web server.
    request = SimpleNamespace(
        headers={"x-real-ip": "203.0.113.66", "x-forwarded-for": "203.0.113.66, 192.0.2.1"},
        client=SimpleNamespace(host="198.51.100.1"),
    )
    data = SimpleNamespace(dict=lambda: {"query_target": "192.0.2.0/24"})
    asyncio.run(tasks.send_webhook(params=params, data=data, request=request, timestamp=None))
    assert len(hook.sent) == 1
    assert hook.sent[0]["source"] == "198.51.100.1"
    # The headers are still included as information.
    assert hook.sent[0]["headers"]["x-real-ip"] == "203.0.113.66"
