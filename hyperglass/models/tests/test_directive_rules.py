"""Test directive rule validation."""

# Third Party
import pytest

# Project
from hyperglass.exceptions.private import InputValidationError

# Local
from ..directive import RuleWithPattern


def test_permit_pattern_matches_whole_target():
    rule = RuleWithPattern(condition=r"65000:\d+", action="permit", command="show {target}")
    assert rule.validate_target("65000:100", multiple=False) is True
    assert rule.validate_target("65000:100 ; id", multiple=False) is False
    assert rule.validate_target(["65000:100", "65000:200"], multiple=True) is True
    assert rule.validate_target(["65000:100", "65000:1x"], multiple=True) is False
    assert rule.validate_target([], multiple=True) is False


def test_deny_pattern_matches_target_start():
    rule = RuleWithPattern(condition="65000:", action="deny", command="show {target}")
    with pytest.raises(InputValidationError):
        rule.validate_target("65000:100", multiple=False)
    with pytest.raises(InputValidationError):
        rule.validate_target(["64512:1", "65000:100"], multiple=True)
    assert rule.validate_target("64512:65000", multiple=False) is False
