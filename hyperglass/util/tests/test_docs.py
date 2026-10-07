"""Test docs utilities."""

# Standard Library
import json
from pathlib import Path

# Local
from ..docs import create_platform_list


def test_create_platform_list(tmp_path: Path):
    file_ = tmp_path / "platforms.json"
    create_platform_list(file_)
    platforms = json.loads(file_.read_text())
    native = {p["name"]: p["keys"] for p in platforms if p["native"]}
    assert "juniper" in native["Juniper Junos"]
    assert any(not p["native"] for p in platforms)
