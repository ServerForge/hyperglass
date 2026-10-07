"""Parsing utilities shared by platform response models."""

# Standard Library
import re
import typing as t

if t.TYPE_CHECKING:
    # Third Party
    from pydantic import ValidationError

# A local AS number enclosed in brackets, e.g. Junos' `[65000] 65001 I`.
LOCAL_AS_PATTERN = re.compile(r"\[[^\]]*\]")
# Characters enclosing AS sets (`{}`) & confederation segments (`()`), and separating set members.
AS_PATH_DELIMITERS = re.compile(r"[{}()\[\],]")
ASPLAIN_PATTERN = re.compile(r"^\d+$")
ASDOT_PATTERN = re.compile(r"^(\d+)\.(\d+)$")


def parse_as_path(value: t.Optional[str], *, exclude_local: bool = False) -> t.List[int]:
    """Get all ASNs from an AS path string, including AS set & confederation members.

    Origin codes and other non-ASN tokens are ignored. For example,
    `65001 (65010 65011) {65003,65004} I` becomes `[65001, 65010, 65011, 65003, 65004]`.

    If `exclude_local` is `True`, bracketed local AS numbers, which aren't part of the received
    path, are excluded.
    """
    if not value:
        return []
    if exclude_local:
        value = LOCAL_AS_PATTERN.sub(" ", value)

    as_path = []
    for token in AS_PATH_DELIMITERS.sub(" ", value).split():
        if ASPLAIN_PATTERN.match(token):
            as_path.append(int(token))
        elif match := ASDOT_PATTERN.match(token):
            # Convert asdot notation, e.g. `1.10`, to asplain.
            high, low = match.groups()
            as_path.append(int(high) * 65536 + int(low))
    return as_path


def split_communities(value: t.Optional[str]) -> t.List[str]:
    """Split a string of space-separated communities into a list.

    Some extended communities contain spaces, e.g. `LB:65000:12500000 (100.000 Mbps)`. Tokens
    without a `:` are considered part of the previous community.
    """
    if not value:
        return []
    communities = []
    for token in value.split():
        if communities and ":" not in token:
            communities[-1] = f"{communities[-1]} {token}"
        else:
            communities.append(token)
    return communities


def validation_error_message(err: "ValidationError") -> str:
    """Summarize a response validation error, e.g. `paths.0.peer: Field required`."""
    return "; ".join(
        "{}: {}".format(".".join(str(loc) for loc in error["loc"]), error["msg"])
        for error in err.errors()
    )
