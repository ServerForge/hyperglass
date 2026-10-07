"""Session handler for Microsoft Teams API."""

# Standard Library
import typing as t

# Project
from hyperglass.log import log
from hyperglass.external._base import BaseWebhook
from hyperglass.models.webhook import Webhook

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.config.logging import Http


class MSTeams(BaseWebhook, name="MSTeams"):
    """Microsoft Teams session handler."""

    def __init__(self: "MSTeams", config: "Http") -> None:
        """Initialize external base class with Microsoft Teams connection details."""

        super().__init__(config=config, parse=False)

    async def send(self: "MSTeams", query: t.Dict[str, t.Any]):
        """Send an incoming webhook to Microsoft Teams."""

        payload = Webhook(**query)
        log.bind(destination="MS Teams", payload=payload).debug("Sending request")

        return await self._send(payload.msteams())
