"""Test system information utilities."""

# Standard Library
import os
from pathlib import Path

# Third Party
import pytest

# Local
from ..system_info import available_cpus


@pytest.mark.parametrize(
    "cpu_max,expected",
    (
        ("max 100000", 8),
        ("200000 100000", 2),
        ("150000 100000", 2),
        ("50000 100000", 1),
        (None, 8),
    ),
)
def test_available_cpus(monkeypatch: pytest.MonkeyPatch, cpu_max: str, expected: int):
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: set(range(8)), raising=False)
    read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        if self == Path("/sys/fs/cgroup/cpu.max"):
            if cpu_max is None:
                raise FileNotFoundError(self)
            return cpu_max
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert available_cpus() == expected
