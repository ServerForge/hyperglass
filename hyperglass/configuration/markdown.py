"""Markdown processing utility functions."""

# Standard Library
import typing as t
from pathlib import Path

# Project
from hyperglass.util import replace_placeholders

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models import HyperglassModel


def get_markdown(config: "HyperglassModel", default: str, params: t.Dict[str, t.Any]) -> str:
    """Get markdown file if specified, or use default.

    Placeholders for `params` keys (e.g. `{title}`) are replaced, all other text is kept as-is.
    """

    md = default
    if config.enable and config.file is not None:
        # with config_path.file
        if hasattr(config, "file") and isinstance(config.file, Path):
            with config.file.open("r") as config_file:
                md = config_file.read()

    return replace_placeholders(md, **params)
