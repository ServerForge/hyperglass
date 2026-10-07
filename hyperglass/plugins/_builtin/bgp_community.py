"""Validate BGP community query targets."""

# Standard Library
import typing as t
from ipaddress import ip_address

# Third Party
from pydantic import PrivateAttr

# Local
from .._input import InputPlugin

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.api.query import Query

    # Local
    from .._input import InputPluginValidationReturn

_32BIT = 0xFFFFFFFF
_16BIT = 0xFFFF
EXTENDED_TYPES = ("target", "origin")
# Well-known communities, which most platforms accept by name.
WELL_KNOWN_COMMUNITIES = (
    "accept-own",
    "blackhole",
    "graceful-shutdown",
    "gshut",
    "internet",
    "llgr-stale",
    "local-as",
    "no-advertise",
    "no-export",
    "no-export-subconfed",
    "no-llgr",
    "no-peer",
)
# Platforms with built-in BGP community directives, e.g. `__hyperglass_juniper_bgp_community__`.
# BIRD isn't included, as its directive takes communities in BIRD's own syntax, e.g. `(65000,1)`.
COMMUNITY_DIRECTIVE_PLATFORMS = (
    "arista_eos",
    "cisco_ios",
    "cisco_nxos",
    "cisco_xr",
    "frr",
    "huawei",
    "juniper",
    "mikrotik",
    "nokia_sros",
    "openbgpd",
    "tnsr",
    "vyos",
)
# Platforms with built-in structured (table output) BGP community directives.
COMMUNITY_TABLE_DIRECTIVE_PLATFORMS = ("arista_eos", "juniper")


def check_decimal(value: str, size: int) -> bool:
    """Verify the value is a 32 bit number."""
    try:
        return abs(int(value)) <= size
    except Exception:
        return False


def check_string(value: str) -> bool:
    """Verify part of a community is an IPv4 address, per RFC4360."""
    try:
        addr = ip_address(value)
        return addr.version == 4
    except ValueError:
        return False


def validate_decimal(value: str) -> bool:
    """Verify a community is a 32 bit decimal number."""
    return check_decimal(value, _32BIT)


def validate_new_format(value: str) -> bool:
    """Verify a community matches "new" format, standard or extended."""
    if ":" in value:
        parts = [p for p in value.split(":") if p]
        if len(parts) == 3:
            if parts[0].lower() not in EXTENDED_TYPES:
                # Handle extended community format with `target:` or `origin:` prefix.
                return False
            # Remove type from parts list after it's been validated.
            parts = parts[1:]
        if len(parts) != 2:
            # Only allow two sections in new format, e.g. 65000:1
            return False

        one, two = parts

        if all((check_decimal(one, _16BIT), check_decimal(two, _16BIT))):
            # Handle standard format, e.g. `65000:1`
            return True
        if all((check_decimal(one, _16BIT), check_decimal(two, _32BIT))):
            # Handle extended format, e.g. `65000:4294967295`
            return True
        if all((check_string(one), check_decimal(two, _16BIT))):
            # Handle IP address format, e.g. `192.0.2.1:65000`
            return True

    return False


def validate_large_community(value: str) -> bool:
    """Verify a community matches "large" format. E.g., `65000:65001:65002`."""
    if ":" in value:
        parts = [p for p in value.split(":") if p]
        if len(parts) != 3:
            return False
        for part in parts:
            if not check_decimal(part, _32BIT):
                # Each member must be a 32 bit number.
                return False
        return True
    return False


def validate_well_known(value: str) -> bool:
    """Verify a community is a well-known community name, e.g. `no-export`."""
    return value.lower() in WELL_KNOWN_COMMUNITIES


def validate_community(value: str) -> bool:
    """Verify a value is a BGP community in any supported format."""
    validators = (
        validate_decimal,
        validate_new_format,
        validate_large_community,
        validate_well_known,
    )
    return any(validator(value) for validator in validators)


class ValidateBGPCommunity(InputPlugin):
    """Validate a BGP community string."""

    _hyperglass_builtin: bool = PrivateAttr(True)
    directives: t.Sequence[str] = (
        *(f"__hyperglass_{p}_bgp_community__" for p in COMMUNITY_DIRECTIVE_PLATFORMS),
        *(f"__hyperglass_{p}_bgp_community_table__" for p in COMMUNITY_TABLE_DIRECTIVE_PLATFORMS),
    )

    def validate(self, query: "Query") -> "InputPluginValidationReturn":
        """Ensure each query target is a valid BGP community, or space-separated communities."""

        # The UI sends targets as a list.
        targets = query.query_target
        if isinstance(targets, str):
            targets = [targets]
        if not isinstance(targets, (list, tuple)) or not all(isinstance(v, str) for v in targets):
            return None

        communities = [community for target in targets for community in target.split()]
        if len(communities) != 0 and all(validate_community(c) for c in communities):
            return True

        self.failure_reason = "Not a valid BGP community"
        return False
