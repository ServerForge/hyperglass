"""Remove anything before the command if found in output."""

# Standard Library
from typing import TYPE_CHECKING, List, Sequence

# Third Party
from pydantic import PrivateAttr

# Project
from hyperglass.log import log
from hyperglass.util.typing import is_series
from hyperglass.exceptions import HyperglassError

# Local
from .._output import OutputType, OutputPlugin

if TYPE_CHECKING:
    # Project
    from hyperglass.models.api.query import Query


def remove_command(output: str, commands: Sequence[str]) -> str:
    """Remove each line up to & including the last line containing a command, if any."""
    lines = output.splitlines()
    for idx in reversed(range(len(lines))):
        if any(command in lines[idx] for command in commands):
            return "\n".join(lines[idx + 1 :])
    return output


class RemoveCommand(OutputPlugin):
    """Remove anything before the command if found in output."""

    _hyperglass_builtin: bool = PrivateAttr(True)
    # Applies to all directives on all platforms.
    common: bool = True

    @staticmethod
    def _commands(query: "Query") -> List[str]:
        """Get the commands sent to the device, with the query target & attributes rendered."""
        # Project
        from hyperglass.execution.drivers._construct import Construct

        try:
            return Construct(device=query.device, query=query).queries()
        except HyperglassError as err:
            log.bind(error=str(err)).debug("Unable to determine commands to remove")
            return []

    def process(self, *, output: OutputType, query: "Query") -> OutputType:
        """Remove anything before the command if found in output."""

        # Only unstructured output from SSH devices may contain the echoed command.
        if not is_series(output) or query.device.driver == "hyperglass_http_client":
            return output

        commands = [c.strip() for c in self._commands(query) if c.strip()]
        if not commands:
            return output

        return tuple(remove_command(o, commands) if isinstance(o, str) else o for o in output)
