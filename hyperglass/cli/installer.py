"""Install hyperglass."""

# Standard Library
import os
import time
import shutil
import typing as t
import getpass
from types import TracebackType
from pathlib import Path

# Third Party
import typer
from rich.progress import Progress

# Project
from hyperglass.settings import Settings
from hyperglass.constants import __version__

# Local
from .echo import echo

ASSET_DIR = Path(__file__).parent.parent / "images"
IGNORED_FILES = [".DS_Store"]


class Installer:
    """Install hyperglass."""

    app_path: Path
    progress: Progress
    user: str
    assets: int

    def __init__(self):
        """Start hyperglass installer."""
        self.app_path = Settings.app_path
        self.progress: Progress = Progress(console=echo._console)
        self.user = getpass.getuser()
        self.assets = len([p for p in ASSET_DIR.iterdir() if p.name not in IGNORED_FILES])

    def install(self) -> None:
        """Initialize tasks and start installer."""
        permissions_task = self.progress.add_task("[bright purple]Checking System", total=2)
        scaffold_task = self.progress.add_task(
            "[bright blue]Creating Directory Structures", total=3
        )
        asset_task = self.progress.add_task(
            "[bright cyan]Migrating Static Assets", total=self.assets
        )
        ui_task = self.progress.add_task("[bright teal]Initialzing UI", total=1, start=False)

        self.progress.start()

        self.check_permissions(task_id=permissions_task)
        self.scaffold(task_id=scaffold_task)
        self.migrate_static_assets(task_id=asset_task)
        self.init_ui(task_id=ui_task)

    def __enter__(self) -> t.Callable[[], None]:
        """Initialize tasks."""
        self.progress.print(f"Starting hyperglass {__version__} setup")
        return self.install

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]] = None,
        exc_value: t.Optional[BaseException] = None,
        exc_traceback: t.Optional[TracebackType] = None,
    ):
        """Print errors on exit."""
        self.progress.stop()
        if isinstance(exc_value, typer.Exit):
            # Exit with the same code; the error has already been reported, e.g. by `build_ui()`.
            return
        if exc_type is not None:
            echo._console.print_exception(show_locals=True)
            raise typer.Exit(1)
        raise typer.Exit(0)

    def check_permissions(self, task_id: int) -> None:
        """Ensure the executing user has permissions to the app path."""
        read = os.access(self.app_path, os.R_OK)
        if not read:
            self.progress.print(
                f"User {self.user!r} does not have read access to {self.app_path!s}", style="error"
            )
            raise typer.Exit(1)

        self.progress.advance(task_id)
        time.sleep(0.4)

        write = os.access(self.app_path, os.W_OK)
        if not write:
            self.progress.print(
                f"User {self.user!r} does not have write access to {self.app_path!s}", style="error"
            )
            raise typer.Exit(1)
        self.progress.advance(task_id)

    def scaffold(self, task_id: int) -> None:
        """Create the file structure necessary for hyperglass to run."""

        if not self.app_path.exists():
            self.progress.print("Created {!s}".format(self.app_path), style="info")
            self.app_path.mkdir(parents=True)

        self.progress.print(f"hyperglass path is {self.app_path!s}", style="subtle")
        self.progress.advance(task_id)

        ui_dir = self.app_path / "static" / "ui"
        favicon_dir = self.app_path / "static" / "images" / "favicons"

        for path in (ui_dir, favicon_dir):
            if not path.exists():
                self.progress.print("Created {!s}".format(path), style="info")
                path.mkdir(parents=True)

            self.progress.advance(task_id)
            time.sleep(0.4)

    def migrate_static_assets(self, task_id: int) -> None:
        """Copy any of the project's assets missing from the installation's assets.

        The installation's asset directory also contains user files (e.g. logos & avatars), so
        existing files are never removed or replaced.
        """

        target_dir = self.app_path / "static" / "images"
        target_dir.mkdir(parents=True, exist_ok=True)

        for asset in sorted(ASSET_DIR.iterdir()):
            if asset.name in IGNORED_FILES:
                continue
            target = target_dir / asset.name
            if not target.exists():
                if asset.is_dir():
                    shutil.copytree(asset, target, ignore=shutil.ignore_patterns(*IGNORED_FILES))
                else:
                    shutil.copy2(asset, target)
                self.progress.print(f"Copied {target!s}", style="info")
            self.progress.advance(task_id)

    def init_ui(self, task_id: int) -> None:
        """Initialize UI."""
        # Project
        from hyperglass.log import log

        # Local
        from .util import build_ui

        self.progress.start_task(task_id)
        log.disable("hyperglass")
        try:
            # Build errors are printed by `build_ui()`, so console output must not be captured.
            build_ui(timeout=180)
        finally:
            log.enable("hyperglass")
        self.progress.advance(task_id)
