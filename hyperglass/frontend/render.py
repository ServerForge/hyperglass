"""Render configuration into a pre-built UI.

The UI is built without configuration. Configuration-dependent values are rendered as
placeholders (see `hyperglass/ui/pages/_document.tsx`), which are replaced at startup. This
allows configuration changes without a new UI build.
"""

# Standard Library
import re
import html
import shutil
import typing as t
from pathlib import Path

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.ui import UIParameters

PLACEHOLDER_PATTERN = re.compile(r"__HYPERGLASS_[A-Z_]+__")
CONFIG_PLACEHOLDER = "__HYPERGLASS_CONFIG__"
# Written to a UI build directory to identify the source it was built from.
BUILD_ID_FILE = ".hyperglass-build-id"
COLOR_MODES = ("light", "dark", "system")


class UIRenderError(Exception):
    """Raised when a UI build can't be rendered."""


def google_font_url(font_family: str, weights: t.Sequence[int] = (300, 400, 700)) -> str:
    """Get a Google Fonts stylesheet URL. Must match `googleFontUrl` in `ui/util/theme.ts`."""
    font_name = re.split(r", ", font_family)[0].strip().replace("'", "").replace('"', "")
    url_font = "+".join(font_name.split(" "))
    url_weights = ",".join(str(w) for w in weights)
    return f"https://fonts.googleapis.com/css?family={url_font}:{url_weights}&display=swap"


def _read(path: t.Optional[Path]) -> str:
    return path.read_text() if path is not None else ""


def _script_json(data: str) -> str:
    """Make a JSON string safe to embed in a `<script/>` element."""
    return data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def placeholder_values(params: "UIParameters") -> t.Dict[str, str]:
    """Get the rendered value of each placeholder, escaped for its context."""
    theme = params.web.theme
    color_mode = theme.default_color_mode or "system"
    if color_mode not in COLOR_MODES:
        raise UIRenderError(f"Invalid color mode '{color_mode}'")

    return {
        CONFIG_PLACEHOLDER: _script_json(params.export_json(by_alias=True)),
        "__HYPERGLASS_TITLE__": html.escape(params.site_title),
        "__HYPERGLASS_DESCRIPTION__": html.escape(params.site_description),
        "__HYPERGLASS_VERSION__": html.escape(params.version),
        "__HYPERGLASS_FONT_BODY__": html.escape(google_font_url(theme.fonts.body)),
        "__HYPERGLASS_FONT_MONO__": html.escape(google_font_url(theme.fonts.mono)),
        "__HYPERGLASS_COLOR_MODE__": color_mode,
        # Custom JS & HTML are operator-provided and intentionally inserted as-is.
        "__HYPERGLASS_CUSTOM_JS__": _read(params.web.custom_javascript),
        "__HYPERGLASS_CUSTOM_HTML__": _read(params.web.custom_html),
    }


def render_html(content: str, values: t.Mapping[str, str]) -> str:
    """Replace placeholders in a single pass, so inserted values are never re-substituted."""
    if CONFIG_PLACEHOLDER not in content:
        raise UIRenderError(
            "UI build does not contain configuration placeholders. "
            "Run `hyperglass build-ui` to create a new UI build."
        )

    def replace(match: re.Match) -> str:
        placeholder = match.group(0)
        if placeholder not in values:
            raise UIRenderError(f"Unknown UI placeholder '{placeholder}'")
        return values[placeholder]

    return PLACEHOLDER_PATTERN.sub(replace, content)


def render_ui(build_dir: Path, output_dir: Path, params: "UIParameters") -> None:
    """Copy a UI build to the output directory, rendering configuration into each HTML file."""
    values = placeholder_values(params)
    # Render all HTML first, so a failure leaves the existing output untouched.
    rendered = {
        path.relative_to(build_dir): render_html(path.read_text(), values)
        for path in build_dir.rglob("*.html")
    }
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(build_dir, output_dir, ignore=shutil.ignore_patterns(BUILD_ID_FILE))
    for path, content in rendered.items():
        (output_dir / path).write_text(content)

