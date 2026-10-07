"""Data Models for Parsing FRRouting JSON Response."""

# Standard Library
import time
import typing as t

# Third Party
from pydantic import ConfigDict, model_validator

# Project
from hyperglass.log import log
from hyperglass.models.data import BGPRouteTable

# Local
from ..main import HyperglassModel
from .common import split_communities


def _alias_generator(field):
    components = field.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class _FRRBase(HyperglassModel):
    model_config = ConfigDict(alias_generator=_alias_generator, extra="ignore")


class FRRNextHop(_FRRBase):
    """FRR Next Hop Model."""

    ip: str
    afi: str
    # FRR omits fields that don't apply, e.g. the link-local half of an IPv6 next hop pair has no
    # metric, and only the next hop in use is marked as `used`.
    scope: str = "global"
    metric: int = 0
    accessible: bool = False
    used: bool = False


class FRRPeer(_FRRBase):
    """FRR Peer Model."""

    peer_id: str
    router_id: str = ""
    type: t.Optional[str] = None


class FRRPath(_FRRBase):
    """FRR Path Model."""

    aspath: t.List[int] = []
    aggregator_as: int = 0
    aggregator_id: str = ""
    loc_prf: int = 100  # 100 is the default value for local preference
    metric: int = 0
    med: int = 0
    weight: int = 0
    # Only valid paths are marked as `valid`.
    valid: bool = False
    last_update: int
    bestpath: bool
    community: t.List[str] = []
    nexthops: t.List[FRRNextHop] = []
    peer: FRRPeer

    @model_validator(mode="before")
    def validate_path(cls, values):
        """Extract meaningful data from FRR response."""
        new = values.copy()
        # Include every segment, e.g. confederation segments & AS sets. Locally originated routes
        # have no segments.
        segments = values.get("aspath", {}).get("segments", [])
        new["aspath"] = [asn for segment in segments for asn in segment.get("list", [])]
        new["community"] = [
            *values.get("community", {}).get("list", []),
            *split_communities(values.get("extendedCommunity", {}).get("string")),
            *values.get("largeCommunity", {}).get("list", []),
        ]
        new["lastUpdate"] = values.get("lastUpdate", {}).get("epoch", int(time.time()))
        bestpath = values.get("bestpath", {})
        new["bestpath"] = bestpath.get("overall", False)
        return new

    @property
    def next_hop(self) -> str:
        """Get the path's next hop, preferring a global address over a link-local address."""
        nexthops = [n for n in self.nexthops if n.scope != "link-local"] or self.nexthops
        for nexthop in nexthops:
            if nexthop.used:
                return nexthop.ip
        return nexthops[0].ip if nexthops else ""


class FRRBGPTable(_FRRBase):
    """FRR Route Model."""

    prefix: str
    paths: t.List[FRRPath] = []

    def bgp_table(self):
        """Convert the FRR-specific fields to standard parsed data model."""

        # TODO: somehow, get the actual VRF
        vrf = "default"

        routes = []
        for route in self.paths:
            routes.append(
                {
                    "prefix": self.prefix,
                    "active": route.bestpath,
                    "age": int(time.time()) - route.last_update,
                    "weight": route.weight,
                    "med": route.med,
                    "local_preference": route.loc_prf,
                    "as_path": route.aspath,
                    "communities": route.community,
                    "next_hop": route.next_hop,
                    "source_as": route.aggregator_as,
                    "source_rid": route.aggregator_id,
                    "peer_rid": route.peer.peer_id,
                    # TODO: somehow, get the actual RPKI state
                    # This depends on whether or not the RPKI module is enabled in FRR
                    "rpki_state": 3,
                }
            )

        serialized = BGPRouteTable(
            vrf=vrf,
            count=len(routes),
            routes=routes,
            winning_weight="high",
        )

        log.bind(platform="frr", response=repr(serialized)).debug("Serialized response")
        return serialized
