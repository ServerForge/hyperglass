"""Tasks to be executed from web API."""

# Standard Library
import typing as t
from datetime import datetime

# Third Party
from httpx import Headers
from litestar import Request

# Project
from hyperglass.log import log
from hyperglass.external import Webhook, bgptools
from hyperglass.models.api import Query

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.config.params import Params

__all__ = ("send_webhook",)


async def process_headers(headers: Headers) -> t.Dict[str, t.Any]:
    """Filter out unwanted headers and return as a dictionary."""
    headers = dict(headers)
    header_keys = (
        "user-agent",
        "referer",
        "accept-encoding",
        "accept-language",
        "x-real-ip",
        "x-forwarded-for",
    )
    return {k: headers.get(k) for k in header_keys}


async def send_webhook(
    params: "Params",
    data: Query,
    request: Request,
    timestamp: datetime,
) -> t.NoReturn:
    """If webhooks are enabled, get request info and send a webhook."""
    try:
        if params.logging.http is not None and params.logging.http.enable:
            headers = await process_headers(headers=request.headers)

            # The client's address is taken from `X-Forwarded-For` only if the request is from a
            # trusted proxy (`HYPERGLASS_TRUSTED_PROXIES`); otherwise, any client could set it.
            host = request.client.host

            network_info = await bgptools.network_info(host)

            async with Webhook(params.logging.http) as hook:
                await hook.send(
                    query={
                        **data.dict(),
                        "headers": headers,
                        "source": host,
                        "network": network_info.get(host, {}),
                        "timestamp": timestamp,
                    }
                )
    except Exception as err:
        log.bind(destination=params.logging.http.provider, error=str(err)).error(
            "Failed to send webhook"
        )
