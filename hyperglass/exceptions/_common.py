"""Custom exceptions for hyperglass."""

# Standard Library
import re
import json as _json
from typing import Any, Set, Dict, List, Union, Literal, Optional

# Third Party
from pydantic import ValidationError

# Project
from hyperglass.log import log
from hyperglass.util import repr_from_attrs
from hyperglass.constants import STATUS_CODE_MAP

ErrorLevel = Literal["danger", "warning"]

# Format placeholders: named (`{key}`), numbered (`{0}`) or automatically numbered (`{}`).
_PLACEHOLDER = re.compile(r"\{(\w*)\}")


def safe_format(template: str, *args: Any, **kwargs: Any) -> str:
    """Replace placeholders in a template with arguments' values.

    Unlike `str.format()`, placeholders without a matching argument and any other braces (e.g. in
    device output included in an error) are left as-is, rather than raising an error.
    """
    positional = iter(args)

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key == "":
            return str(next(positional, match.group(0)))
        if key.isdigit():
            index = int(key)
            return str(args[index]) if index < len(args) else match.group(0)
        if key in kwargs:
            return str(kwargs[key])
        return match.group(0)

    return _PLACEHOLDER.sub(replace, str(template))


def has_placeholder(template: str, key: str) -> bool:
    """Determine if a template contains a named placeholder."""
    return key in _PLACEHOLDER.findall(template)


class HyperglassError(Exception):
    """hyperglass base exception."""

    def __init__(
        self,
        message: str = "",
        level: ErrorLevel = "warning",
        keywords: Optional[List[str]] = None,
    ) -> None:
        """Initialize the hyperglass base exception class."""
        self._message = message
        self._level = level
        self._keywords = keywords or []
        self._log()

    def _log(self) -> None:
        """Log the error when it's created."""
        if self._level == "warning":
            log.error(str(self))
        elif self._level == "danger":
            log.critical(str(self))
        else:
            log.info(str(self))

    def __str__(self) -> str:
        """Return the instance's error message."""
        return self._message

    def __repr__(self) -> str:
        """Return the instance's severity & error message in a string."""
        return repr_from_attrs(self, ("_message", "level", "keywords"), strip="_")

    def dict(self) -> Dict[str, Union[str, List[str]]]:
        """Return the instance's attributes as a dictionary."""
        return {
            "message": self._message,
            "level": self._level,
            "keywords": self.keywords,
        }

    def json(self) -> str:
        """Return the instance's attributes as a JSON object."""
        return _json.dumps(self.dict())

    @staticmethod
    def _safe_format(template: str, *args: Any, **kwargs: Any) -> str:
        """Safely format a string template from arguments."""
        return safe_format(template, *args, **kwargs)

    @staticmethod
    def _parse_pydantic_errors(*errors: Dict[str, Any]) -> str:
        errs = ("\n",)

        for err in errors:
            loc = " → ".join(str(loc) for loc in err["loc"])
            errs += (f"Field: {loc}\n  Error: {err['msg']}\n",)

        return "\n".join(errs)

    def _process_keywords(self) -> None:
        out: Set[str] = set()
        for val in self._keywords:
            if isinstance(val, str):
                out.add(val)
            elif isinstance(val, list):
                for v in val:
                    out.add(str(v))
            elif val is not None:
                out.add(str(val))
        # Keywords are highlighted in the message. Exclude values that aren't part of the message,
        # so internal details passed to the message template aren't exposed.
        self._keywords = [k for k in out if k and k in self._message]

    @property
    def message(self) -> str:
        """Return the instance's `message` attribute."""
        return self._message

    @property
    def level(self) -> str:
        """Return the instance's `level` attribute."""
        return self._level

    @property
    def keywords(self) -> List[str]:
        """Return the instance's `keywords` attribute."""
        self._process_keywords()
        return self._keywords

    @property
    def status_code(self) -> int:
        """Return HTTP status code based on level level."""
        return STATUS_CODE_MAP.get(self._level, 500)


class PublicHyperglassError(HyperglassError):
    """Base exception class for user-facing errors.

    Error text should be defined in
    `hyperglass.configuration.params.messages` and associated with the
    exception class at start time.
    """

    _level = "warning"
    _message_template = "Something went wrong."
    _original_template_name: str = ""

    def __init_subclass__(
        cls, *, template: Optional[str] = None, level: Optional[ErrorLevel] = None
    ) -> None:
        """Override error attributes from subclass."""

        if template is not None:
            cls._message_template = template
            cls._original_template_name = template
        if level is not None:
            cls._level = level

    def __init__(self, **kwargs: Any) -> None:
        """Format error message with keyword arguments."""
        # Project
        from hyperglass.state import use_state

        template = self._message_template

        (messages := use_state("params").messages)
        if messages.has(self._original_template_name):
            template = messages[self._original_template_name]

        error = kwargs.pop("error", None)
        if error is not None and str(error) != "":
            # Error text may itself be a template, e.g. "No rules matched target '{target}'".
            kwargs["error"] = self._safe_format(str(error), **kwargs)
            if not has_placeholder(template, "error"):
                template += " ({error})"
        elif has_placeholder(template, "error"):
            kwargs["error"] = ""

        self._message = self._safe_format(template, **kwargs)
        self._keywords = list(kwargs.values())
        super().__init__(message=self._message, level=self._level, keywords=self._keywords)

    def _log(self) -> None:
        """Log the error when it's created.

        User-facing errors, e.g. invalid input, are logged by the API's error handlers along with
        the request & response status, at a level appropriate for the response.
        """
        log.debug(str(self))


class PrivateHyperglassError(HyperglassError):
    """Base exception class for internal system errors.

    Error text is dynamic based on the exception being caught.
    """

    _level = "warning"

    def _parse_validation_error(self, err: ValidationError) -> str:
        errors = err.errors()
        parsed = {
            k: ", ".join(str(loc) for t in errors for loc in t["loc"] if t["type"] == k)
            for k in {e["type"] for e in errors}
        }
        return ", ".join(parsed.values())

    def __init_subclass__(cls, *, level: Optional[ErrorLevel] = None) -> None:
        """Override error attributes from subclass."""
        if level is not None:
            cls._level = level

    def __init__(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Format error message with positional & keyword arguments."""
        if "error" in kwargs:
            error = kwargs.pop("error")
            error = self._safe_format(str(error), *args, **kwargs)
            kwargs["error"] = error

        if isinstance(message, ValidationError):
            message = self._parse_validation_error(message)

        self._message = self._safe_format(message, *args, **kwargs)
        self._keywords = [*args, *kwargs.values()]
        super().__init__(message=self._message, level=self._level, keywords=self._keywords)
