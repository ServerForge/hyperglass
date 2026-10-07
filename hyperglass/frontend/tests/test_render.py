"""Test rendering configuration into a pre-built UI."""

# Standard Library
import json
from types import SimpleNamespace
from pathlib import Path

# Third Party
import pytest

# Local
from ..render import (
    BUILD_ID_FILE,
    UIRenderError,
    render_ui,
    render_html,
    google_font_url,
    placeholder_values,
)

TEMPLATE = """<html><head><title>__HYPERGLASS_TITLE__</title>
<meta content="__HYPERGLASS_TITLE__ - __HYPERGLASS_DESCRIPTION__"/>
<link href="__HYPERGLASS_FONT_BODY__"/><link href="__HYPERGLASS_FONT_MONO__"/>
<meta content="__HYPERGLASS_VERSION__"/>
<script id="hyperglass-config" type="application/json">__HYPERGLASS_CONFIG__</script>
<script id="custom-javascript">__HYPERGLASS_CUSTOM_JS__</script></head>
<body><script>m="__HYPERGLASS_COLOR_MODE__"</script>
<div id="custom-html">__HYPERGLASS_CUSTOM_HTML__</div></body></html>"""


def _params(tmp_path: Path, **overrides) -> SimpleNamespace:
    custom_html = tmp_path / "custom.html"
    custom_html.write_text("<p>__HYPERGLASS_TITLE__</p>")
    config = {"siteTitle": 'Title </script><script>alert("x")'}
    values = {
        "site_title": 'Title </script><script>alert("x")',
        "site_description": "Network & Looking Glass",
        "version": "2.0.4",
        "export_json": lambda by_alias: json.dumps(config),
        "web": SimpleNamespace(
            theme=SimpleNamespace(
                default_color_mode=None,
                fonts=SimpleNamespace(body="Nunito", mono="'Fira Code', monospace"),
            ),
            custom_javascript=None,
            custom_html=custom_html,
        ),
        **overrides,
    }
    return SimpleNamespace(**values)


def test_render_html(tmp_path: Path):
    result = render_html(TEMPLATE, placeholder_values(_params(tmp_path)))
    assert "__HYPERGLASS_" not in result.replace("<p>__HYPERGLASS_TITLE__</p>", "")
    # Values are escaped for their context.
    assert "<title>Title &lt;/script&gt;&lt;script&gt;alert(&quot;x&quot;)</title>" in result
    assert "Network &amp; Looking Glass" in result
    assert "family=Fira+Code:300,400,700&amp;display=swap" in result
    assert 'm="system"' in result
    # Embedded JSON can't close its script element & still parses to the original value.
    config = result.split('type="application/json">')[1].split("</script>")[0]
    assert "</script>" not in config
    assert json.loads(config) == {"siteTitle": 'Title </script><script>alert("x")'}
    # Inserted values are never re-substituted.
    assert '<div id="custom-html"><p>__HYPERGLASS_TITLE__</p></div>' in result
    assert '<script id="custom-javascript"></script>' in result


def test_render_html_without_placeholders(tmp_path: Path):
    with pytest.raises(UIRenderError, match="hyperglass build-ui"):
        render_html("<html></html>", placeholder_values(_params(tmp_path)))


def test_render_html_unknown_placeholder(tmp_path: Path):
    with pytest.raises(UIRenderError, match="__HYPERGLASS_UNKNOWN__"):
        render_html(TEMPLATE + "__HYPERGLASS_UNKNOWN__", placeholder_values(_params(tmp_path)))


@pytest.mark.parametrize(
    "font,expected",
    (
        ("Nunito", "Nunito"),
        ("'Fira Code', monospace", "Fira+Code"),
        ('"Open Sans", sans-serif', "Open+Sans"),
    ),
)
def test_google_font_url(font: str, expected: str):
    url = google_font_url(font)
    assert url == f"https://fonts.googleapis.com/css?family={expected}:300,400,700&display=swap"


def test_render_ui(tmp_path: Path):
    build = tmp_path / "build"
    (build / "_next").mkdir(parents=True)
    (build / "index.html").write_text(TEMPLATE)
    (build / "_next" / "app.js").write_text("js")
    (build / BUILD_ID_FILE).write_text("id")
    output = tmp_path / "output"
    (output / "stale").mkdir(parents=True)

    render_ui(build, output, _params(tmp_path))

    assert "__HYPERGLASS_CONFIG__" not in (output / "index.html").read_text()
    assert (output / "_next" / "app.js").read_text() == "js"
    assert not (output / BUILD_ID_FILE).exists()
    assert not (output / "stale").exists()
    # The build itself is unchanged, so it can be rendered again with new configuration.
    assert (build / "index.html").read_text() == TEMPLATE


def test_render_ui_failure_keeps_output(tmp_path: Path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("<html>outdated build</html>")
    output = tmp_path / "output"
    output.mkdir()
    (output / "index.html").write_text("previous")

    with pytest.raises(UIRenderError):
        render_ui(build, output, _params(tmp_path))
    assert (output / "index.html").read_text() == "previous"
