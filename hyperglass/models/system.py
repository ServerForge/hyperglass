"""hyperglass System Settings model."""

# Standard Library
import os
import typing as t
import logging
from pathlib import Path
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import quote

# Third Party
from pydantic import (
    Field,
    FilePath,
    RedisDsn,
    SecretStr,
    DirectoryPath,
    IPvAnyAddress,
    ValidationInfo,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
)

# Project
from hyperglass.util import at_least, cpu_count, available_cpus

if t.TYPE_CHECKING:
    # Third Party
    from rich.console import Console, RenderResult, ConsoleOptions

ListenHost = t.Union[None, IPvAnyAddress, t.Literal["localhost"]]

_default_app_path = Path("/etc/hyperglass")
# Default maximum number of web server workers, if `HYPERGLASS_WORKERS` isn't set.
MAX_DEFAULT_WORKERS = 4
# File in the app path from which environment variables are read.
ENV_FILE_NAME = "hyperglass.env"


def mask_dsn_password(dsn: t.Optional[RedisDsn]) -> t.Optional[str]:
    """Represent a DSN with its password (if any) masked, e.g. for display or logging."""
    if dsn is None:
        return None
    if dsn.password:
        return str(dsn).replace(f":{dsn.password}@", ":********@", 1)
    return str(dsn)


class HyperglassSettings(BaseSettings):
    """hyperglass system settings, required to start hyperglass."""

    # Ignore unrelated variables in `hyperglass.env`.
    model_config = SettingsConfigDict(env_prefix="hyperglass_", extra="ignore")

    config_file_names: t.ClassVar[t.Tuple[str, ...]] = ("config", "devices", "directives")
    default_app_path: t.ClassVar[Path] = _default_app_path
    original_app_path: Path = _default_app_path

    debug: bool = False
    dev_mode: bool = False
    disable_ui: bool = False
    app_path: DirectoryPath = _default_app_path
    redis_host: str = "localhost"
    redis_password: t.Optional[SecretStr] = None
    redis_db: int = 1
    redis_dsn: RedisDsn = None
    host: IPvAnyAddress = None
    port: int = 8001
    ca_cert: t.Optional[FilePath] = None
    container: bool = False
    # Reverse proxies trusted to set the client address via X-Forwarded-For (comma-separated IPs
    # or networks, or `*`), used for logging & rate limiting.
    trusted_proxies: str = "127.0.0.1,::1"
    workers: t.Optional[int] = Field(None, gt=0)

    def __init__(self, **kwargs) -> None:
        """Create hyperglass Settings instance."""
        super().__init__(**kwargs)
        if self.container:
            self.app_path = self.default_app_path

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: t.Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> t.Tuple[PydanticBaseSettingsSource, ...]:
        """Read settings from `hyperglass.env` in the app path, if it exists.

        Environment variables take precedence over the file.
        """
        sources = (init_settings, env_settings)
        env_file = Path(os.environ.get("HYPERGLASS_APP_PATH", _default_app_path)) / ENV_FILE_NAME
        try:
            # The file may only be readable by root, if it's (also) used as a systemd
            # EnvironmentFile, in which case systemd has already set its variables.
            if env_file.is_file() and os.access(env_file, os.R_OK):
                sources += (DotEnvSettingsSource(settings_cls, env_file=env_file),)
        except OSError:
            pass
        return (*sources, file_secret_settings)

    def __repr_args__(self) -> t.Iterable[t.Tuple[t.Optional[str], t.Any]]:
        """Mask the Redis password in the DSN, e.g. when settings are logged."""
        for name, value in super().__repr_args__():
            if name == "redis_dsn":
                value = mask_dsn_password(value)
            yield name, value

    def __rich_console__(self, console: "Console", options: "ConsoleOptions") -> "RenderResult":
        """Render a Rich table representation of hyperglass settings."""
        # Third Party
        from rich.panel import Panel
        from rich.style import Style
        from rich.table import Table, box
        from rich.pretty import Pretty

        table = Table(box=box.MINIMAL, border_style="subtle")
        table.add_column("Environment Variable", style=Style(color="#118ab2", bold=True))
        table.add_column("Value")
        params = sorted(
            (
                "debug",
                "dev_mode",
                "app_path",
                "redis_host",
                "redis_db",
                "redis_dsn",
                "host",
                "port",
                "trusted_proxies",
                "workers",
            )
        )
        for attr in params:
            value = getattr(self, attr)
            if attr == "redis_dsn":
                value = mask_dsn_password(value)
            table.add_row(f"hyperglass_{attr}".upper(), Pretty(value))

        yield Panel.fit(table, title="hyperglass settings", border_style="subtle")

    @field_validator("host", mode="before")
    def validate_host(
        cls: "HyperglassSettings", value: t.Any, info: ValidationInfo
    ) -> IPvAnyAddress:
        """Set default host based on debug mode."""

        if value is None:
            if info.data.get("debug") is False:
                return ip_address("::1")
            if info.data.get("debug") is True:
                return ip_address("::")

        if isinstance(value, (IPv4Address, IPv6Address)):
            return value

        if isinstance(value, str):
            if value != "localhost":
                # Accept IPv6 addresses in brackets, e.g. `[::1]`, as they're written in URLs.
                if value.startswith("[") and value.endswith("]"):
                    value = value[1:-1]
                try:
                    return ip_address(value)
                except ValueError as err:
                    raise ValueError(str(value)) from err

            elif value == "localhost":
                return ip_address("::1")

        raise ValueError(str(value))

    @field_validator("redis_dsn", mode="before")
    def validate_redis_dsn(cls, value: t.Any, info: ValidationInfo) -> RedisDsn:
        """Construct a Redis DSN if none is provided."""
        if value is None:
            host = info.data.get("redis_host")
            try:
                # IPv6 addresses must be enclosed in brackets in a URL.
                if ip_address(host).version == 6:
                    host = f"[{host}]"
            except ValueError:
                pass
            db = info.data.get("redis_db")
            dsn = "redis://{}/{!s}".format(host, db)
            password = info.data.get("redis_password")
            if password is not None:
                # Escape the password, so URL syntax in it (e.g. `@`, `/`, `#`, `%20`) is
                # treated as part of the password.
                password = quote(password.get_secret_value(), safe="")
                dsn = "redis://:{}@{}/{!s}".format(password, host, db)
            return dsn
        return value

    def bind(self: "HyperglassSettings") -> str:
        """Format a listen_address. Wraps IPv6 address in brackets."""
        if self.host.version == 6:
            return f"[{self.host!s}]:{self.port!s}"
        return f"{self.host!s}:{self.port!s}"

    @property
    def log_level(self: "HyperglassSettings") -> int:
        """Get log level, inferred from debug mode."""
        if self.debug:
            return logging.DEBUG
        return logging.INFO

    def worker_count(self: "HyperglassSettings") -> int:
        """Get the number of web server workers.

        hyperglass is I/O bound (waiting on devices), so a few workers handle many concurrent
        queries; additional workers mostly consume memory.
        """
        if self.workers is not None:
            return self.workers
        if self.debug:
            return 1
        return min(available_cpus(), MAX_DEFAULT_WORKERS)

    @property
    def redis(self: "HyperglassSettings") -> t.Dict[str, t.Union[None, int, str]]:
        """Get redis parameters as a dict for convenient connection setups."""
        password = None
        if self.redis_password is not None:
            password = self.redis_password.get_secret_value()

        return {
            "db": self.redis_db,
            "host": self.redis_host,
            "password": password,
        }

    @property
    def redis_connection_pool(self: "HyperglassSettings") -> t.Dict[str, t.Any]:
        """Get Redis ConnectionPool keyword arguments."""
        return {"url": str(self.redis_dsn), "max_connections": at_least(8, cpu_count(2))}

    @property
    def dev_url(self: "HyperglassSettings") -> str:
        """Get the hyperglass URL for when dev_mode is enabled."""
        return f"http://localhost:{self.port!s}/"

    @property
    def prod_url(self: "HyperglassSettings") -> str:
        """Get the UI-facing hyperglass URL/path."""
        return "/api/"

    @property
    def static_path(self: "HyperglassSettings") -> Path:
        """Get static asset path."""
        return Path(self.app_path / "static")
