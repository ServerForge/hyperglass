"""API Error Handlers."""

# Standard Library
import typing as t

# Third Party
from litestar import Request, Response
from litestar.exceptions import ValidationException, TooManyRequestsException

# Project
from hyperglass.log import log
from hyperglass.state import use_state

__all__ = (
    "default_handler",
    "http_handler",
    "app_handler",
    "validation_handler",
)

# Used if the configured message can't be read, e.g. if Redis is unreachable.
DEFAULT_ERROR_MESSAGE = "Something went wrong."


def _log_error(request: Request, status_code: int, message: str, **kwargs: t.Any) -> None:
    """Log an error response, as an error only if it's a server error.

    Client errors (e.g. invalid input or an unknown path) are expected, and logged as info.
    """
    _log = log.bind(method=request.method, path=request.url.path, status=status_code, **kwargs)
    if status_code >= 500:
        _log.error(message)
    else:
        _log.info(message)


def _message(name: str) -> str:
    """Get a configured message, falling back to a generic message if it can't be read."""
    try:
        return getattr(use_state("params").messages, name)
    except Exception:
        return DEFAULT_ERROR_MESSAGE


def get_validation_exception_detail(exc: ValidationException) -> Response:
    data: dict[str, t.Any] = {
        "level": "error",
        "status_code": exc.status_code,
        "keywords": [],
        "output": repr(exc),
    }
    if isinstance(exc.extra, dict):
        outputs = []
        kw = []
        for k, v in exc.extra.items():
            outputs = [*outputs, f"{k}: {v!r}"]
            kw = [*kw, k]
        data["output"] = "\n".join(outputs)
        data["keywords"] = kw

    if isinstance(exc.extra, list):
        outputs = []
        for v in exc.extra:
            if isinstance(v, dict) and "message" in v:
                # e.g. `{"message": "Field required", "key": "queryTarget", "source": "body"}`
                outputs = [*outputs, ": ".join(str(i) for i in (v.get("key"), v["message"]) if i)]
            else:
                outputs = [*outputs, str(v)]
        data["output"] = "\n".join(outputs)
        data["keywords"] = []

    return Response(data, status_code=exc.status_code)


def default_handler(request: Request, exc: BaseException) -> Response:
    """Handle uncaught errors."""
    log.bind(method=request.method, path=request.url.path, detail=str(exc)).critical("Error")
    return Response(
        {"output": _message("general"), "level": "danger", "keywords": []},
        status_code=500,
    )


def http_handler(request: Request, exc: BaseException) -> Response:
    """Handle web server errors."""
    if isinstance(exc, TooManyRequestsException):
        log.bind(method=request.method, path=request.url.path, client=request.client).warning(
            "Rate limit exceeded"
        )
        return Response(
            {"output": _message("rate_limited"), "level": "warning", "keywords": []},
            status_code=exc.status_code,
            # Litestar only sets RateLimit-* headers; Retry-After is more widely understood.
            headers={**exc.headers, "Retry-After": exc.headers.get("RateLimit-Reset", "60")},
        )

    _log_error(request, exc.status_code, "HTTP Error", detail=exc.detail)
    return Response(
        {
            "output": exc.detail,
            "level": "danger" if exc.status_code >= 500 else "warning",
            "keywords": [],
        },
        status_code=exc.status_code,
        headers=exc.headers,
    )


def app_handler(request: Request, exc: BaseException) -> Response:
    """Handle application errors."""
    _log_error(request, exc.status_code, "hyperglass Error", detail=exc.message)
    return Response(
        {"output": exc.message, "level": exc.level, "keywords": exc.keywords},
        status_code=exc.status_code,
    )


def validation_handler(request: Request, exc: ValidationException) -> Response:
    """Handle Pydantic validation errors raised by FastAPI."""
    _log_error(request, exc.status_code, "Validation Error", detail=exc)
    return get_validation_exception_detail(exc)
