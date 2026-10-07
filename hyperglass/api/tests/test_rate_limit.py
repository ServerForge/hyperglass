"""Test query rate limiting."""

# Standard Library
import typing as t
from types import SimpleNamespace

# Third Party
import pytest
from litestar import get, post
from litestar.testing import create_test_client
from litestar.exceptions import HTTPException

# Project
from hyperglass.state import use_state
from hyperglass.settings import Settings
from hyperglass.models.config.params import Params

# Local
from ..middleware import create_rate_limit
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
    state.cache.set("params", _params)
    yield _params
    state.clear()


def _client(params: Params):
    middleware, stores = create_rate_limit(SimpleNamespace(params=params, settings=Settings))
    # Isolate each test's request history.
    stores["rate_limit"].namespace = f"HYPERGLASS_RATE_LIMIT_TEST_{id(params)}"
    return create_test_client(
        route_handlers=[limited, unlimited],
        middleware=middleware,
        stores=stores,
        exception_handlers={HTTPException: http_handler},
    )


def test_rate_limit(params: Params):
    with _client(params) as client:
        assert [client.post("/limited").status_code for _ in range(2)] == [201, 201]
        response = client.post("/limited")
        assert response.status_code == 429
        assert response.json()["output"] == params.messages.rate_limited
        assert response.json()["level"] == "warning"
        assert "retry-after" in response.headers


def test_rate_limit_only_opted_in_routes(params: Params):
    with _client(params) as client:
        assert all(client.get("/unlimited").status_code == 200 for _ in range(5))


def test_rate_limit_disabled():
    _params = Params(rate_limit={"enable": False})
    assert create_rate_limit(SimpleNamespace(params=_params, settings=Settings)) == ([], {})
