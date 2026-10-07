"""Validate RPKI state via Cloudflare GraphQL API."""

# Standard Library
import typing as t

# Project
from hyperglass.log import log
from hyperglass.state import use_state
from hyperglass.external._base import BaseExternal

if t.TYPE_CHECKING:
    # Standard Library
    from ipaddress import IPv4Address, IPv6Address, IPv4Network, IPv6Network

    # Project
    from hyperglass.state.redis import RedisManager

    Prefix = t.Union[IPv4Address, IPv6Address, IPv4Network, IPv6Network, str]

RPKI_STATE_MAP = {"Invalid": 0, "Valid": 1, "NotFound": 2, "DEFAULT": 3}
RPKI_NAME_MAP = {v: k for k, v in RPKI_STATE_MAP.items()}
CACHE_KEY = "hyperglass.external.rpki"
# Seconds a validation state is cached.
CACHE_TIMEOUT = 3600
# Seconds a failed lookup is cached. If the validator can't be reached, lookups are skipped for
# this long, so its timeout isn't added to every query (or every route).
FAILURE_TIMEOUT = 60
# Seconds to wait for the validator (once per batch of routes), as for other external requests.
REQUEST_TIMEOUT = 10
# Maximum number of routes validated per request.
BATCH_SIZE = 100


def _cache_name(cache: "RedisManager", item: str) -> str:
    """Get an item's cache key. Prefixes aren't split on `.`, unlike `RedisManager.key()`."""
    return f"{cache.key(CACHE_KEY)}:{item}"


def _validate(routes: t.Sequence[t.Tuple[str, int]]) -> t.List[t.Optional[int]]:
    """Get the RPKI state of each route in a single request, or `None` if one is missing."""
    fields = " ".join(
        f'r{i}: validation(prefix: "{prefix}", asn: {asn}) {{ state }}'
        for i, (prefix, asn) in enumerate(routes)
    )
    query = f"query GetValidation {{ {fields} }}"
    log.bind(query=query).debug("Cloudflare RPKI GraphQL Query")

    with BaseExternal(base_url="https://rpki.cloudflare.com", timeout=REQUEST_TIMEOUT) as client:
        response = client._post("/api/graphql", data={"query": query})

    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected response from Cloudflare: {response!r}")

    states = []
    for i, (prefix, asn) in enumerate(routes):
        state = (data.get(f"r{i}") or {}).get("state")
        if state not in RPKI_STATE_MAP:
            log.bind(prefix=prefix, asn=asn, result=data.get(f"r{i}")).error(
                "Response from Cloudflare missing state"
            )
        states.append(RPKI_STATE_MAP.get(state))
    return states


def rpki_states(routes: t.Sequence[t.Tuple["Prefix", t.Union[int, str]]]) -> t.List[int]:
    """Get the RPKI state of each (prefix, origin ASN) pair, mapped to the expected integer."""
    routes = [(str(prefix), int(asn)) for prefix, asn in routes]
    if not routes:
        return []

    cache = use_state("cache")
    names = [_cache_name(cache, f"{prefix}@{asn}") for prefix, asn in routes]
    unavailable = _cache_name(cache, "unavailable")

    states = {}
    for route, cached in zip(routes, cache.instance.mget(names)):
        if cached is not None:
            states[route] = int(cached)

    missing = list(dict.fromkeys(r for r in routes if r not in states))

    if missing and cache.instance.exists(unavailable):
        log.bind(routes=len(missing)).debug("Skipping RPKI validation, validator is unavailable")
        missing = []

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i : i + BATCH_SIZE]
        try:
            results = _validate(batch)
        except Exception as err:
            log.bind(error=str(err)).error("Unable to validate RPKI state")
            # Don't try again until the validator might be available again.
            cache.instance.set(unavailable, 1, ex=FAILURE_TIMEOUT)
            break

        with cache.instance.pipeline() as pipeline:
            for (prefix, asn), state in zip(batch, results):
                # Cache failed lookups too, but not for as long.
                timeout = FAILURE_TIMEOUT if state is None else CACHE_TIMEOUT
                state = 3 if state is None else state
                states[(prefix, asn)] = state
                pipeline.set(_cache_name(cache, f"{prefix}@{asn}"), state, ex=timeout)
            pipeline.execute()

    result = [states.get(route, 3) for route in routes]
    for (prefix, asn), state in zip(routes, result):
        log.debug("RPKI Validation State for {} via AS{} is {}", prefix, asn, RPKI_NAME_MAP[state])
    return result


def rpki_state(prefix: "Prefix", asn: t.Union[int, str]) -> int:
    """Get RPKI state and map to expected integer."""
    return rpki_states([(prefix, asn)])[0]
