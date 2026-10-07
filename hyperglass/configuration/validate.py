"""Import configuration files and run validation."""

# Standard Library
import typing as t

# Third Party
from pydantic import ValidationError

# Project
from hyperglass.log import log
from hyperglass.util import replace_placeholders
from hyperglass.settings import Settings
from hyperglass.models.ui import UIParameters
from hyperglass.models.directive import Directive, Directives
from hyperglass.exceptions.private import ConfigError, ConfigInvalid
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Device, Devices

# Local
from .load import find_path, load_config
from .markdown import get_markdown

__all__ = (
    "init_devices",
    "init_directives",
    "init_files",
    "init_params",
    "init_ui_params",
)

Location = t.Tuple[t.Union[str, int], ...]


def _file_name(name: str) -> str:
    """Get the file name of a configuration file, for error messages."""
    path = find_path(name, required=False)
    return name if path is None else path.name


def _invalid(location: Location, message: str) -> ConfigInvalid:
    """Create a configuration validation error for a single field."""
    return ConfigInvalid(errors=[{"loc": location, "msg": message}])


def _invalid_shape(location: Location, expected: str, value: t.Any) -> ConfigInvalid:
    """Create a configuration validation error for a value with an unexpected type/shape."""
    return _invalid(location, f"Expected {expected}, got '{type(value).__name__}'")


def _from_validation_error(location: Location, error: ValidationError) -> ConfigInvalid:
    """Create a configuration validation error from a model validation error, with context."""
    return ConfigInvalid(errors=[{**e, "loc": (*location, *e["loc"])} for e in error.errors()])


def init_files() -> None:
    """Check if required directories exist and if not, create them."""
    for directory in ("plugins", "static/images"):
        path = Settings.app_path / directory
        if not path.exists():
            path.mkdir(parents=True)
            log.debug("Created directory", path=path)


def init_params() -> "Params":
    """Validate & initialize configuration parameters."""
    user_config = load_config("config", required=False)
    file_name = _file_name("config")
    if not isinstance(user_config, t.Dict):
        raise _invalid_shape((file_name,), "a mapping of configuration parameters", user_config)
    # Map imported user configuration to expected schema.
    try:
        params = Params(**user_config)
    except ValidationError as err:
        raise _from_validation_error((file_name,), err) from err

    # # Set up file logging once configuration parameters are initialized.
    # enable_file_logging(
    #     log_directory=params.logging.directory,
    #     log_format=params.logging.format,
    #     log_max_size=params.logging.max_size,
    #     debug=Settings.debug,
    # )

    # Set up syslog logging if enabled.
    # if params.logging.syslog is not None and params.logging.syslog.enable:
    #     enable_syslog_logging(
    #         syslog_host=params.logging.syslog.host,
    #         syslog_port=params.logging.syslog.port,
    #     )

    if params.logging.http is not None and params.logging.http.enable:
        log.debug("HTTP logging is enabled")

    # Perform post-config initialization string formatting or other
    # functions that require access to other config levels. E.g.,
    # something in 'params.web.text' needs to be formatted with a value
    # from params. Only known placeholders are replaced, other text (e.g. braces) is kept as-is.
    try:
        params.web.text.subtitle = replace_placeholders(
            params.web.text.subtitle,
            **params.model_dump(exclude={"web", "queries", "messages"}),
        )
    except ValidationError as err:
        raise _from_validation_error((file_name, "web", "text"), err) from err

    return params


def init_directives() -> "Directives":
    """Validate & initialize directives."""
    # Map imported user directives to expected schema.
    directives_config = load_config("directives", required=False)
    file_name = _file_name("directives")
    if not isinstance(directives_config, t.Dict):
        raise _invalid_shape(
            (file_name,), "a mapping of directive IDs to directives", directives_config
        )

    directives = []
    for name, directive in directives_config.items():
        if not isinstance(directive, t.Dict):
            raise _invalid_shape((file_name, name), "a mapping of directive parameters", directive)
        try:
            directives.append(Directive(id=name, **directive))
        except ValidationError as err:
            raise _from_validation_error((file_name, name), err) from err

    return Directives(*directives)


def init_devices() -> "Devices":
    """Validate & initialize devices."""
    devices_config = load_config("devices", required=True)
    file_name = _file_name("devices")
    if not isinstance(devices_config, t.Dict):
        raise _invalid_shape(
            (file_name,),
            "a mapping with a 'devices' key, containing a list of devices",
            devices_config,
        )

    # Support first matching main key name.
    key, items = next(
        ((k, devices_config[k]) for k in ("main", "devices", "routers") if k in devices_config),
        ("devices", None),
    )

    if not items:
        raise ConfigError("No devices are defined in {file}", file=file_name)

    if not isinstance(items, (t.List, t.Tuple)):
        raise _invalid_shape((file_name, key), "a list of devices", items)

    devices = []
    for index, item in enumerate(items):
        if not isinstance(item, t.Dict):
            raise _invalid_shape((file_name, key, index), "a mapping of device parameters", item)
        location = (file_name, key, item.get("name", index))
        try:
            devices.append(Device(**item))
        except ValidationError as err:
            raise _from_validation_error(location, err) from err
        except ValueError as err:
            # Raised prior to field validation, e.g. for a missing name or deprecated field.
            raise _invalid(location, str(err)) from err

    devices = Devices(*devices)
    log.debug("Initialized devices", devices=devices)

    return devices


def init_ui_params(*, params: "Params", devices: "Devices") -> "UIParameters":
    """Validate & initialize UI parameters."""

    # Project
    from hyperglass.defaults import CREDIT
    from hyperglass.constants import PARSED_RESPONSE_FIELDS, __version__

    content_greeting = get_markdown(
        config=params.web.greeting,
        default="",
        params={"title": params.web.greeting.title},
    )
    content_credit = CREDIT.format(version=__version__)

    _ui_params = params.frontend()
    _ui_params["web"]["logo"]["light_format"] = params.web.logo.light.suffix
    _ui_params["web"]["logo"]["dark_format"] = params.web.logo.dark.suffix

    return UIParameters(
        **_ui_params,
        version=__version__,
        devices=devices.frontend(),
        developer_mode=Settings.dev_mode,
        parsed_data_fields=PARSED_RESPONSE_FIELDS,
        content={"credit": content_credit, "greeting": content_greeting},
    )
