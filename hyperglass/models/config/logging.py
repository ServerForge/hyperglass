"""Validate logging configuration."""

# Standard Library
import typing as t
from pathlib import Path

# Third Party
from pydantic import ByteSize, SecretStr, AnyHttpUrl, DirectoryPath, field_validator

# Local
from ..main import HyperglassModel
from ..fields import LogFormat, HttpAuthMode, HttpProvider


class Syslog(HyperglassModel):
    """Validation model for syslog configuration."""

    enable: bool = True
    host: str
    port: int = 514


class HttpAuth(HyperglassModel):
    """HTTP hook authentication parameters."""

    mode: HttpAuthMode = "basic"
    username: t.Optional[str] = None
    password: SecretStr
    header: str = "x-api-key"

    def api_key(self):
        """Represent authentication as an API key header."""
        return {self.header: self.password.get_secret_value()}

    def basic(self):
        """Represent HTTP basic authentication."""
        return (self.username or "", self.password.get_secret_value())


class Http(HyperglassModel, extra="allow"):
    """HTTP logging parameters."""

    enable: bool = True
    provider: HttpProvider = "generic"
    host: AnyHttpUrl
    authentication: t.Optional[HttpAuth] = None
    headers: t.Dict[str, t.Union[str, int, bool, None]] = {}
    params: t.Dict[str, t.Union[str, int, bool, None]] = {}
    verify_ssl: bool = True
    timeout: t.Union[float, int] = 5.0

    @field_validator("headers", "params")
    def stringify_headers_params(cls, value):
        """Ensure headers and URL parameters are strings."""
        for k, v in value.items():
            if not isinstance(v, str):
                value[k] = str(v)
        return value


class Logging(HyperglassModel):
    """Validation model for logging configuration."""

    directory: DirectoryPath = Path("/tmp")  # noqa: S108
    format: LogFormat = "text"
    max_size: ByteSize = "50MB"
    syslog: t.Optional[Syslog] = None
    http: t.Optional[Http] = None
