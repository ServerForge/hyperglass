"""Device-Agnostic Parsed Response Data Model."""

# Standard Library
import re
import typing as t
from ipaddress import ip_network

# Third Party
from pydantic import field_validator

# Project
from hyperglass.state import use_state
from hyperglass.external.rpki import rpki_states

# Local
from ..main import HyperglassModel

WinningWeight = t.Literal["low", "high"]


class BGPRoute(HyperglassModel):
    """Post-parsed BGP route."""

    prefix: str
    active: bool
    age: int
    weight: int
    med: int
    local_preference: int
    as_path: t.List[int]
    communities: t.List[str]
    next_hop: str
    source_as: int
    source_rid: str
    peer_rid: str
    rpki_state: int

    @field_validator("communities")
    def validate_communities(cls, value):
        """Filter returned communities against configured policy.

        Actions:
            permit: only permit matches
            deny: only deny matches
        """

        (structured := use_state("params").structured)

        def _permit(comm):
            """Only allow matching patterns."""
            valid = False
            for pattern in structured.communities.items:
                if re.fullmatch(pattern, comm):
                    valid = True
                    break
            return valid

        def _deny(comm):
            """Allow any except matching patterns."""
            valid = True
            for pattern in structured.communities.items:
                if re.fullmatch(pattern, comm):
                    valid = False
                    break
            return valid

        func_map = {"permit": _permit, "deny": _deny}
        func = func_map[structured.communities.mode]

        return [c for c in value if func(c)]


class BGPRouteTable(HyperglassModel):
    """Post-parsed BGP route table."""

    vrf: str
    count: int = 0
    routes: t.List[BGPRoute]
    winning_weight: WinningWeight

    def __init__(self, **kwargs):
        """Sort routes by prefix after validation."""
        super().__init__(**kwargs)
        self.routes = sorted(self.routes, key=lambda r: r.prefix)

        if use_state("params").structured.rpki.mode == "external":
            self.validate_rpki_states()

    def validate_rpki_states(self) -> None:
        """Get routes' RPKI states from Cloudflare's RPKI API, in a single request.

        Routes with non-global prefixes keep the RPKI state reported by the router.
        """
        external = []
        for route in self.routes:
            if len(route.as_path) == 0:
                # If the AS_PATH length is 0, i.e. for an internal route,
                # return RPKI Unknown state.
                route.rpki_state = 3
                continue
            try:
                net = ip_network(route.prefix)
            except ValueError:
                route.rpki_state = 3
                continue
            # Only do external RPKI lookups for global prefixes.
            if net.is_global:
                external.append(route)

        # Validate the prefix & last ASN in the path, i.e. the origin ASN.
        states = rpki_states([(route.prefix, route.as_path[-1]) for route in external])
        for route, state in zip(external, states):
            route.rpki_state = state

    def __add__(self: "BGPRouteTable", other: "BGPRouteTable") -> "BGPRouteTable":
        """Merge another BGP table instance with this instance."""
        if isinstance(other, BGPRouteTable):
            self.routes = sorted([*self.routes, *other.routes], key=lambda r: r.prefix)
            self.count = len(self.routes)
        return self
