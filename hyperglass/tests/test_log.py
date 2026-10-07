"""Test logging configuration."""

# Standard Library
import io
import os
import sys
import logging
import typing as t
from pathlib import Path

# Third Party
import pytest
from rich.console import Console
from rich.logging import RichHandler

# Project
from hyperglass import log as log_module
from hyperglass.log import log, formatter, configure_logging
from hyperglass.models.config.logging import Logging


@pytest.fixture(autouse=True)
def restore_logging() -> t.Generator[None, None, None]:
    yield
    log.remove()
    log.add(sys.stderr)


def test_formatter_braces():
    output = io.StringIO()
    log.remove()
    log.add(RichHandler(console=Console(file=output, width=200)), format=formatter)
    log.bind(target="{1,2}").info("extra with braces")
    log.info("message with {master} braces")
    # Messages containing braces must not be dropped.
    assert "extra with braces target='{1,2}'" in output.getvalue()
    assert "message with {master} braces" in output.getvalue()


def test_configure_logging_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(log_module, "_configured_pid", None)
    params = Logging(directory=tmp_path)

    configure_logging(logging.INFO, params=params, header=False)
    # Logging is configured once per process, e.g. by the process starting the web server, and
    # isn't configured again when the app is loaded in the same process.
    configure_logging(logging.INFO, params=params)
    log.debug("debug message")
    log.info("info message")
    log.complete()

    content = (tmp_path / "hyperglass.log").read_text()
    assert content.count("info message") == 1
    assert "debug message" not in content
    assert "# hyperglass" not in content


def test_configure_logging_new_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # e.g. a web server worker process.
    monkeypatch.setattr(log_module, "_configured_pid", os.getpid() + 1)
    configure_logging(logging.DEBUG, params=Logging(directory=tmp_path))
    log.debug("debug message")
    log.complete()
    assert "debug message" in (tmp_path / "hyperglass.log").read_text()
