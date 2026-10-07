"""Test OpenGraph image generation & image migration."""

# Standard Library
import typing as t
from types import SimpleNamespace
from pathlib import Path

# Third Party
import pytest
from PIL import Image
from pydantic_extra_types.color import Color

# Local
from .. import migrate_images, generate_opengraph

BACKGROUND = "#102030"
BACKGROUND_RGB = (16, 32, 48)


def _generate(source: Path, target: Path, background: t.Any = BACKGROUND) -> Image.Image:
    target.mkdir(parents=True, exist_ok=True)
    generate_opengraph(source, 1200, 630, target, background)
    with Image.open(target / "opengraph.jpg") as image:
        assert image.format == "JPEG"
        image.load()
        return image


def _close(actual: t.Sequence[int], expected: t.Sequence[int], tolerance: int = 10) -> bool:
    """Compare pixels, allowing for JPEG compression artifacts."""
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


def _transparent_png(path: Path) -> Path:
    """Create an image with transparent *white* pixels around an opaque green square."""
    image = Image.new("RGBA", (400, 200), (255, 255, 255, 0))
    image.paste((0, 200, 0, 255), (150, 50, 250, 150))
    image.save(path)
    return path


def test_source_named_like_output(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "opengraph.jpg"
    Image.new("RGB", (1200, 630), (200, 30, 30)).save(source)
    original = source.read_bytes()

    image = _generate(source, tmp_path / "images")

    assert image.size == (1200, 630)
    assert source.read_bytes() == original
    assert [p.name for p in source_dir.iterdir()] == ["opengraph.jpg"]


def test_source_in_images_directory(tmp_path: Path):
    images = tmp_path / "images"
    images.mkdir()
    source = images / "my-og.png"
    Image.new("RGB", (2400, 1260), (200, 30, 30)).save(source)
    original = source.read_bytes()

    image = _generate(source, images)

    assert image.size == (1200, 630)
    assert source.read_bytes() == original
    assert sorted(p.name for p in images.iterdir()) == ["my-og.png", "opengraph.jpg"]


def test_source_is_output(tmp_path: Path):
    images = tmp_path / "images"
    images.mkdir()
    source = images / "opengraph.jpg"
    Image.new("RGB", (800, 400), (200, 30, 30)).save(source)
    original = source.read_bytes()

    generate_opengraph(source, 1200, 630, images, BACKGROUND)

    # The configured image is already the served image, so it's left untouched.
    assert source.read_bytes() == original


def test_other_images_unaffected(tmp_path: Path):
    """A source named like a migrated logo must not replace or delete that logo."""
    images = tmp_path / "images"
    images.mkdir()
    logo = images / "light.png"
    Image.new("RGB", (100, 50), (1, 2, 3)).save(logo)
    logo_bytes = logo.read_bytes()
    source = _transparent_png(tmp_path / "light.png")

    _generate(source, images)

    assert logo.read_bytes() == logo_bytes


def _palette(path: Path) -> None:
    Image.new("RGB", (600, 315), (200, 30, 30)).convert("P", palette=Image.Palette.ADAPTIVE).save(
        path
    )


def _palette_transparent(path: Path) -> None:
    _transparent_png(path.with_suffix(".rgba.png"))
    with Image.open(path.with_suffix(".rgba.png")) as image:
        image.convert("P").save(path, transparency=0)


def _gray16(path: Path) -> None:
    Image.new("I;16", (600, 315), 40000).save(path)


def _gray_alpha(path: Path) -> None:
    Image.new("LA", (600, 315), (100, 255)).save(path)


def _cmyk(path: Path) -> None:
    Image.new("CMYK", (600, 315), (0, 50, 50, 0)).save(path)


def _bilevel(path: Path) -> None:
    Image.new("1", (600, 315), 1).save(path)


@pytest.mark.parametrize(
    "name,create,expected",
    (
        ("palette.png", _palette, (200, 30, 30)),
        ("palette-transparent.png", _palette_transparent, None),
        # 40000 of 65535 is ~156 of 255, rather than being clipped to white.
        ("gray16.png", _gray16, (156, 156, 156)),
        ("gray-alpha.png", _gray_alpha, None),
        ("cmyk.jpg", _cmyk, None),
        ("bilevel.png", _bilevel, (255, 255, 255)),
    ),
)
def test_image_modes(
    tmp_path: Path,
    name: str,
    create: t.Callable[[Path], None],
    expected: t.Optional[t.Tuple[int, int, int]],
):
    source = tmp_path / name
    create(source)

    image = _generate(source, tmp_path / "images")

    assert image.mode == "RGB"
    if expected is not None:
        assert _close(image.getpixel((image.width // 2, image.height // 2)), expected)


@pytest.mark.parametrize("background", (BACKGROUND, Color(BACKGROUND)))
def test_transparency_uses_background(tmp_path: Path, background: t.Any):
    source = _transparent_png(tmp_path / "logo.png")

    image = _generate(source, tmp_path / "images", background)

    assert image.size == (1200, 630)
    # Transparent pixels (white, with no opacity) show the background color, not white.
    assert _close(image.getpixel((10, 10)), BACKGROUND_RGB)
    assert _close(image.getpixel((600 - 150, 315)), BACKGROUND_RGB)
    # Opaque pixels are kept.
    assert _close(image.getpixel((600, 315)), (0, 200, 0))


def test_migrate_images(tmp_path: Path):
    app_path = tmp_path / "app"
    images = app_path / "static" / "images"
    images.mkdir(parents=True)
    # A logo that's already in the images directory, at the path it's migrated to.
    light = images / "light.png"
    Image.new("RGB", (100, 50), (1, 2, 3)).save(light)
    light_bytes = light.read_bytes()
    dark = tmp_path / "logo-dark.png"
    Image.new("RGB", (100, 50), (4, 5, 6)).save(dark)
    favicon = tmp_path / "icon.png"
    Image.new("RGB", (64, 64), (7, 8, 9)).save(favicon)
    params = SimpleNamespace(
        web=SimpleNamespace(logo=SimpleNamespace(light=light, dark=dark, favicon=favicon))
    )

    migrate_images(app_path, params)

    assert light.read_bytes() == light_bytes
    assert (images / "dark.png").read_bytes() == dark.read_bytes()
    assert (images / "favicon.png").read_bytes() == favicon.read_bytes()
