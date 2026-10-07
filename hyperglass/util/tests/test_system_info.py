"""Test system information utilities."""

# Standard Library
import os
import shutil
import subprocess
from pathlib import Path

# Third Party
import pytest

# Local
from ..system_info import available_cpus, get_system_info, get_node_version


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


@pytest.mark.parametrize(
    "output,expected", (("v22.20.0\n", (22, 20, 0)), ("v23.0.0-nightly20241001", (23, 0, 0)))
)
def test_node_version(monkeypatch: pytest.MonkeyPatch, output: str, expected: tuple):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: output.encode())
    assert get_node_version() == expected


def test_node_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="NodeJS is not installed"):
        get_node_version()
    # NodeJS is only required to build the UI, so system information is still available.
    node_version, _ = get_system_info()["Node Version"]
    assert node_version.startswith("Not available")
