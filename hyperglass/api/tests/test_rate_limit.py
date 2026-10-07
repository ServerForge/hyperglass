"""Test query rate limiting."""

# Standard Library
import typing as t
import asyncio
from types import SimpleNamespace

# Third Party
import httpx
import pytest
from litestar import Litestar, get, post
from litestar.testing import create_test_client
from litestar.exceptions import HTTPException

# Project
from hyperglass.state import use_state
from hyperglass.settings import Settings
from hyperglass.models.config.params import Params

# Local
from ..middleware import client_identifier, create_rate_limit
from ..error_handlers import http_handler


@post("/limited", opt={"rate_limit": True})
async def limited() -> str:
    return "ok"


@get("/unlimited")
async def unlimited() -> str:
    return "ok"


@pytest.fixture
def params() -> t.Generator[Params, None, None]:
    _params = Params(rate_limit={"queries": 2, "period": "minute"})
    state = use_state()
    # Isolate each test's request history.
    state.clear()
    state.cache.set("params", _params)
    yield _params
    state.clear()


def _app_kwargs(params: Params) -> t.Dict[str, t.Any]:
    middleware, on_shutdown = create_rate_limit(SimpleNamespace(params=params, settings=Settings))
    return {
        "route_handlers": [limited, unlimited],
        "middleware": middleware,
        "on_shutdown": on_shutdown,
        "exception_handlers": {HTTPException: http_handler},
    }


def test_rate_limit(params: Params):
    with create_test_client(**_app_kwargs(params)) as client:
        responses = [client.post("/limited") for _ in range(2)]
        assert [r.status_code for r in responses] == [201, 201]
        assert [r.headers["ratelimit-remaining"] for r in responses] == ["1", "0"]
        response = client.post("/limited")
        assert response.status_code == 429
        assert response.json()["output"] == params.messages.rate_limited
        assert response.json()["level"] == "warning"
        assert 0 < int(response.headers["retry-after"]) <= 60


def test_rate_limit_only_opted_in_routes(params: Params):
    with create_test_client(**_app_kwargs(params)) as client:
        assert all(client.get("/unlimited").status_code == 200 for _ in range(5))


@pytest.mark.asyncio
async def test_rate_limit_shared_by_workers(params: Params):
    # Each worker process has its own app instance; concurrent requests to all of them must be
    # counted, so the limit can't be exceeded.
    _params = Params(rate_limit={"queries": 5, "period": "minute"})
    apps = [Litestar(**_app_kwargs(_params)) for _ in range(3)]
    clients = [
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        for app in apps
    ]
    try:
        responses = await asyncio.gather(
            *(clients[i % len(clients)].post("/limited") for i in range(30))
        )
    finally:
        for client in clients:
            await client.aclose()
    status_codes = [r.status_code for r in responses]
    assert status_codes.count(201) == 5
    assert status_codes.count(429) == 25


@pytest.mark.parametrize(
    "host,expected",
    (
        ("192.0.2.1", "192.0.2.1"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
        ("::ffff:192.0.2.1", "192.0.2.1"),
        ("testclient", "testclient"),
    ),
)
def test_client_identifier(host: str, expected: str):
    request = SimpleNamespace(client=SimpleNamespace(host=host))
    assert client_identifier(request) == expected


def test_rate_limit_disabled():
    _params = Params(rate_limit={"enable": False})
    assert create_rate_limit(SimpleNamespace(params=_params, settings=Settings)) == ([], [])
