"""hyperglass API middleware."""

# Standard Library
import typing as t

# Third Party
from redis.asyncio import Redis
from litestar.stores.redis import RedisStore
from litestar.config.cors import CORSConfig
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.config.compression import CompressionConfig

if t.TYPE_CHECKING:
    # Third Party
    from litestar import Request
    from litestar.stores.base import Store
    from litestar.middleware.base import DefineMiddleware

    # Project
    from hyperglass.state import HyperglassState

__all__ = ("create_cors_config", "create_rate_limit", "COMPRESSION_CONFIG")

COMPRESSION_CONFIG = CompressionConfig(backend="brotli", brotli_gzip_fallback=True)

REQUEST_LOG_MESSAGE = "REQ"
RESPONSE_LOG_MESSAGE = "RES"
REQUEST_LOG_FIELDS = ("method", "path", "path_params", "query")
RESPONSE_LOG_FIELDS = ("status_code",)


def create_cors_config(state: "HyperglassState") -> CORSConfig:
    """Create CORS configuration from parameters."""
    origins = state.params.cors_origins.copy()
    if state.settings.dev_mode:
        origins = [*origins, state.settings.dev_url, "http://localhost:3000"]

    return CORSConfig(
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


def is_rate_limited(request: "Request") -> bool:
    """Only rate limit route handlers that opt in, e.g. queries, which connect to devices."""
    return request.route_handler.opt.get("rate_limit", False)


def create_rate_limit(
    state: "HyperglassState",
) -> t.Tuple[t.List["DefineMiddleware"], t.Dict[str, "Store"]]:
    """Create query rate limiting middleware & its store from parameters."""
    rate_limit = state.params.rate_limit
    if not rate_limit.enable:
        return [], {}

    config = RateLimitConfig(
        rate_limit=(rate_limit.period, rate_limit.queries),
        check_throttle_handler=is_rate_limited,
    )
    # Store request history in Redis so the limit is shared by all workers.
    store = RedisStore(
        redis=Redis.from_url(str(state.settings.redis_dsn)),
        namespace="HYPERGLASS_RATE_LIMIT",
        handle_client_shutdown=True,
    )
    return [config.middleware], {config.store: store}
