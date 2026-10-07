"""Session handler for external http data sources."""

# Standard Library
import re
import json as _json
import typing as t
from json import JSONDecodeError
from urllib.parse import urlencode

# Third Party
import httpx

# Project
from hyperglass.log import log
from hyperglass.util import parse_exception, repr_from_attrs
from hyperglass.settings import Settings
from hyperglass.constants import __version__
from hyperglass.models.fields import JsonValue, HttpMethod, Primitives
from hyperglass.exceptions.private import ExternalError

if t.TYPE_CHECKING:
    # Standard Library
    from types import TracebackType

    # Project
    from hyperglass.exceptions._common import ErrorLevel
    from hyperglass.models.config.logging import Http

D = t.TypeVar("D", bound=t.Dict)


def _prepare_dict(_dict: D) -> D:
    return _json.loads(_json.dumps(_dict, default=str))


class BaseExternal:
    """Base session handler."""

    def __init__(
        self,
        base_url: str,
        config: t.Optional["Http"] = None,
        uri_prefix: str = "",
        uri_suffix: str = "",
        verify_ssl: bool = True,
        timeout: t.Union[int, float] = 10,
        parse: bool = True,
        headers: t.Optional[t.Dict[str, str]] = None,
        auth: t.Optional[t.Tuple[str, str]] = None,
    ) -> None:
        """Initialize connection instance."""
        self.__name__ = getattr(self, "name", "BaseExternal")
        self.name = self.__name__
        self.config = config
        self.base_url = base_url.strip("/")
        self.uri_prefix = uri_prefix.strip("/")
        self.uri_suffix = uri_suffix.strip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.parse = parse

        context = httpx.create_ssl_context(verify=verify_ssl)

        if Settings.ca_cert is not None:
            context.load_verify_locations(cafile=str(Settings.ca_cert))

        client_kwargs = {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "verify": context,
            "headers": {"user-agent": f"hyperglass/{__version__}", **(headers or {})},
            "auth": auth,
        }

        self._session = httpx.Client(**client_kwargs)
        self._asession = httpx.AsyncClient(**client_kwargs)

    @classmethod
    def __init_subclass__(
        cls: "BaseExternal", name: t.Optional[str] = None, **kwargs: t.Any
    ) -> None:
        """Set correct subclass name."""
        super().__init_subclass__(**kwargs)
        cls.name = name or cls.__name__

    async def __aenter__(self: "BaseExternal") -> "BaseExternal":
        """Enter session."""
        log.bind(url=self.base_url).debug("Initialized session")
        return self

    async def __aexit__(
        self: "BaseExternal",
        exc_type: t.Optional[t.Type[BaseException]] = None,
        exc_value: t.Optional[BaseException] = None,
        traceback: t.Optional["TracebackType"] = None,
    ) -> True:
        """Close connection on exit."""
        log.bind(url=self.base_url).debug("Closing session")

        if exc_type is not None:
            log.error(str(exc_value))

        await self._asession.aclose()
        if exc_value is not None:
            raise exc_value
        return True

    def __enter__(self: "BaseExternal") -> "BaseExternal":
        """Enter session."""
        log.bind(url=self.base_url).debug("Initialized session")
        return self

    def __exit__(
        self: "BaseExternal",
        exc_type: t.Optional[t.Type[BaseException]] = None,
        exc_value: t.Optional[BaseException] = None,
        exc_traceback: t.Optional["TracebackType"] = None,
    ) -> bool:
        """Close connection on exit."""
        if exc_type is not None:
            log.error(str(exc_value))
        self._session.close()
        if exc_value is not None:
            raise exc_value
        return True

    def __repr__(self: "BaseExternal") -> str:
        """Return user friendly representation of instance."""
        return repr_from_attrs(self, ("name", "base_url", "config", "parse"))

    def _exception(
        self: "BaseExternal",
        message: str,
        exc: t.Optional[BaseException] = None,
        level: "ErrorLevel" = "warning",
        **kwargs: t.Any,
    ) -> ExternalError:
        """Add stringified exception to message if passed."""
        if exc is not None:
            message = f"{message!s}: {exc!s}"

        return ExternalError(message=message, level=level, **kwargs)

    def _parse_response(self: "BaseExternal", response: httpx.Response) -> t.Any:
        if self.parse:
            parsed = {}
            try:
                parsed = response.json()
            except JSONDecodeError:
                try:
                    parsed = _json.loads(response)
                except (JSONDecodeError, TypeError):
                    parsed = {"data": response.text}
        else:
            parsed = response
        return parsed

    def _build_request(self: "BaseExternal", **kwargs: t.Any) -> t.Dict[str, t.Any]:
        """Process requests parameters into structure usable by http library."""
        # Standard Library
        from operator import itemgetter

        supported_methods = ("GET", "POST", "PUT", "DELETE", "HEAD", "PATCH")

        (
            method,
            endpoint,
            item,
            headers,
            params,
            data,
            timeout,
            response_required,
        ) = itemgetter(*kwargs.keys())(kwargs)

        if method.upper() not in supported_methods:
            raise self._exception(
                f"Method must be one of {', '.join(supported_methods)}. Got: {str(method)}"
            )

        if re.match(r"^https?://", endpoint, re.IGNORECASE):
            # Use absolute URLs, e.g. a configured webhook URL, as-is.
            url = endpoint
        else:
            url = "/".join(
                i
                for i in (
                    "",
                    self.uri_prefix.strip("/"),
                    endpoint.strip("/"),
                    self.uri_suffix.strip("/"),
                    item,
                )
                if i
            )

        request = {"method": method, "url": url}

        if headers is not None:
            # Merged with the session's headers.
            request["headers"] = headers

        if params:
            # Query parameters replace any query string in the URL.
            params = {str(k): str(v) for k, v in params.items() if v is not None}
            request["params"] = params

        if data is not None:
            if not isinstance(data, dict):
                raise self._exception(f"Data must be a dict, got: {str(data)}")
            request["json"] = _prepare_dict(data)

        if timeout is not None:
            if not isinstance(timeout, (int, float)):
                try:
                    timeout = float(timeout)
                except (TypeError, ValueError) as err:
                    raise self._exception(f"Timeout must be a number, got: {str(timeout)}") from err
            request["timeout"] = timeout
        return request

    async def _arequest(  # noqa: C901
        self: "BaseExternal",
        method: HttpMethod,
        endpoint: str,
        item: t.Union[str, int, None] = None,
        headers: t.Dict[str, str] = None,
        params: t.Dict[str, JsonValue[Primitives]] = None,
        data: t.Optional[t.Any] = None,
        timeout: t.Optional[int] = None,
        response_required: bool = False,
    ) -> t.Any:
        """Run HTTP POST operation."""
        request = self._build_request(
            method=method,
            endpoint=endpoint,
            item=item,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout,
            response_required=response_required,
        )

        try:
            response = await self._asession.request(**request)

            if response.status_code not in range(200, 300):
                status = httpx.codes(response.status_code)
                error = self._parse_response(response)
                raise self._exception(
                    f"{status.name.replace('_', ' ')}: {error}", level="danger"
                ) from None

        except httpx.HTTPError as http_err:
            raise self._exception(parse_exception(http_err), level="danger") from None

        return self._parse_response(response)

    async def _aget(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="GET", endpoint=endpoint, **kwargs)

    async def _apost(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="POST", endpoint=endpoint, **kwargs)

    async def _aput(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="PUT", endpoint=endpoint, **kwargs)

    async def _adelete(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="DELETE", endpoint=endpoint, **kwargs)

    async def _apatch(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="PATCH", endpoint=endpoint, **kwargs)

    async def _ahead(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return await self._arequest(method="HEAD", endpoint=endpoint, **kwargs)

    def _request(  # noqa: C901
        self: "BaseExternal",
        method: HttpMethod,
        endpoint: str,
        item: t.Union[str, int, None] = None,
        headers: t.Dict[str, str] = None,
        params: t.Dict[str, JsonValue[Primitives]] = None,
        data: t.Optional[t.Any] = None,
        timeout: t.Optional[int] = None,
        response_required: bool = False,
    ) -> t.Any:
        """Run HTTP POST operation."""
        request = self._build_request(
            method=method,
            endpoint=endpoint,
            item=item,
            headers=headers,
            params=params,
            data=data,
            timeout=timeout,
            response_required=response_required,
        )

        try:
            response = self._session.request(**request)

            if response.status_code not in range(200, 300):
                status = httpx.codes(response.status_code)
                error = self._parse_response(response)
                raise self._exception(
                    f"{status.name.replace('_', ' ')}: {error}", level="danger"
                ) from None

        except httpx.HTTPError as http_err:
            raise self._exception(parse_exception(http_err), level="danger") from None

        return self._parse_response(response)

    def _get(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="GET", endpoint=endpoint, **kwargs)

    def _post(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="POST", endpoint=endpoint, **kwargs)

    def _put(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="PUT", endpoint=endpoint, **kwargs)

    def _delete(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="DELETE", endpoint=endpoint, **kwargs)

    def _patch(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="PATCH", endpoint=endpoint, **kwargs)

    def _head(self: "BaseExternal", endpoint: str, **kwargs: t.Any) -> t.Any:
        return self._request(method="HEAD", endpoint=endpoint, **kwargs)


class BaseWebhook(BaseExternal):
    """Base webhook session handler, which sends requests to the configured URL."""

    config: "Http"

    def __init__(self: "BaseWebhook", config: "Http", parse: bool = True) -> None:
        """Initialize external base class with the webhook's connection details."""
        headers = config.headers.copy()
        auth = None
        if config.authentication is not None:
            if config.authentication.mode == "api_key":
                headers.update(config.authentication.api_key())
            else:
                auth = config.authentication.basic()

        super().__init__(
            base_url=f"{config.host.scheme}://{config.host.host}:{config.host.port}",
            config=config,
            verify_ssl=config.verify_ssl,
            timeout=config.timeout,
            parse=parse,
            headers=headers,
            auth=auth,
        )

    @property
    def url(self: "BaseWebhook") -> str:
        """Get the webhook URL, with configured parameters added to its query string."""
        url = httpx.URL(str(self.config.host))
        if self.config.params:
            query = "&".join(q for q in (url.query.decode(), urlencode(self.config.params)) if q)
            url = url.copy_with(query=query.encode())
        return str(url)

    async def _send(self: "BaseWebhook", data: t.Dict[str, t.Any]) -> t.Any:
        """POST data to the webhook URL."""
        return await self._apost(endpoint=self.url, data=data)
