"""Validation model for query rate limiting."""

# Standard Library
import typing as t

# Third Party
from pydantic import Field

# Local
from ..main import HyperglassModel


class RateLimit(HyperglassModel):
    """Query rate limiting parameters."""

    enable: bool = Field(
        True,
        title="Enable Rate Limiting",
        description="Limit the number of queries a single client may submit.",
    )
    queries: int = Field(
        60,
        gt=0,
        title="Queries",
        description="Maximum number of queries a single client may submit per `period`. When querying multiple locations at once, each location counts as one query.",
    )
    period: t.Literal["second", "minute", "hour", "day"] = Field(
        "minute",
        title="Period",
        description="Time period over which `queries` is counted.",
    )
