"""Test system settings."""

# Standard Library
import os
from pathlib import Path
from ipaddress import ip_address

# Third Party
import pytest
from redis.connection import parse_url

# Project
from hyperglass.log import HyperglassConsole

# Local
from ..system import ENV_FILE_NAME, HyperglassSettings


@pytest.fixture(autouse=True)
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [*os.environ]:
        if name.upper().startswith("HYPERGLASS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("HYPERGLASS_APP_PATH", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("password", ("p@ss/w#rd", "with%20escape", "a:b?c&d=e"))
def test_redis_dsn_password(password: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYPERGLASS_REDIS_PASSWORD", password)
    settings = HyperglassSettings()
    connection = parse_url(str(settings.redis_dsn))
    assert connection["password"] == password
    assert connection["host"] == "localhost"
    assert connection["db"] == 1


def test_redis_dsn_ipv6(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYPERGLASS_REDIS_HOST", "::1")
    settings = HyperglassSettings()
    assert parse_url(str(settings.redis_dsn))["host"] == "::1"


def test_redis_dsn_masked(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYPERGLASS_REDIS_PASSWORD", "secret-password")
    settings = HyperglassSettings()
    assert "secret-password" not in repr(settings)
    with HyperglassConsole.capture() as capture:
        HyperglassConsole.print(settings)
    output = capture.get()
    assert "secret-password" not in output
    assert "redis://:********@localhost:6379/1" in output


@pytest.mark.parametrize(
    "value,expected",
    (("[::1]", "::1"), ("::1", "::1"), ("localhost", "::1"), ("192.0.2.1", "192.0.2.1")),
)
def test_host(value: str, expected: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HYPERGLASS_HOST", value)
    assert HyperglassSettings().host == ip_address(expected)


def test_env_file(environment: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = environment / ENV_FILE_NAME
    env_file.write_text("HYPERGLASS_PORT=9000\nHYPERGLASS_DEBUG=true\nUNRELATED=1\n")
    settings = HyperglassSettings()
    assert settings.port == 9000
    assert settings.debug is True

    # Environment variables take precedence over the file.
    monkeypatch.setenv("HYPERGLASS_PORT", "9001")
    assert HyperglassSettings().port == 9001


def test_env_file_missing():
    assert HyperglassSettings().port == 8001


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_env_file_unreadable(environment: Path):
    env_file = environment / ENV_FILE_NAME
    env_file.write_text("HYPERGLASS_PORT=9000\n")
    env_file.chmod(0o000)
    assert HyperglassSettings().port == 8001
