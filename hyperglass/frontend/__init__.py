"""Utility functions for frontend-related tasks."""

# Standard Library
import os
import math
import shutil
import typing as t
import asyncio
import hashlib
from pathlib import Path

# Project
from hyperglass.log import log
from hyperglass.util import copyfiles, check_path

# Local
from .render import BUILD_ID_FILE, render_ui
from .favicons import generate_favicons

if t.TYPE_CHECKING:
    # Project
    from hyperglass.models.ui import UIParameters

UI_DIR = Path(__file__).parent.parent / "ui"
UI_BUILD_DIR = UI_DIR / "out"
# Files & directories that determine the UI build's output.
UI_SOURCES = (
    "components",
    "context",
    "elements",
    "hooks",
    "pages",
    "public",
    "types",
    "util",
    "favicon-formats.ts",
    "next.config.js",
    "package.json",
    "pnpm-lock.yaml",
    "tsconfig.json",
)


def get_ui_build_timeout() -> t.Optional[int]:
    """Read the UI build timeout from environment variables or set a default."""
    timeout = None

    if "HYPERGLASS_UI_BUILD_TIMEOUT" in os.environ:
        timeout = int(os.environ["HYPERGLASS_UI_BUILD_TIMEOUT"])
        log.bind(timeout=timeout).debug("Found UI build timeout environment variable")

    return timeout


def ui_source_hash() -> str:
    """Create a hash of the UI source, used to determine if a new UI build is required."""
    digest = hashlib.sha256()
    for source in UI_SOURCES:
        path = UI_DIR / source
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else (path,)
        for file in files:
            digest.update(file.relative_to(UI_DIR).as_posix().encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def ui_build_current() -> bool:
    """Determine if the existing UI build was built from the current UI source."""
    build_id = UI_BUILD_DIR / BUILD_ID_FILE
    return build_id.exists() and build_id.read_text().strip() == ui_source_hash()


async def run_ui_command(command: str, timeout: int, **env: str) -> str:
    """Run a command in the UI directory, raising an error if it fails or times out."""
    env_timeout = get_ui_build_timeout()
    if env_timeout is not None and env_timeout > timeout:
        timeout = env_timeout

    proc = await asyncio.create_subprocess_shell(
        cmd=command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=UI_DIR,
        env={**os.environ, **env},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as err:
        proc.kill()
        raise RuntimeError(f"{timeout} second timeout exceeded running '{command}'") from err

    messages = stdout.decode("utf-8").strip()
    if proc.returncode != 0:
        errors = stderr.decode("utf-8").strip()
        raise RuntimeError(f"'{command}' failed\nMessages:\n{messages}\nErrors:\n{errors}")
    return messages


async def build_ui(timeout: int = 180, force: bool = False) -> bool:
    """Build the UI if its source has changed since the last build.

    The UI is built without configuration, so configuration changes never require a new build.

    Returns:
        `True` if a new UI build was created.
    """
    if not force and ui_build_current():
        log.debug("UI build is current, skipping UI build")
        return False

    log.info("Starting UI build")
    build_id = ui_source_hash()

    # Configuration written in development mode must not be included in a UI build.
    (UI_DIR / "hyperglass.json").unlink(missing_ok=True)

    await run_ui_command("pnpm install --frozen-lockfile", timeout)
    log.debug(await run_ui_command("node_modules/.bin/next build", timeout, NODE_ENV="production"))

    (UI_BUILD_DIR / BUILD_ID_FILE).write_text(build_id)
    log.info("Completed UI build")
    return True


def generate_opengraph(
    image_path: Path,
    max_width: int,
    max_height: int,
    target_path: Path,
    background_color: str,
):
    """Generate an OpenGraph compliant image."""
    # Third Party
    from PIL import Image

    def center_point(background: Image, foreground: Image):
        """Generate a tuple of center points for PIL."""
        bg_x, bg_y = background.size[0:2]
        fg_x, fg_y = foreground.size[0:2]
        x1 = math.floor((bg_x / 2) - (fg_x / 2))
        y1 = math.floor((bg_y / 2) - (fg_y / 2))
        x2 = math.floor((bg_x / 2) + (fg_x / 2))
        y2 = math.floor((bg_y / 2) + (fg_y / 2))
        return (x1, y1, x2, y2)

    # Convert image to JPEG format with static name "opengraph.jpg"
    dst_path = target_path / "opengraph.jpg"

    # Copy the original image to the target path
    copied = shutil.copy2(image_path, target_path)
    log.bind(source=str(image_path), destination=str(target_path)).debug("Copied OpenGraph image")

    with Image.open(copied) as src:
        # Only resize the image if it needs to be resized
        if src.size[0] != max_width or src.size[1] != max_height:
            # Resize image while maintaining aspect ratio
            log.debug("Opengraph image is not 1200x630, resizing...")
            src.thumbnail((max_width, max_height))

        # Only impose a background image if the original image has
        # alpha/transparency channels
        if src.mode in ("RGBA", "LA"):
            log.debug("Opengraph image has transparency, converting...")
            background = Image.new("RGB", (max_width, max_height), background_color)
            background.paste(src, box=center_point(background, src))
            dst = background
        else:
            dst = src

        # Save new image to derived target path
        dst.save(dst_path)

        # Delete the copied image
        Path(copied).unlink()

        if not dst_path.exists():
            raise RuntimeError(f"Unable to save resized image to {str(dst_path)}")
        log.bind(path=str(dst_path)).debug("OpenGraph image ready")

    return True


def migrate_images(app_path: Path, params: "UIParameters"):
    """Migrate images from source code to install directory."""
    images_dir = app_path / "static" / "images"
    favicon_dir = images_dir / "favicons"
    check_path(favicon_dir, create=True)
    src_files = ()
    dst_files = ()

    for image in ("light", "dark", "favicon"):
        src: Path = getattr(params.web.logo, image)
        dst = images_dir / f"{image + src.suffix}"
        src_files += (src,)
        dst_files += (dst,)
    return copyfiles(src_files, dst_files)


def write_custom_files(params: "UIParameters") -> None:
    """Write custom files to the `ui` directory so they can be imported and rendered."""
    js = Path(__file__).parent.parent / "ui" / "custom.js"
    html = Path(__file__).parent.parent / "ui" / "custom.html"

    # Handle Custom JS.
    if params.web.custom_javascript is not None:
        copyfiles((params.web.custom_javascript,), (js,))
    else:
        with js.open("w") as f:
            f.write("")
    # Handle Custom HTML.
    if params.web.custom_html is not None:
        copyfiles((params.web.custom_html,), (html,))
    else:
        with html.open("w") as f:
            f.write("")


async def build_frontend(
    dev_mode: bool,
    dev_url: str,
    params: "UIParameters",
    app_path: Path,
    force: bool = False,
    timeout: int = 180,
) -> bool:
    """Prepare the UI to be served with the current configuration.

    In production, the UI is only built if its source has changed (e.g. after an upgrade), and
    configuration is rendered into the existing build. In development mode, configuration is
    written to the UI directory for the Next.js development server.
    """
    images_dir = app_path / "static" / "images"
    favicons = await asyncio.to_thread(
        generate_favicons, params.web.logo.favicon, images_dir / "favicons"
    )
    log.bind(count=len(favicons)).debug("Generated favicons")
    migrate_images(app_path, params)
    generate_opengraph(
        params.web.opengraph.image,
        1200,
        630,
        images_dir,
        params.web.theme.colors.black,
    )

    if dev_mode:
        (UI_DIR / "hyperglass.json").write_text(params.export_json(by_alias=True))
        write_custom_files(params)
        (UI_DIR / ".env").write_text(f"HYPERGLASS_URL={dev_url}\nNODE_ENV=development")
        if not (UI_DIR / "node_modules").exists():
            await run_ui_command("pnpm install --frozen-lockfile", timeout)
        log.debug("Running in developer mode, wrote UI configuration")
        return True

    await build_ui(timeout=timeout, force=force)
    await asyncio.to_thread(render_ui, UI_BUILD_DIR, app_path / "static" / "ui", params)
    log.debug("Rendered UI configuration")
    return True
