"""API Routes."""

# Standard Library
import json
import time
import typing as t
from datetime import UTC, datetime

# Third Party
from litestar import Request, Response, get, post
from litestar.di import Provide
from litestar.exceptions import NotFoundException
from litestar.background_tasks import BackgroundTask

# Project
from hyperglass.log import log
from hyperglass.state import HyperglassState
from hyperglass.exceptions import HyperglassError, safe_format
from hyperglass.models.api import Query
from hyperglass.models.data import OutputDataModel
from hyperglass.util.typing import is_type
from hyperglass.execution.main import execute
from hyperglass.models.api.response import QueryResponse
from hyperglass.models.config.params import Params, APIParams
from hyperglass.models.config.devices import Devices, APIDevice

# Local
from .state import get_state, get_params, get_devices
from .tasks import send_webhook
from .fake_output import fake_output

__all__ = (
    "device",
    "devices",
    "queries",
    "info",
    "query",
)


@get(
    "/api/devices/{id:str}",
    dependencies={"devices": Provide(get_devices), "params": Provide(get_params)},
)
async def device(devices: Devices, params: Params, id: str) -> APIDevice:
    """Retrieve a device by ID."""
    try:
        return devices[id].export_api()
    except IndexError:
        message = safe_format(
            params.messages.not_found, type=params.web.text.query_location, name=id
        )
        raise NotFoundException(message) from None


@get("/api/devices", dependencies={"devices": Provide(get_devices)})
async def devices(devices: Devices) -> t.List[APIDevice]:
    """Retrieve all devices."""
    return devices.export_api()


@get("/api/queries", dependencies={"devices": Provide(get_devices)})
async def queries(devices: Devices) -> t.List[str]:
    """Retrieve all directive IDs, i.e. valid `queryType` values."""
    return list(dict.fromkeys(i for device in devices for i in device.directive_ids))


@get("/api/info", dependencies={"params": Provide(get_params)})
async def info(params: Params) -> APIParams:
    """Retrieve looking glass parameters."""
    return params.export_api()


@post("/api/query", dependencies={"_state": Provide(get_state)}, opt={"rate_limit": True})
async def query(_state: HyperglassState, request: Request, data: Query) -> QueryResponse:
    """Ingest request data pass it to the backend application to perform the query."""

    timestamp = datetime.now(UTC)

    # Each access of `_state.params` reads it from Redis.
    params = _state.params

    # Initialize cache
    cache = _state.redis

    # Use hashed `data` string as key for for k/v cache store so
    # each command output value is unique.
    cache_key = f"hyperglass.query.{data.digest()}"

    _log = log.bind(query=data.summary())

    _log.info("Starting query execution")

    output = cache.get_map(cache_key, "output")
    cached = False
    runtime = 65535

    if output is not None:
        _log.bind(cache_key=cache_key).debug("Cache hit")

        # The cached response's expiration isn't extended, so the cache is refreshed every
        # `cache.timeout` seconds, even if the query is repeated more often.
        cached = True
        runtime = 0
        timestamp = cache.get_map(cache_key, "timestamp")

    else:
        _log.bind(cache_key=cache_key).debug("Cache miss")

        timestamp = data.timestamp

        starttime = time.time()

        if params.fake_output:
            # Return fake, static data for development purposes, if enabled.
            result = await fake_output(
                query_type=data.query_type,
                structured=data.device.structured_output or False,
            )
        else:
            # Pass request to execution module
            result = await execute(data)

        endtime = time.time()
        elapsedtime = round(endtime - starttime, 4)
        _log.debug("Runtime: {!s} seconds", elapsedtime)

        if result is None:
            raise HyperglassError(message=params.messages.general, level="danger")

        if is_type(result, OutputDataModel):
            # Export structured output as JSON string to guarantee value
            # is serializable, then convert it back to a dict.
            output = json.loads(result.export_json())
        else:
            output = str(result)

        # A cache timeout of 0 disables caching.
        if params.cache.timeout > 0:
            with cache.pipeline() as pipeline:
                pipeline.set_map_item(cache_key, "output", output)
                pipeline.set_map_item(cache_key, "timestamp", timestamp)
                pipeline.expire(cache_key, expire_in=params.cache.timeout)

            _log.bind(cache_timeout=params.cache.timeout).debug("Response cached")

        runtime = int(round(elapsedtime, 0))

    json_output = is_type(output, t.Dict)
    response_format = "text/plain"

    if json_output:
        response_format = "application/json"
    _log.info("Execution completed")

    response = {
        "output": output,
        "id": cache_key,
        "cached": cached,
        "runtime": runtime,
        "timestamp": timestamp,
        "format": response_format,
        "random": data.random(),
        "level": "success",
        "keywords": [],
    }

    return Response(
        response,
        background=BackgroundTask(
            send_webhook,
            params=params,
            data=data,
            request=request,
            timestamp=timestamp,
        ),
    )
