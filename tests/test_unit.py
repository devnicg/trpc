"""Unit tests for the warera_api package.

These tests do **not** require a live API connection — all HTTP traffic is
mocked via httpx transports.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import pytest

from warera_api import create_api_client, PageResult, PaginationOptions
from warera_api.client import APIClient, _ProcedureProxy
from warera_api.pagination import parse_cursor_date, auto_paginate
from warera_api.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trpc_batch_response(result: Any) -> list[dict]:
    """Wrap *result* in the tRPC batch envelope."""
    return [{"result": {"data": {"json": result}}}]


class _MockTransport(httpx.AsyncBaseTransport):
    """Return canned responses keyed by the procedure path in the URL."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # The procedure path sits between the last `/` and `?batch=1`
        url_path = request.url.path.rsplit("/", 1)[-1]
        body = _trpc_batch_response(self._responses.get(url_path, {}))
        return httpx.Response(200, json=body)


# ---------------------------------------------------------------------------
# parse_cursor_date
# ---------------------------------------------------------------------------


class TestParseCursorDate:
    def test_valid_iso_cursor(self) -> None:
        cursor = "2026-02-11T23:32:39.000Z|698bbff3f4d930a30ffbe671"
        result = parse_cursor_date(cursor)
        assert result is not None
        assert result.year == 2026

    def test_valid_rfc_cursor(self) -> None:
        cursor = "Wed Feb 11 2026 23:32:39 GMT+0000|698bbff3f4d930a30ffbe671"
        result = parse_cursor_date(cursor)
        assert result is not None
        assert result.year == 2026

    def test_none_cursor(self) -> None:
        assert parse_cursor_date(None) is None

    def test_empty_cursor(self) -> None:
        assert parse_cursor_date("") is None

    def test_invalid_cursor_no_pipe(self) -> None:
        assert parse_cursor_date("invalid") is None

    def test_undefined_date(self) -> None:
        assert parse_cursor_date("undefined|abc123") is None

    def test_unparseable_date(self) -> None:
        assert parse_cursor_date("not-a-date|abc123") is None


# ---------------------------------------------------------------------------
# PaginationOptions
# ---------------------------------------------------------------------------


class TestPaginationOptions:
    def test_defaults(self) -> None:
        opts = PaginationOptions()
        assert opts.auto_paginate is False
        assert opts.max_pages is None
        assert opts.cursor_end is None

    def test_custom_values(self) -> None:
        dt = datetime(2026, 2, 15)
        opts = PaginationOptions(auto_paginate=True, max_pages=5, cursor_end=dt)
        assert opts.auto_paginate is True
        assert opts.max_pages == 5
        assert opts.cursor_end == dt


# ---------------------------------------------------------------------------
# PageResult
# ---------------------------------------------------------------------------


class TestPageResult:
    def test_defaults(self) -> None:
        page = PageResult()
        assert page.items == []
        assert page.cursor == ""

    def test_with_data(self) -> None:
        page = PageResult(items=[{"id": 1}], cursor="next")
        assert len(page.items) == 1
        assert page.cursor == "next"


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_does_not_raise(self) -> None:
        limiter = RateLimiter(requests_per_minute=6000)
        await limiter.acquire()
        await limiter.acquire()


# ---------------------------------------------------------------------------
# auto_paginate
# ---------------------------------------------------------------------------


class TestAutoPaginate:
    @pytest.mark.asyncio
    async def test_yields_pages_and_stops(self) -> None:
        pages = [
            {"items": [1, 2], "nextCursor": "c1|id1"},
            {"items": [3], "nextCursor": "c2|id2"},
            {"items": [], "nextCursor": ""},
        ]
        call_idx = 0

        async def fake_query(_path: str, _params: dict) -> dict:
            nonlocal call_idx
            page = pages[call_idx]
            call_idx += 1
            return page

        results: list[PageResult] = []
        async for page in auto_paginate(fake_query, "test.path", {}):
            results.append(page)

        assert len(results) == 3
        assert results[0].items == [1, 2]
        assert results[2].items == []

    @pytest.mark.asyncio
    async def test_max_pages(self) -> None:
        async def infinite_query(_path: str, _params: dict) -> dict:
            return {"items": [1], "nextCursor": "2026-01-01T00:00:00Z|id"}

        count = 0
        async for _ in auto_paginate(infinite_query, "p", {}, max_pages=3):
            count += 1

        assert count == 3

    @pytest.mark.asyncio
    async def test_cursor_end(self) -> None:
        responses = [
            {"items": [1], "nextCursor": "2026-03-01T00:00:00.000Z|a"},
            {"items": [2], "nextCursor": "2026-01-01T00:00:00.000Z|b"},  # older than cutoff
        ]
        idx = 0

        async def query(_p: str, _i: dict) -> dict:
            nonlocal idx
            r = responses[idx]
            idx += 1
            return r

        pages: list[PageResult] = []
        async for page in auto_paginate(
            query, "x", {}, cursor_end=datetime(2026, 2, 1)
        ):
            pages.append(page)

        assert len(pages) == 2

    @pytest.mark.asyncio
    async def test_stops_on_undefined_cursor(self) -> None:
        async def query(_p: str, _i: dict) -> dict:
            return {"items": [1], "nextCursor": "undefined|abc"}

        pages = [p async for p in auto_paginate(query, "x", {})]
        assert len(pages) == 1


# ---------------------------------------------------------------------------
# APIClient / _ProcedureProxy (with mocked HTTP)
# ---------------------------------------------------------------------------


class TestAPIClient:
    @pytest.mark.asyncio
    async def test_simple_query(self) -> None:
        transport = _MockTransport(
            {"country.getAllCountries": [{"_id": "1", "name": "TestLand"}]}
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = create_api_client(http_client=http)
            result = await client.country.getAllCountries()
            assert result == [{"_id": "1", "name": "TestLand"}]

    @pytest.mark.asyncio
    async def test_query_with_params(self) -> None:
        transport = _MockTransport(
            {"country.getCountryById": {"_id": "42", "name": "Foo"}}
        )
        async with httpx.AsyncClient(transport=transport) as http:
            client = create_api_client(http_client=http)
            result = await client.country.getCountryById(countryId="42")
            assert result["name"] == "Foo"

    @pytest.mark.asyncio
    async def test_auto_paginate_via_proxy(self) -> None:
        """Calling with auto_paginate=True should return an async iterator."""
        call_count = 0

        class PagTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    body = _trpc_batch_response(
                        {"items": [{"id": 1}], "nextCursor": "2026-03-01T00:00:00Z|x"}
                    )
                else:
                    body = _trpc_batch_response({"items": [], "nextCursor": ""})
                return httpx.Response(200, json=body)

        async with httpx.AsyncClient(transport=PagTransport()) as http:
            client = create_api_client(http_client=http)
            pages: list[PageResult] = []
            async for page in await client.article.getArticlesPaginated(
                auto_paginate=True, limit=5
            ):
                pages.append(page)

            assert len(pages) == 2
            assert pages[0].items == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_headers_include_api_key(self) -> None:
        sent_headers: dict[str, str] = {}

        class CapturingTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                sent_headers.update(dict(request.headers))
                return httpx.Response(200, json=_trpc_batch_response({}))

        async with httpx.AsyncClient(transport=CapturingTransport()) as http:
            client = create_api_client(api_key="secret", http_client=http)
            await client.test.noop()

        assert sent_headers.get("x-api-key") == "secret"

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        async with create_api_client() as client:
            assert isinstance(client, APIClient)


# ---------------------------------------------------------------------------
# Pagination option extraction
# ---------------------------------------------------------------------------


class TestPaginationOptionExtraction:
    def test_options_removed_from_params(self) -> None:
        """Verify that pagination-specific keys are stripped before querying."""
        original = {
            "type": "last",
            "limit": 10,
            "auto_paginate": True,
            "max_pages": 5,
            "cursor_end": datetime(2026, 2, 15),
        }
        cleaned = dict(original)
        cleaned.pop("auto_paginate")
        cleaned.pop("max_pages")
        cleaned.pop("cursor_end")

        assert "auto_paginate" not in cleaned
        assert "max_pages" not in cleaned
        assert "cursor_end" not in cleaned
        assert cleaned == {"type": "last", "limit": 10}
