"""Remove anything before the command if found in output."""

# Standard Library
import re
import typing as t

# Third Party
from pydantic import PrivateAttr

# Project
from hyperglass.types import Series

# Local
from .._output import OutputType, OutputPlugin

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.api.query import Query

# Mikrotik's pager prompt, e.g. `-- [Q quit|D dump|down]` or `-- [Q quit|D dump|C-z pause]`.
PAGER_PROMPT = re.compile(r"(-- )?\[Q quit\|D dump\|[^\]]*\]")


def normalize(line: str) -> str:
    """Normalize a line for comparison purposes."""
    # Remove all the newline characters (which differ line to line).
    normalized = " ".join(line.split())
    # Remove ansii characters that aren't caught by Netmiko.
    return re.sub(r"\\x1b\[\S{2}\s", "", normalized)


def remove_pager_prompts(lines: t.List[str]) -> t.List[str]:
    """Remove Mikrotik's unhelpful helpers from the output, and lines left empty by doing so."""
    result = []
    for line in lines:
        cleaned = PAGER_PROMPT.sub("", line)
        if cleaned != line and not cleaned.strip():
            continue
        result.append(cleaned)
    return result


class MikrotikGarbageOutput(OutputPlugin):
    """Parse Mikrotik output to remove garbage."""

    _hyperglass_builtin: bool = PrivateAttr(True)
    platforms: t.Sequence[str] = ("mikrotik_routeros", "mikrotik_switchos")
    directives: t.Sequence[str] = (
        "__hyperglass_mikrotik_bgp_aspath__",
        "__hyperglass_mikrotik_bgp_community__",
        "__hyperglass_mikrotik_bgp_route__",
        "__hyperglass_mikrotik_ping__",
        "__hyperglass_mikrotik_traceroute__",
    )

    def process(self, *, output: OutputType, query: "Query") -> Series[str]:
        """Parse Mikrotik output to remove garbage."""

        result = ()

        for each_output in output:
            all_lines = remove_pager_prompts(each_output.splitlines())

            # Skip leading empty lines, so the first line is the column row.
            while len(all_lines) != 0 and not all_lines[0].strip():
                all_lines.pop(0)

            words = " ".join(all_lines).split()
            if len(words) == 0 or words[-1] in ("DISTANCE", "STATUS"):
                # Mikrotik shows the columns with no rows if there is no data.
                # Rather than send back an empty table, send back an empty
                # response which is handled with a warning message.
                continue

            # Starting index for rows (after the column row).
            start = 1
            # Extract the column row.
            column_line = normalize(all_lines[0])
            # Compare against the normalized column row, even after it's re-assigned.
            column_key = column_line

            for i, line in enumerate(all_lines[1:], start=1):
                if column_key in normalize(line):
                    # Mikrotik often re-inserts the column row in the output,
                    # effectively 'starting over'. In that case, re-assign
                    # the column row and starting index to that point.
                    column_line = re.sub(r"\[\S{2}\s", "", line)
                    start = i + 1

            # Combine the column row and the data rows from the starting
            # index onward, re-joined with a single newline character.
            lines = [column_line, *all_lines[start:]]
            result += ("\n".join(lines),)

        return result
