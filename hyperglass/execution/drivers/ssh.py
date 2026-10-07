"""Common Classes or Utilities for SSH Drivers."""

# Standard Library
import asyncio
from typing import TYPE_CHECKING, AsyncIterator
from contextlib import asynccontextmanager

# Third Party
import paramiko

# Project
from hyperglass.log import log
from hyperglass.state import use_state
from hyperglass.compat import BaseSSHTunnelForwarderError, open_tunnel
from hyperglass.exceptions.public import ScrapeError

# Local
from ._common import Connection

if TYPE_CHECKING:
    # Project
    from hyperglass.compat import SSHTunnelForwarder

# Errors raised when an SSH tunnel can't be set up, e.g. if the proxy is unreachable or rejects the
# credentials, or a key can't be loaded.
TUNNEL_ERRORS = (BaseSSHTunnelForwarderError, paramiko.SSHException, OSError, ValueError)


def _stop(tunnel: "SSHTunnelForwarder") -> None:
    """Stop an SSH tunnel, which may not have (fully) started."""
    try:
        tunnel.stop()
    except Exception as err:
        log.bind(error=str(err)).warning("Failed to stop SSH tunnel")


class SSHConnection(Connection):
    """Base class for SSH drivers."""

    @asynccontextmanager
    async def setup_proxy(self) -> AsyncIterator["SSHTunnelForwarder"]:
        """Open an SSH tunnel to the device through its proxy.

        Connecting to the proxy blocks, so the tunnel is opened & closed in a worker thread.
        """

        proxy = self.device.proxy
        params = use_state("params")

        tunnel_kwargs = {
            "ssh_username": proxy.credential.username,
            "remote_bind_address": (self.device._target, self.device.port),
            "local_bind_address": ("localhost", 0),
            "skip_tunnel_checkup": False,
            "gateway_timeout": params.request_timeout - 2,
        }
        if proxy.credential._method == "password":
            # Use password auth if no key is defined.
            tunnel_kwargs["ssh_password"] = proxy.credential.password.get_secret_value()
        else:
            # Otherwise, use key auth.
            tunnel_kwargs["ssh_pkey"] = proxy.credential.key.as_posix()
            if proxy.credential._method == "encrypted_key":
                # If the key is encrypted, use the password field as the
                # private key password.
                tunnel_kwargs["ssh_private_key_password"] = (
                    proxy.credential.password.get_secret_value()
                )
        loop = asyncio.get_running_loop()
        try:
            tunnel = open_tunnel(
                ssh_address_or_host=proxy._target, ssh_port=proxy.port, **tunnel_kwargs
            )
            # A worker thread can't be cancelled, e.g. when the request times out. If that happens,
            # the tunnel is stopped once it has started, so its SSH session isn't left open.
            started = loop.run_in_executor(None, tunnel.start)
            try:
                await asyncio.shield(started)
            except asyncio.CancelledError:
                started.add_done_callback(lambda _: loop.run_in_executor(None, _stop, tunnel))
                raise
            except TUNNEL_ERRORS:
                # Close anything opened before the error, e.g. the SSH session with the proxy.
                await asyncio.to_thread(_stop, tunnel)
                raise

        except TUNNEL_ERRORS as scrape_proxy_error:
            log.bind(device=self.device.name, proxy=proxy._target).error(
                "Failed to connect to device via proxy"
            )
            raise ScrapeError(error=scrape_proxy_error, device=self.device) from scrape_proxy_error

        try:
            yield tunnel
        finally:
            await asyncio.to_thread(_stop, tunnel)
