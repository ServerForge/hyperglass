"""Test query target character validation."""

# Third Party
import pytest

# Project
from hyperglass.exceptions.private import InputValidationError

# Local
from ..api.query import validate_target_characters

VALID = (
    "192.0.2.0/24",
    "2001:db8::/32",
    "2001:db8::1",
    "65000:100",
    "65000:100:200",
    "target:65000:100",
    "no-export",
    "65000:.*",
    "_65000$",
    "^65000_",
    "^65000 65001$",
    ".* 65000 .*",
    "(65000|65001)$",
    "_(65000|65001)_",
    "_6500[0-9]_",
    "^[0-9]+$",
    "[= * 65000 * =]",
    "(65000,100)",
    "(65000,100,200)",
)

INVALID = (
    '1:1" ; id ; echo "',
    "1:1'; id",
    "1:1; id",
    "1:1 && id",
    "1:1`id`",
    "1:1$(id)",
    "1:1${IFS}id",
    "65000$HOME",
    "1:1\nshow running-config",
    "1:1\rreload",
    "1:1 | save /var/tmp/x",
    "1:1|/bin/sh",
    "_65000$|sh",
    "65000 > /tmp/x",
    "[/system reboot]",
    "[ :put 1]",
    '2001:db8::1%x" ; id ; "',
    "2001:db8::1%eth0",
    "1:1\\",
)


@pytest.mark.parametrize("target", VALID)
def test_valid_targets(target: str):
    validate_target_characters(target)


@pytest.mark.parametrize("target", INVALID)
def test_invalid_targets(target: str):
    with pytest.raises(InputValidationError):
        validate_target_characters(target)
