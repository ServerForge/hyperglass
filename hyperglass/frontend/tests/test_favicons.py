"""Test favicon generation."""

# Standard Library
import json
from pathlib import Path

# Third Party
import pytest
from PIL import Image

# Project
from hyperglass.models.config.web import Logo

# Local
from ..favicons import FAVICONS, favicon_filename, generate_favicons

UI_FAVICON_FORMATS = Path(__file__).parent.parent.parent / "ui" / "favicon-formats.ts"


def _check_output(output: Path) -> None:
    for favicon in FAVICONS:
        file = output / favicon_filename(favicon)
        assert file.exists()
        with Image.open(file) as image:
            assert image.format == favicon["image_format"].upper()
            assert image.size == favicon["dimensions"]
            # Rendered content must not be fully transparent.
            assert image.convert("RGBA").getbbox() is not None


def test_generate_from_default_svg(tmp_path: Path):
    generate_favicons(Logo().favicon, tmp_path)
    _check_output(tmp_path)


def test_generate_from_png(tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGB", (300, 200), (255, 0, 0)).save(source)
    output = tmp_path / "out"
    generate_favicons(source, output)
    _check_output(output)
    # Non-square sources keep their aspect ratio, centered on a transparent canvas.
    with Image.open(output / "favicon-64x64.png") as image:
        assert image.getpixel((32, 0))[3] == 0
        assert image.getpixel((32, 32)) == (255, 0, 0, 255)


def test_unsupported_format(tmp_path: Path):
    source = tmp_path / "source.gif"
    Image.new("RGB", (64, 64)).save(source)
    with pytest.raises(ValueError, match="Unsupported favicon format"):
        generate_favicons(source, tmp_path / "out")


def test_formats_match_ui():
    """Favicon definitions must match those the UI was built with."""
    content = UI_FAVICON_FORMATS.read_text()
    ui_formats = json.loads(content[content.index("[") : content.rindex(" as Favicon[]")])
    expected = [{**f, "dimensions": list(f["dimensions"])} for f in FAVICONS]
    assert ui_formats == expected
