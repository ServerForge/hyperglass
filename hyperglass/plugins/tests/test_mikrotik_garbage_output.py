"""Mikrotik Garbage Output Plugin Tests."""

# Local
from .._builtin.mikrotik_garbage_output import MikrotikGarbageOutput

HEADER = " #   DST-ADDRESS        GATEWAY         DISTANCE"
ROWS = [f" {i} ADb 10.{i}.0.0/16        192.0.2.{i}        20" for i in range(6)]
PAGER = "-- [Q quit|D dump|C-z pause]"


def _process(*output: str):
    return MikrotikGarbageOutput().process(output=output, query=None)


def test_mikrotik_pager_before_header():
    # Mikrotik starts over at the re-inserted column row, after the pager prompt.
    output = "\n".join([HEADER, ROWS[0], ROWS[1], PAGER, HEADER, *ROWS[2:]])
    assert _process(output) == ("\n".join([HEADER, *ROWS[2:]]),)


def test_mikrotik_pager_after_header():
    output = "\n".join([HEADER, ROWS[0], HEADER, ROWS[1], ROWS[2], PAGER, ROWS[3], ROWS[4]])
    assert _process(output) == ("\n".join([HEADER, *ROWS[1:5]]),)


def test_mikrotik_header_repeated():
    output = "\n".join([HEADER, ROWS[0], HEADER, ROWS[1], HEADER, ROWS[2]])
    assert _process(output) == ("\n".join([HEADER, ROWS[2]]),)


def test_mikrotik_empty_output():
    # Mikrotik shows the columns with no rows if there is no data.
    assert _process("\n", "", HEADER) == ()
    result = _process(HEADER, "\n".join([HEADER, ROWS[0]]))
    assert result == ("\n".join([" ".join(HEADER.split()), ROWS[0]]),)
