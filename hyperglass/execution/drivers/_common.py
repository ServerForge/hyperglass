"""Base Connection Class."""

# Standard Library
import typing as t
import asyncio
from abc import ABC, abstractmethod

# Project
from hyperglass.types import Series
from hyperglass.plugins import OutputPluginManager

# Local
from ._construct import Construct

if t.TYPE_CHECKING:
    # Project
    from hyperglass.compat import SSHTunnelForwarder
    from hyperglass.models.api import Query
    from hyperglass.models.data import OutputDataModel
    from hyperglass.models.config.devices import Device


class Connection(ABC):
    """Base transport driver class."""

    def __init__(self, device: "Device", query_data: "Query") -> None:
        """Initialize connection to device."""
        self.device = device
        self.query_data = query_data
        self.query_type = self.query_data.query_type
        self.query_target = self.query_data.query_target
        self._query = Construct(device=self.device, query=self.query_data)
        self.query = self._query.queries()
        self.plugin_manager = OutputPluginManager()

    @abstractmethod
    def setup_proxy(self: "Connection") -> t.AsyncContextManager["SSHTunnelForwarder"]:
        """Open an SSH tunnel to the device through its proxy, for the duration of the context."""
        pass

    async def response(self, output: Series[str]) -> t.Union["OutputDataModel", str]:
        """Send output through common parsers."""

        # Parsing can be slow & do network I/O (e.g. external RPKI validation), so run it in a
        # worker thread to avoid blocking the event loop.
        response = await asyncio.to_thread(
            self.plugin_manager.execute, output=output, query=self.query_data
        )

        if response is None:
            response = ()

        return response
