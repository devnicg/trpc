# Auto-Pagination Feature

## Overview

The WarEra API client supports automatic cursor-based pagination for endpoints that return paginated results. This allows you to easily iterate through all pages of data without manually managing cursors.

## Supported Endpoints

The following 8 endpoints support auto-pagination:

- `article.getArticlesPaginated`
- `battle.getBattles`
- `company.getCompanies`
- `event.getEventsPaginated`
- `mu.getManyPaginated`
- `transaction.getPaginatedTransactions`
- `user.getUsersByCountry`
- `workOffer.getWorkOffersPaginated`

## Usage

### Basic Auto-Pagination

To enable auto-pagination, add `auto_paginate=True` to your request:

```python
import asyncio
from warera_api import create_api_client

async def main():
    async with create_api_client(api_key="your-api-key") as client:
        async for page in await client.article.getArticlesPaginated(
            type="last",
            limit=20,
            auto_paginate=True,
            max_pages=20,
        ):
            print(f"Received {len(page.items)} articles")
            for article in page.items:
                print(article["title"])
            print(f"Cursor: {page.cursor}")

asyncio.run(main())
```

### Options

#### `auto_paginate: bool`

When set to `True`, the client returns an async iterator that yields pages until all data is retrieved.

```python
await client.article.getArticlesPaginated(auto_paginate=True)
```

#### `max_pages: int | None`

Limit the maximum number of pages to retrieve. Useful to prevent runaway pagination or for testing.

```python
await client.article.getArticlesPaginated(auto_paginate=True, max_pages=5)
```

**Default**: `None` (no limit)

#### `cursor_end: datetime | None`

Stop pagination when the cursor date becomes older than this date. The cursor format includes a timestamp that is parsed and compared.

```python
from datetime import datetime

await client.article.getArticlesPaginated(
    auto_paginate=True,
    cursor_end=datetime(2026, 2, 15),
)
```

**Default**: `None` (no date filtering)

**Note**: Cursors have the format `"{date}|{id}"`. The date portion is extracted and parsed for comparison.

## Return Types

### With Auto-Pagination

When `auto_paginate=True`, the call returns an `AsyncIterator[PageResult]`:

```python
@dataclass
class PageResult:
    items: list[Any]   # Items for this page
    cursor: str        # Cursor for the next page (empty string when exhausted)
```

### Without Auto-Pagination (Regular Call)

Without `auto_paginate`, the call returns the raw JSON response:

```python
{
    "items": [...],
    "nextCursor": "..."
}
```

## Examples

### Example 1: Collect All Items

```python
async with create_api_client() as client:
    all_battles = []
    async for page in await client.battle.getBattles(
        auto_paginate=True, max_pages=10, limit=50
    ):
        all_battles.extend(page.items)

    print(f"Total battles: {len(all_battles)}")
```

### Example 2: Date-Based Filtering

```python
from datetime import datetime, timedelta

one_week_ago = datetime.now() - timedelta(weeks=1)

async with create_api_client() as client:
    async for page in await client.event.getEventsPaginated(
        auto_paginate=True, cursor_end=one_week_ago, limit=100
    ):
        process_events(page.items)
```

### Example 3: Early Termination

```python
async with create_api_client() as client:
    found = False
    async for page in await client.company.getCompanies(auto_paginate=True):
        for company in page.items:
            if company["name"] == "Target Company":
                found = True
                break
        if found:
            break
```

### Example 4: Regular (Non-Paginated) Call

```python
async with create_api_client() as client:
    result = await client.article.getArticlesPaginated(type="last", limit=10)
    print(f"Items: {len(result['items'])}")
    print(f"Next cursor: {result['nextCursor']}")
```

## Rate Limiting

Auto-pagination respects the existing rate limiting:

- Default: 100 requests per minute (without API key)
- With API key: 200 requests per minute
- Configurable via `rate_limit` option

Each page request counts toward the rate limit and is automatically queued and delayed as needed.

## Termination Conditions

Auto-pagination stops when any of the following conditions is met:

1. **No more data**: The API returns an empty or null `nextCursor`
2. **Max pages reached**: The `max_pages` limit is hit
3. **Cursor date exceeded**: When using `cursor_end`, pagination stops when the next cursor's date is older than the specified date

## Error Handling

Errors during pagination will raise and stop the iteration:

```python
try:
    async for page in await client.battle.getBattles(auto_paginate=True):
        ...  # process page
except Exception as exc:
    print(f"Pagination failed: {exc}")
```

## Migration from TypeScript

| TypeScript | Python |
|---|---|
| `autoPaginate: true` | `auto_paginate=True` |
| `maxPages: 5` | `max_pages=5` |
| `cursorEnd: new Date(...)` | `cursor_end=datetime(...)` |
| `for await (const page of ...)` | `async for page in await ...` |

## Implementation Notes

- Cursor format: `"{date}|{id}"` where date is a parseable date string
- Empty cursors, malformed cursors, or unparseable dates are handled gracefully
- All 8 paginated endpoints follow the same response pattern: `{"items": [...], "nextCursor": "..."}`
- The feature is zero-cost for non-paginated endpoints and backward compatible
