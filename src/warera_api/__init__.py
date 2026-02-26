"""WarEra API client – Python edition.

Provides a lightweight, batching-aware, rate-limited client for the
WarEra.io tRPC API with automatic cursor-based pagination support.
"""

from .client import APIClient, create_api_client
from .pagination import PageResult, PaginationOptions

__all__ = [
    "APIClient",
    "create_api_client",
    "PageResult",
    "PaginationOptions",
]
