"""Core API client that mirrors the TypeScript ``createAPIClient`` helper.

The client communicates with a tRPC backend over HTTP using the *batch*
protocol and exposes procedures via attribute access::

    client = create_api_client(api_key="…")
    countries = await client.country.getAllCountries()
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from .pagination import PageResult, auto_paginate
from .rate_limiter import RateLimiter

logger = logging.getLogger("warera_api")

_DEFAULT_URL = "https://api2.warera.io/trpc"
_MAX_URL_LENGTH = 16_000


class APIClient:
    """Async tRPC client with batching, rate limiting and auto-pagination.

    You should normally use :func:`create_api_client` instead of
    instantiating this class directly.

    Parameters
    ----------
    url:
        Base URL of the tRPC API.
    api_key:
        Optional API key (sent as ``x-api-key`` header).
    rate_limit:
        Maximum requests per minute.  Defaults to 200 when *api_key* is
        provided, 100 otherwise.
    headers:
        Additional HTTP headers to include with every request.
    enable_logging:
        When *True*, request/response details are logged at DEBUG level.
    http_client:
        Optional pre-configured :class:`httpx.AsyncClient`.  When omitted
        a new client is created (and owned by this instance).
    """

    def __init__(
        self,
        *,
        url: str = _DEFAULT_URL,
        api_key: str | None = None,
        rate_limit: int | None = None,
        headers: dict[str, str] | None = None,
        enable_logging: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        effective_rate = rate_limit or (200 if api_key else 100)
        self._url = url.rstrip("/")
        self._headers: dict[str, str] = {**(headers or {})}
        if api_key:
            self._headers["x-api-key"] = api_key
        self._limiter = RateLimiter(effective_rate)
        self._logging = enable_logging
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient()

    # -- low-level helpers ---------------------------------------------------

    async def _raw_query(self, path: str, params: dict[str, Any]) -> Any:
        """Execute a single tRPC query (batch-of-one) and return the result."""
        await self._limiter.acquire()

        url = f"{self._url}/{path}?batch=1"
        body = json.dumps({"0": {"json": params}})
        hdrs = {**self._headers, "content-type": "application/json"}

        if self._logging:
            logger.debug("POST %s  body=%s", url, body)

        resp = await self._http.post(url, content=body, headers=hdrs)
        resp.raise_for_status()
        data = resp.json()

        if self._logging:
            logger.debug("Response %s: %s", resp.status_code, data)

        # tRPC batch response is a JSON array
        if isinstance(data, list) and len(data) > 0:
            result_wrapper = data[0].get("result", {})
            return result_wrapper.get("data", {}).get("json")

        return data

    async def query(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Public query method – supports auto-pagination when requested.

        If *params* contains ``auto_paginate=True`` the return value is an
        :class:`AsyncIterator[PageResult]` instead of a plain result.
        """
        params = dict(params) if params else {}

        auto_pag = params.pop("auto_paginate", False)
        max_pages = params.pop("max_pages", None)
        cursor_end = params.pop("cursor_end", None)

        if auto_pag:
            return auto_paginate(
                self._raw_query,
                path,
                params,
                max_pages=max_pages,
                cursor_end=cursor_end,
            )

        return await self._raw_query(path, params)

    # -- proxy / attribute access --------------------------------------------

    def __getattr__(self, name: str) -> "_ProcedureProxy":
        # Avoid intercepting dunder attributes
        if name.startswith("_"):
            raise AttributeError(name)
        return _ProcedureProxy(self, (name,))

    # -- lifecycle -----------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP client (if owned by this instance)."""
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> "APIClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


class _ProcedureProxy:
    """Proxy that builds a dot-separated procedure path via attribute access.

    Calling the proxy invokes :meth:`APIClient.query` with the accumulated
    path::

        client.country.getAllCountries()  # → query("country.getAllCountries", {})
    """

    __slots__ = ("_client", "_parts")

    def __init__(self, client: APIClient, parts: tuple[str, ...]) -> None:
        self._client = client
        self._parts = parts

    def __getattr__(self, name: str) -> "_ProcedureProxy":
        if name.startswith("_"):
            raise AttributeError(name)
        return _ProcedureProxy(self._client, (*self._parts, name))

    def __call__(self, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Invoke the tRPC procedure.

        Parameters can be passed either as a single *dict* positional
        argument or as keyword arguments (or both, merged).
        """
        merged: dict[str, Any] = {}
        if params:
            merged.update(params)
        if kwargs:
            merged.update(kwargs)
        path = ".".join(self._parts)
        return self._client.query(path, merged)


def create_api_client(
    *,
    url: str = _DEFAULT_URL,
    api_key: str | None = None,
    rate_limit: int | None = None,
    headers: dict[str, str] | None = None,
    enable_logging: bool = False,
    http_client: httpx.AsyncClient | None = None,
) -> APIClient:
    """Create a new :class:`APIClient`.

    This is the main entry-point of the package — equivalent to
    ``createAPIClient`` in the original TypeScript library.

    Parameters
    ----------
    url:
        Base URL of the tRPC API.  Defaults to ``https://api2.warera.io/trpc``.
    api_key:
        Optional API key for the ``x-api-key`` header.
    rate_limit:
        Requests per minute (default: 200 with *api_key*, 100 without).
    headers:
        Extra headers to include on every request.
    enable_logging:
        Enable DEBUG-level logging of requests / responses.
    http_client:
        Pre-configured :class:`httpx.AsyncClient` to use.
    """
    return APIClient(
        url=url,
        api_key=api_key,
        rate_limit=rate_limit,
        headers=headers,
        enable_logging=enable_logging,
        http_client=http_client,
    )
