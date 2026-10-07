"""Utility functions for gathering system information."""

# Standard Library
import os
import sys
import math
import typing as t
import platform
from pathlib import Path

# Third Party
import psutil as _psutil
from cpuinfo import get_cpu_info as _get_cpu_info  # type: ignore

# Project
from hyperglass.constants import __version__

SystemData = t.Dict[str, t.Tuple[t.Union[str, int], str]]


def _cpu() -> SystemData:
    """Construct CPU Information."""
    cpu_info = _get_cpu_info()
    brand = cpu_info.get("brand_raw", "")
    cores_logical = _psutil.cpu_count()
    cores_raw = _psutil.cpu_count(logical=False)
    # TODO: this is currently broken for M1 Macs, check status of: https://github.com/giampaolo/psutil/issues/1892
    cpu_ghz = _psutil.cpu_freq().current / 1000
    return (brand, cores_logical, cores_raw, cpu_ghz)


def _memory() -> SystemData:
    """Construct RAM Information."""
    mem_info = _psutil.virtual_memory()
    total_gb = round(mem_info.total / 1e9, 2)
    usage_percent = mem_info.percent
    return (total_gb, usage_percent)


def _disk() -> SystemData:
    """Construct Disk Information."""
    disk_info = _psutil.disk_usage("/")
    total_gb = round(disk_info.total / 1e9, 2)
    usage_percent = disk_info.percent
    return (total_gb, usage_percent)


def get_node_version() -> t.Tuple[int, int, int]:
    """Get the system's NodeJS version.

    Raises:
        RuntimeError: If NodeJS isn't installed, or its version can't be determined.
    """

    # Standard Library
    import re
    import shutil
    import subprocess

    node_path = shutil.which("node")
    if node_path is None:
        raise RuntimeError("NodeJS is not installed, or 'node' is not in PATH")

    raw_version = subprocess.check_output([node_path, "--version"]).decode()  # noqa: S603

    # Node returns the version as 'v14.5.0', for example.
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw_version)
    if match is None:
        raise RuntimeError(f"Unable to determine NodeJS version from {raw_version.strip()!r}")
    major, minor, patch = (int(v) for v in match.groups())
    return (major, minor, patch)


def _node_version() -> str:
    """Get the system's NodeJS version as a string, for display."""
    try:
        return ".".join(str(v) for v in get_node_version())
    except Exception as err:
        # NodeJS is only needed to build the UI, so its absence shouldn't break system-info.
        return f"Not available ({err})"


def available_cpus() -> int:
    """Get the number of CPUs available to this process.

    Unlike `os.cpu_count()`, this respects CPU affinity & container (cgroup v2) CPU limits.
    """
    try:
        count = len(os.sched_getaffinity(0))
    except AttributeError:
        count = os.cpu_count() or 1
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            count = min(count, max(1, math.ceil(int(quota) / int(period))))
    except (OSError, ValueError):
        pass
    return count


def cpu_count(multiplier: int = 0) -> int:
    """Get server's CPU core count.

    Used to determine the number of web server workers.
    """
    # Standard Library
    import multiprocessing

    return multiprocessing.cpu_count() * multiplier


def check_python() -> str:
    """Verify Python Version."""
    # Project
    from hyperglass.constants import MIN_PYTHON_VERSION

    pretty_version = ".".join(tuple(str(v) for v in MIN_PYTHON_VERSION))
    running_version = ".".join(
        str(v) for v in (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    )
    if sys.version_info < MIN_PYTHON_VERSION:
        raise RuntimeError(f"Python {pretty_version}+ is required (Running {running_version})")
    return running_version


def get_system_info() -> SystemData:
    """Get system info."""
    # Project
    from hyperglass.settings import Settings

    cpu_info, cpu_logical, cpu_physical, cpu_speed = _cpu()
    mem_total, mem_usage = _memory()
    disk_total, disk_usage = _disk()

    return {
        "hyperglass Version": (__version__, "text"),
        "hyperglass Path": (str(Settings.app_path), "code"),
        "Python Version": (platform.python_version(), "code"),
        "Node Version": (_node_version(), "code"),
        "Platform Info": (platform.platform(), "code"),
        "CPU Info": (cpu_info, "text"),
        "Logical Cores": (cpu_logical, "code"),
        "Physical Cores": (cpu_physical, "code"),
        "Processor Speed": (f"{cpu_speed}GHz", "code"),
        "Total Memory": (f"{mem_total} GB", "text"),
        "Memory Utilization": (f"{mem_usage}%", "text"),
        "Total Disk Space": (f"{disk_total} GB", "text"),
        "Disk Utilization": (f"{disk_usage}%", "text"),
    }
