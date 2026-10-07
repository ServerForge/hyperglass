"""Functions & handlers for external data."""

# Local
from .rpki import rpki_state
from ._base import BaseExternal
from .slack import SlackHook
from .msteams import MSTeams
from .bgptools import network_info, network_info_sync
from .webhooks import Webhook
from .http_client import HTTPClient

__all__ = (
    "BaseExternal",
    "HTTPClient",
    "MSTeams",
    "network_info_sync",
    "network_info",
    "rpki_state",
    "SlackHook",
    "Webhook",
)
