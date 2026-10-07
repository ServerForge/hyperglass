"""Test RPKI data fetching."""

# Standard Library
import typing as t

# Third Party
import pytest

# Project
from hyperglass.state import use_state
from hyperglass.exceptions.private import ExternalError

# Local
from .. import rpki
from ..rpki import RPKI_NAME_MAP, rpki_state, rpki_states

TEST_STATES = (
    ("103.21.244.0/24", 13335, 0),
    ("1.1.1.0/24", 13335, 1),
    ("192.0.2.0/24", 65000, 2),
)

# Routes validated by a fake validator.
FAKE_ROUTES = (("198.51.100.0/24", 64496), ("203.0.113.0/24", 64497), ("2001:db8::/32", 64498))


class FakeValidator:
    """Stand-in for Cloudflare's RPKI API client, recording queries."""

    queries: t.List[str] = []
    response: t.Union[t.Dict[str, t.Any], Exception] = {}

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        pass

    def __enter__(self) -> "FakeValidator":
        """Enter session."""
        return self

    def __exit__(self, *args: t.Any) -> None:
        """Exit session."""

    def _post(self, endpoint: str, data: t.Dict[str, str]) -> t.Dict[str, t.Any]:
        self.queries.append(data["query"])
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def validator(monkeypatch) -> t.Generator[t.Type[FakeValidator], None, None]:
    cache = use_state("cache")

    def clear():
        keys = list(cache.instance.scan_iter(f"{cache.key(rpki.CACHE_KEY)}:*"))
        if keys:
            cache.instance.delete(*keys)

    clear()
    fake = type("Validator", (FakeValidator,), {"queries": [], "response": {}})
    monkeypatch.setattr(rpki, "BaseExternal", fake)
    yield fake
    clear()


@pytest.mark.dependency()
def test_rpki():
    for prefix, asn, expected in TEST_STATES:
        result = rpki_state(prefix, asn)
        result_name = RPKI_NAME_MAP.get(result, "No Name")
        expected_name = RPKI_NAME_MAP.get(expected, "No Name")
        assert result == expected, (
            "RPKI State for '{}' via AS{!s} '{}' ({}) instead of '{}' ({})".format(
                prefix, asn, result, result_name, expected, expected_name
            )
        )


def test_rpki_states_batched(validator):
    states = {"r0": {"state": "Valid"}, "r1": {"state": "Invalid"}, "r2": None}
    validator.response = {"data": states}

    assert rpki_states(FAKE_ROUTES) == [1, 0, 3]
    # All routes are validated in a single request.
    assert len(validator.queries) == 1
    assert 'r2: validation(prefix: "2001:db8::/32", asn: 64498)' in validator.queries[0]

    # Validation states are cached, & expire. Failed lookups are cached for less time.
    cache = use_state("cache")
    ttls = [cache.instance.ttl(rpki._cache_name(cache, f"{p}@{a}")) for p, a in FAKE_ROUTES]
    assert rpki.FAILURE_TIMEOUT < ttls[0] <= rpki.CACHE_TIMEOUT
    assert rpki.FAILURE_TIMEOUT < ttls[1] <= rpki.CACHE_TIMEOUT
    assert 0 < ttls[2] <= rpki.FAILURE_TIMEOUT

    assert rpki_states(FAKE_ROUTES) == [1, 0, 3]
    assert len(validator.queries) == 1


def test_rpki_validator_unavailable(validator):
    validator.response = ExternalError(message="Connection timed out", level="danger")

    assert rpki_states(FAKE_ROUTES) == [3, 3, 3]
    assert len(validator.queries) == 1

    # Lookups are skipped until the validator might be available again, so its timeout isn't
    # added to every query.
    assert rpki_state("192.0.2.0/24", 64499) == 3
    assert len(validator.queries) == 1
    cache = use_state("cache")
    assert 0 < cache.instance.ttl(rpki._cache_name(cache, "unavailable")) <= rpki.FAILURE_TIMEOUT
