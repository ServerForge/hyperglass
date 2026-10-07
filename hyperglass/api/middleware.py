"""hyperglass API middleware."""

# Standard Library
import typing as t
from ipaddress import IPv6Network, ip_address

# Third Party
from redis.asyncio import Redis
from litestar.enums import ScopeType
from litestar.exceptions import TooManyRequestsException
from litestar.config.cors import CORSConfig
from litestar.datastructures import MutableScopeHeaders
from litestar.middleware.base import AbstractMiddleware, DefineMiddleware
from litestar.config.compression import CompressionConfig

if t.TYPE_CHECKING:
    # Third Party
    from litestar import Request
    from litestar.types import ASGIApp, Message, Receive, Scope, Send

    # Project
    from hyperglass.state import HyperglassState

__all__ = ("create_cors_config", "create_rate_limit", "COMPRESSION_CONFIG")

COMPRESSION_CONFIG = CompressionConfig(backend="brotli", brotli_gzip_fallback=True)

REQUEST_LOG_MESSAGE = "REQ"
RESPONSE_LOG_MESSAGE = "RES"
REQUEST_LOG_FIELDS = ("method", "path", "path_params", "query")
RESPONSE_LOG_FIELDS = ("status_code",)

# Prefix of rate limit keys in Redis.
RATE_LIMIT_NAMESPACE = "hyperglass.rate_limit"
PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}

# Count a request & get the number of seconds until the count resets, atomically, so concurrent
# requests (e.g. handled by different workers) are always counted.
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


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


def client_identifier(request: "Request") -> str:
    """Identify a client by its address, or its /64 network if the address is IPv6.

    An IPv6 client is typically assigned a /64 network, and could otherwise use a different
    address for each request.
    """
    host = request.client.host if request.client else "127.0.0.1"
    try:
        address = ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(IPv6Network((int(address) >> 64 << 64, 64)))
    return str(address)


class RateLimitMiddleware(AbstractMiddleware):
    """Limit the number of requests a client may make per period.

    The count is stored in Redis, so the limit is shared by all workers.
    """

    def __init__(self, app: "ASGIApp", *, redis: Redis, limit: int, period: int) -> None:
        """Initialize the middleware."""
        super().__init__(app=app, scopes={ScopeType.HTTP})
        self.limit = limit
        self.period = period
        self.count_request = redis.register_script(RATE_LIMIT_SCRIPT)

    def headers(self, count: int, reset: int) -> t.Dict[str, str]:
        """Create rate limit response headers."""
        return {
            "RateLimit-Policy": f"{self.limit}; w={self.period}",
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(max(self.limit - count, 0)),
            "RateLimit-Reset": str(reset),
        }

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """Count & limit requests to route handlers that opt in."""
        request: "Request" = scope["litestar_app"].request_class(scope)
        if not is_rate_limited(request):
            await self.app(scope, receive, send)
            return

        key = f"{RATE_LIMIT_NAMESPACE}:{client_identifier(request)}"
        count, reset = await self.count_request(keys=[key], args=[self.period])
        headers = self.headers(count, reset)
        if count > self.limit:
            raise TooManyRequestsException(headers=headers)

        async def send_with_headers(message: "Message") -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                response_headers = MutableScopeHeaders(message)
                for name, value in headers.items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_rate_limit(
    state: "HyperglassState",
) -> t.Tuple[t.List[DefineMiddleware], t.List[t.Callable[[], t.Awaitable[None]]]]:
    """Create query rate limiting middleware from parameters, and its shutdown handlers."""
    rate_limit = state.params.rate_limit
    if not rate_limit.enable:
        return [], []

    redis = Redis.from_url(str(state.settings.redis_dsn))
    middleware = DefineMiddleware(
        RateLimitMiddleware,
        redis=redis,
        limit=rate_limit.queries,
        period=PERIODS[rate_limit.period],
    )

    async def close_redis() -> None:
        await redis.aclose()

    return [middleware], [close_redis]
