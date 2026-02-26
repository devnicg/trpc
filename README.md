# WarEra API Client (Python)

A Python 3.12+ client for the [WarEra.io](https://app.warera.io) tRPC API with built-in rate limiting and automatic cursor-based pagination.

## Features

- Attribute-based procedure access — no manual endpoint strings.
- Built-in rate limiting aligned to API requirements.
- **Automatic cursor-based pagination** via async iterators.  See the [Auto-Pagination Guide](./docs/AUTO_PAGINATION.md).
- Lightweight — only depends on [httpx](https://www.python-httpx.org/).

## Install

```bash
pip install warera-api
```

## Usage

```python
import asyncio
from warera_api import create_api_client

async def main():
    async with create_api_client(api_key="YOUR_KEY") as client:
        countries = await client.country.getAllCountries()
        first_id = countries[0]["_id"]

        country = await client.country.getCountryById(countryId=first_id)
        government = await client.government.getByCountryId(countryId=first_id)

        print("Country:", country)
        print("Government:", government)

asyncio.run(main())
```

## Auto-Pagination

For endpoints that support cursor-based pagination, pass `auto_paginate=True` to receive an async iterator of pages:

```python
import asyncio
from warera_api import create_api_client

async def main():
    async with create_api_client(api_key="YOUR_KEY") as client:
        async for page in await client.article.getArticlesPaginated(
            type="last",
            limit=50,
            auto_paginate=True,
            max_pages=20,
        ):
            print(f"Processing {len(page.items)} articles")
            for article in page.items:
                print(f"- {article['title']}")

asyncio.run(main())
```

See the [Auto-Pagination Guide](./docs/AUTO_PAGINATION.md) for more details and advanced usage patterns.

---

Found an issue?
Open a ticket here: https://github.com/WarEraProjects/TRPC/issues

---

If you wish to support future development, feel free to support the devs:

ZaLimitless (Dog):

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/jvdlanger)
