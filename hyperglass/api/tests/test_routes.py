"""Test API routes."""

# Standard Library
import typing as t

# Third Party
import pytest
from litestar import get
from litestar.testing import TestClient, create_test_client
from litestar.exceptions import HTTPException, ValidationException

# Project
from hyperglass.state import use_state
from hyperglass.exceptions import HyperglassError
from hyperglass.configuration import init_ui_params
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices
from hyperglass.defaults.directives import init_builtin_directives

# Local
from ..routes import info, query, device, devices, queries
from ..error_handlers import app_handler, http_handler, default_handler, validation_handler

if t.TYPE_CHECKING:
    # Project
    from hyperglass.state import HyperglassState

QUERY_TYPE = "__hyperglass_juniper_bgp_route_table__"
QUERY = {"queryLocation": "router01", "queryType": QUERY_TYPE, "queryTarget": "192.0.2.0/24"}


@get("/error")
async def error() -> str:
    raise RuntimeError("Unhandled error")


@pytest.fixture
def params() -> t.Dict[str, t.Any]:
    return {"fake_output": True}


@pytest.fixture
def state(params: t.Dict[str, t.Any]) -> t.Generator["HyperglassState", None, None]:
    _state = use_state()
    _state.clear()
    _params = Params(**params)
    with _state.cache.pipeline() as pipeline:
        pipeline.set("params", _params)
        pipeline.set("directives", init_builtin_directives())
    _devices = Devices(
        {
            "name": "Router 01",
            "id": "router01",
            "address": "127.0.0.1",
            "credential": {"username": "test", "password": "test"},
            "platform": "juniper",
            "attrs": {"source4": "192.0.2.1", "source6": "2001:db8::1"},
        }
    )
    with _state.cache.pipeline() as pipeline:
        pipeline.set("devices", _devices)
        pipeline.set("ui_params", init_ui_params(params=_params, devices=_devices))
    yield _state
    _state.clear()


@pytest.fixture
def client(state: "HyperglassState") -> t.Generator[TestClient, None, None]:
    with create_test_client(
        route_handlers=[device, devices, queries, info, query, error],
        exception_handlers={
            HTTPException: http_handler,
            HyperglassError: app_handler,
            ValidationException: validation_handler,
            Exception: default_handler,
        },
    ) as _client:
        yield _client


def test_query(client: TestClient):
    response = client.post("/api/query", json=QUERY)
    assert response.status_code == 201
    assert response.json()["cached"] is False
    assert response.json()["output"]["routes"]


def test_query_cache_not_extended(client: TestClient, state: "HyperglassState"):
    first = client.post("/api/query", json=QUERY).json()
    key = state.redis.key(first["id"])
    assert 0 < state.redis.instance.ttl(key) <= state.params.cache.timeout

    state.redis.instance.expire(key, 5)
    second = client.post("/api/query", json=QUERY).json()
    assert second["cached"] is True
    assert second["output"] == first["output"]
    # A cache hit must not reset the expiration, or the response would never be refreshed.
    assert 0 < state.redis.instance.ttl(key) <= 5


@pytest.mark.parametrize("params", [{"fake_output": True, "cache": {"timeout": 0}}])
def test_query_cache_disabled(client: TestClient, state: "HyperglassState"):
    for _ in range(2):
        response = client.post("/api/query", json=QUERY).json()
        assert response["cached"] is False
        assert response["output"]["routes"]
    assert not state.redis.instance.exists(state.redis.key(response["id"]))


def test_query_device_name(client: TestClient):
    response = client.post("/api/query", json={**QUERY, "queryLocation": "Router 01"})
    assert response.status_code == 201
    assert response.json()["output"]["routes"]


def test_query_unknown_device(client: TestClient):
    response = client.post("/api/query", json={**QUERY, "queryLocation": "nope"})
    assert response.status_code == 400
    assert "nope" in response.json()["output"]


def test_query_validation_error(client: TestClient):
    body = {k: v for k, v in QUERY.items() if k != "queryTarget"}
    response = client.post("/api/query", json=body)
    assert response.status_code == 400
    assert response.json()["output"] == "queryTarget: Field required"


def test_query_no_query_parameters(client: TestClient):
    # Dependencies' parameters become request parameters.
    assert not client.app.openapi_schema.paths["/api/query"].post.parameters
    response = client.post("/api/query?attr=params", json=QUERY)
    assert response.status_code == 201


def test_device(client: TestClient):
    response = client.get("/api/devices/router01")
    assert response.status_code == 200
    assert response.json() == {"id": "router01", "name": "Router 01", "group": None}


def test_device_not_found(client: TestClient):
    response = client.get("/api/devices/nope")
    assert response.status_code == 404
    assert response.json()["output"] == "Location 'nope' not found."


def test_queries_are_query_types(client: TestClient):
    query_types = client.get("/api/queries").json()
    assert QUERY_TYPE in query_types
    for query_type in query_types:
        response = client.post("/api/query", json={**QUERY, "queryType": query_type})
        assert "not found" not in str(response.json()["output"])


def test_unhandled_error_without_redis(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def unavailable(*args: t.Any, **kwargs: t.Any) -> t.NoReturn:
        raise ConnectionError("Redis is unavailable")

    monkeypatch.setattr("hyperglass.api.error_handlers.use_state", unavailable)
    response = client.get("/error")
    assert response.status_code == 500
    assert response.json() == {
        "output": "Something went wrong.",
        "level": "danger",
        "keywords": [],
    }
