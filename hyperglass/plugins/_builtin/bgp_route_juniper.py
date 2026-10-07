"""Coerce a Juniper route table in XML format to a standard BGP Table structure."""

# Standard Library
import re
from typing import TYPE_CHECKING, Any, Dict, List, Union, Sequence, Generator

# Third Party
import xmltodict  # type: ignore
from pydantic import PrivateAttr, ValidationError

# Project
from hyperglass.log import log
from hyperglass.exceptions.private import ParsingError
from hyperglass.models.parsing.common import validation_error_message
from hyperglass.models.parsing.juniper import JuniperBGPTable

# Local
from .._output import OutputPlugin

if TYPE_CHECKING:
    # Standard Library
    from collections import OrderedDict

    # Project
    from hyperglass.models.data import OutputDataModel
    from hyperglass.models.api.query import Query

    # Local
    from .._output import OutputType


REMOVE_PATTERNS = (
    # The XML response can a CLI banner appended to the end of the XML
    # string. For example:
    # ```
    # <rpc-reply>
    # ...
    # <cli>
    #   <banner>{master}</banner>
    # </cli>
    # </rpc-reply>
    #
    # {master} noqa: E800
    # ```
    #
    # This pattern will remove lines consisting only of a banner, i.e. text inside braces. Braces
    # elsewhere, such as AS sets in an AS path, are kept.
    r"^\{[^{}]*\}$",
)


def clean_xml_output(output: str) -> str:
    """Remove Juniper-specific patterns from output."""

    def scrub(lines: List[str]) -> Generator[str, None, None]:
        """Clean & remove each pattern from each line."""
        for line in lines:
            # Strip extra whitespace & remove the patterns.
            scrubbed = line.strip()
            for pattern in REMOVE_PATTERNS:
                scrubbed = re.sub(pattern, "", scrubbed)
            # Only return non-empty and non-newline lines
            if scrubbed and scrubbed != "\n":
                yield scrubbed

    lines = scrub(output.splitlines())

    return "\n".join(lines)


def device_error_message(error: Union[Dict[str, Any], List[Dict[str, Any]], str]) -> str:
    """Get the message(s) from a Junos `xnm:error` element."""
    errors = error if isinstance(error, list) else [error]
    messages = (e.get("message") if isinstance(e, dict) else e for e in errors)
    return "; ".join(str(message).strip() for message in messages if message)


def parse_juniper(output: Sequence[str]) -> "OutputDataModel":  # noqa: C901
    """Parse a Juniper BGP XML response."""
    result = None

    _log = log.bind(plugin=BGPRoutePluginJuniper.__name__)
    for response in output:
        cleaned = clean_xml_output(response)

        try:
            parsed: "OrderedDict" = xmltodict.parse(
                cleaned, force_list=("rt", "rt-entry", "community")
            )
            if "rpc-reply" in parsed.keys():
                reply = parsed["rpc-reply"] or {}
                if "xnm:error" in reply:
                    raise ParsingError(
                        'Error from device: "{error}"',
                        error=device_error_message(reply["xnm:error"]) or "unknown error",
                    )

                parsed_base = reply["route-information"]
            elif "route-information" in parsed.keys():
                parsed_base = parsed["route-information"]
            else:
                raise KeyError("route-information")

            if not parsed_base or "route-table" not in parsed_base:
                # No routes matched the query in this table, e.g. for this address family.
                continue

            tables = parsed_base["route-table"]
            if not isinstance(tables, list):
                tables = [tables]

            for table in tables:
                if not table or "rt" not in table:
                    continue

                validated = JuniperBGPTable(**table)
                bgp_table = validated.bgp_table()

                if result is None:
                    result = bgp_table
                else:
                    result += bgp_table

        except xmltodict.expat.ExpatError as err:
            _log.bind(error=str(err)).critical("Failed to decode XML")
            raise ParsingError("Error parsing response data") from err

        except KeyError as err:
            _log.bind(key=str(err)).critical("Missing required key in response")
            raise ParsingError("{key} was not found in the response", key=str(err)) from err

        except ValidationError as err:
            _log.critical(err)
            raise ParsingError(
                "Error parsing response data: {error}", error=validation_error_message(err)
            ) from err

    return result


class BGPRoutePluginJuniper(OutputPlugin):
    """Coerce a Juniper route table in XML format to a standard BGP Table structure."""

    _hyperglass_builtin: bool = PrivateAttr(True)
    platforms: Sequence[str] = ("juniper",)
    directives: Sequence[str] = (
        "__hyperglass_juniper_bgp_route_table__",
        "__hyperglass_juniper_bgp_aspath_table__",
        "__hyperglass_juniper_bgp_community_table__",
    )

    def process(self, *, output: "OutputType", query: "Query") -> "OutputType":
        """Parse Juniper response if data is a string (and is therefore unparsed)."""
        should_process = all(
            (
                isinstance(output, (list, tuple)),
                query.device.platform in self.platforms,
                query.device.structured_output is True,
                query.device.has_directives(*self.directives),
            )
        )
        if should_process:
            return parse_juniper(output)
        return output
