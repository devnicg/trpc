"""Cursor-based auto-pagination helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator


@dataclass
class PaginationOptions:
    """Options controlling automatic cursor-based pagination.

    Attributes
    ----------
    auto_paginate:
        When *True* the client returns an async iterator that yields pages
        until all data has been retrieved.
    max_pages:
        Maximum number of pages to retrieve.  ``None`` means no limit.
    cursor_end:
        Stop pagination when the cursor date becomes older than this value.
    """

    auto_paginate: bool = False
    max_pages: int | None = None
    cursor_end: datetime | None = None


@dataclass
class PageResult:
    """A single page returned by the auto-paginator.

    Attributes
    ----------
    items:
        List of items in this page.
    cursor:
        The cursor string for the *next* page (empty string when exhausted).
    """

    items: list[Any] = field(default_factory=list)
    cursor: str = ""


def parse_cursor_date(cursor: str | None) -> datetime | None:
    """Extract and parse the date portion of a ``"{date}|{id}"`` cursor.

    Returns ``None`` when the cursor is empty, malformed, or the date
    cannot be parsed.
    """
    if not cursor:
        return None

    pipe_idx = cursor.find("|")
    if pipe_idx == -1:
        return None

    date_str = cursor[:pipe_idx]
    if date_str == "undefined":
        return None

    # The JS Date constructor is very permissive; Python's fromisoformat is
    # stricter so we fall back to a few common formats.
    for fmt in (
        "%a %b %d %Y %H:%M:%S %Z",            # e.g. "Wed Feb 11 2026 23:32:39 GMT"
        "%a %b %d %Y %H:%M:%S GMT%z",          # with offset
        "%Y-%m-%dT%H:%M:%S.%fZ",               # ISO-8601
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    # Last-ditch: try fromisoformat (handles many ISO variants in 3.11+)
    try:
        return datetime.fromisoformat(date_str.strip())
    except ValueError:
        return None


async def auto_paginate(
    query_fn: Any,
    path: str,
    params: dict[str, Any],
    *,
    max_pages: int | None = None,
    cursor_end: datetime | None = None,
) -> AsyncIterator[PageResult]:
    """Async generator that pages through a cursor-based tRPC endpoint.

    Parameters
    ----------
    query_fn:
        Callable ``async def query_fn(path, params) -> dict`` that executes
        a single tRPC query.
    path:
        Dot-separated procedure path (e.g. ``"article.getArticlesPaginated"``).
    params:
        The base input parameters (without pagination-specific keys).
    max_pages:
        Stop after this many pages.  ``None`` = unlimited.
    cursor_end:
        Stop when the next cursor's date is older than this datetime.

    Yields
    ------
    PageResult
        One result per page.
    """
    current_cursor: str | None = params.get("cursor")
    page_count = 0
    limit = max_pages if max_pages is not None else float("inf")

    while page_count < limit:
        request_params = dict(params)
        if current_cursor:
            request_params["cursor"] = current_cursor

        response = await query_fn(path, request_params)

        items = response.get("items", [])
        next_cursor: str = response.get("nextCursor", "") or ""

        yield PageResult(items=items, cursor=next_cursor)
        page_count += 1

        # Termination conditions
        if not next_cursor or len(items) == 0 or "undefined" in next_cursor:
            break

        if cursor_end is not None:
            cursor_date = parse_cursor_date(next_cursor)
            if cursor_date is not None and cursor_date < cursor_end:
                break

        current_cursor = next_cursor
