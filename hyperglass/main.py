"""Start hyperglass."""

# Standard Library
import sys
import typing as t
import asyncio
import logging

# Third Party
import uvicorn

# Local
from .log import LibInterceptHandler, init_logger, configure_logging
from .util import get_node_version
from .constants import MIN_NODE_VERSION, MIN_PYTHON_VERSION, __version__

# Ensure the Python version meets the minimum requirements.
pretty_version = ".".join(tuple(str(v) for v in MIN_PYTHON_VERSION))
if sys.version_info < MIN_PYTHON_VERSION:
    raise RuntimeError(f"Python {pretty_version}+ is required.")


# Local
from .state import use_state
from .settings import Settings

LOG_LEVEL = Settings.log_level
logging.basicConfig(handlers=[LibInterceptHandler()], level=0, force=True)
log = init_logger(LOG_LEVEL)


def check_node_version() -> None:
    """Ensure NodeJS, which the UI requires, is installed & meets the minimum version."""
    try:
        version = get_node_version()
    except Exception as err:
        raise RuntimeError(
            f"NodeJS {MIN_NODE_VERSION!s}+ is required for the UI, but it could not be run: {err!s}"
        ) from err

    if not version:
        raise RuntimeError(f"NodeJS {MIN_NODE_VERSION!s}+ is required for the UI")

    if version[0] < MIN_NODE_VERSION:
        installed = ".".join(str(v) for v in version)
        raise RuntimeError(
            f"NodeJS {MIN_NODE_VERSION!s}+ is required (version {installed} installed)"
        )


async def build_ui() -> bool:
    """Prepare the UI with the current configuration prior to starting the application."""
    # Local
    from .frontend import build_frontend

    state = use_state()
    await build_frontend(
        dev_mode=Settings.dev_mode,
        dev_url=Settings.dev_url,
        params=state.ui_params,
        app_path=Settings.app_path,
    )
    return True


def register_all_plugins() -> None:
    """Validate and register configured plugins."""

    # Local
    from .plugins import register_plugin, init_builtin_plugins

    state = use_state()

    # Register built-in plugins.
    init_builtin_plugins()

    failures = ()

    # Register external directive-based plugins (defined in directives).
    for plugin_file, directives in state.devices.directive_plugins().items():
        failures += register_plugin(plugin_file, directives=directives)

    # Register external global/common plugins (defined in config).
    for plugin_file in state.params.common_plugins():
        failures += register_plugin(plugin_file, common=True)

    for failure in failures:
        log.bind(plugin=failure).warning("Invalid hyperglass plugin")


def unregister_all_plugins() -> None:
    """Unregister all plugins."""
    # Local
    from .plugins import InputPluginManager, OutputPluginManager

    for manager in (InputPluginManager, OutputPluginManager):
        manager().reset()


def start(*, log_level: t.Union[str, int], workers: int) -> None:
    """Start hyperglass via ASGI server."""

    register_all_plugins()

    if not Settings.disable_ui:
        check_node_version()
        asyncio.run(build_ui())

    uvicorn.run(
        # Import the app from its module, rather than `hyperglass.api`, where `app` can resolve to
        # the `hyperglass.api.app` module instead of the application.
        app="hyperglass.api.app:app",
        host=str(Settings.host),
        port=Settings.port,
        workers=workers,
        forwarded_allow_ips=Settings.trusted_proxies,
        log_level=log_level,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "format": "%(message)s",
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "format": "%(message)s",
                },
            },
            "handlers": {
                "default": {"formatter": "default", "class": "hyperglass.log.LibInterceptHandler"},
                "access": {"formatter": "access", "class": "hyperglass.log.LibInterceptHandler"},
            },
            "loggers": {
                "uvicorn.error": {"level": "ERROR", "handlers": ["default"], "propagate": False},
                "uvicorn.access": {"level": "INFO", "handlers": ["access"], "propagate": False},
            },
        },
    )


def run(workers: int = None):
    """Run hyperglass."""
    # Local
    from .configuration import init_user_config

    try:
        log.debug(repr(Settings))

        state = use_state()
        state.clear()

        init_user_config()

        configure_logging(LOG_LEVEL, params=state.params.logging)

        _workers = workers or Settings.worker_count()

        log.bind(
            version=__version__,
            listening=f"http://{Settings.bind()}",
            app_path=f"{Settings.app_path.absolute()!s}",
            container=Settings.container,
            original_app_path=f"{Settings.original_app_path.absolute()!s}",
            workers=_workers,
        ).info(
            "Starting hyperglass",
        )

        start(log_level=LOG_LEVEL, workers=_workers)
        log.bind(version=__version__).critical("Stopping hyperglass")
    except Exception as error:
        log.critical(error)
        # Handle app exceptions.
        if not Settings.dev_mode:
            state = use_state()
            state.clear()
            log.debug("Cleared hyperglass state")
        unregister_all_plugins()
        raise error
    except BaseException:
        # E.g. KeyboardInterrupt, or SystemExit if the server fails to start (e.g. the port is in
        # use). Re-raise, so a failure's exit status is preserved.
        unregister_all_plugins()
        raise


if __name__ == "__main__":
    run()
