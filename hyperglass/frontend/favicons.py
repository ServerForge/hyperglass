"""Generate favicons in common sizes & formats from a single source image."""

# Standard Library
import io
import typing as t
from pathlib import Path

# Third Party
from PIL import Image

SUPPORTED_FORMATS = (".svg", ".jpeg", ".jpg", ".png", ".tiff", ".tif")

# Render SVGs larger than the largest favicon so every size is downscaled.
SVG_RENDER_WIDTH = 1024


class Favicon(t.TypedDict):
    """Favicon definition, consumed by the UI to render `<link/>` elements."""

    image_format: str
    dimensions: t.Tuple[int, int]
    prefix: str
    rel: t.Optional[str]


def _favicon(
    image_format: str, width: int, height: int, prefix: str, rel: t.Optional[str]
) -> Favicon:
    return {
        "image_format": image_format,
        "dimensions": (width, height),
        "prefix": prefix,
        "rel": rel,
    }


FAVICONS: t.Tuple[Favicon, ...] = (
    _favicon("ico", 64, 64, "favicon", None),
    *(_favicon("png", d, d, "favicon", "icon") for d in (16, 32, 64, 96, 180)),
    *(
        _favicon("png", d, d, "apple-touch-icon", "apple-touch-icon")
        for d in (57, 60, 72, 76, 114, 120, 144, 152, 167, 180)
    ),
    *(
        _favicon("png", w, h, "mstile", None)
        for w, h in ((70, 70), (270, 270), (310, 310), (310, 150))
    ),
    _favicon("png", 196, 196, "favicon", "shortcut icon"),
)


def favicon_filename(favicon: Favicon) -> str:
    """Get a favicon's file name, e.g. `favicon-32x32.png` or `favicon.ico`."""
    if favicon["image_format"] == "ico":
        return f"{favicon['prefix']}.ico"
    width, height = favicon["dimensions"]
    return f"{favicon['prefix']}-{width}x{height}.{favicon['image_format']}"


def load_source(source: Path) -> Image.Image:
    """Load a source image as RGBA, rasterizing SVGs."""
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported favicon format '{source.suffix}'. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
        )
    if source.suffix.lower() == ".svg":
        # Third Party
        import resvg_py

        png = resvg_py.svg_to_bytes(svg_path=str(source), width=SVG_RENDER_WIDTH)
        return Image.open(io.BytesIO(bytes(png))).convert("RGBA")

    with Image.open(source) as image:
        return image.convert("RGBA")


def render_favicon(source: Image.Image, dimensions: t.Tuple[int, int]) -> Image.Image:
    """Fit a source image within dimensions, centered on a transparent canvas."""
    image = source.copy()
    image.thumbnail(dimensions, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", dimensions, (0, 0, 0, 0))
    canvas.paste(image, ((dimensions[0] - image.width) // 2, (dimensions[1] - image.height) // 2))
    return canvas


def generate_favicons(source: Path, output_directory: Path) -> t.Tuple[Favicon, ...]:
    """Write all favicons for a source image to a directory."""
    output_directory.mkdir(parents=True, exist_ok=True)
    image = load_source(source)
    for favicon in FAVICONS:
        rendered = render_favicon(image, favicon["dimensions"])
        rendered.save(output_directory / favicon_filename(favicon), favicon["image_format"])
    return FAVICONS
