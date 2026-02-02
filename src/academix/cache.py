"""In-memory cache with TTL support for API responses."""

import hashlib
from typing import Any

from cachetools import TTLCache


class APICache:
    """In-memory cache with TTL for API responses.

    Note: Not thread-safe. Designed for single-threaded async event loop usage.

    Uses cachetools.TTLCache for automatic expiration.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        ttl: int = 300,  # 5 minutes default
    ) -> None:
        """Initialize cache.

        Args:
            maxsize: Maximum number of items to cache
            ttl: Time-to-live in seconds for cached items
        """
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=ttl)
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        """Generate a cache key from prefix and arguments."""
        # Create a stable string representation
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_string = "|".join(key_parts)
        # Hash for consistent key length
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        try:
            value = self._cache[key]
            self._hits += 1
            return value
        except KeyError:
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = value

    def get_or_set(self, key: str, factory: Any) -> Any:
        """Get from cache or compute and store.

        Args:
            key: Cache key
            factory: Callable to produce value if not cached

        Returns:
            Cached or newly computed value
        """
        value = self.get(key)
        if value is not None:
            return value

        # Compute new value
        value = factory() if callable(factory) else factory
        self.set(key, value)
        return value

    def invalidate(self, key: str) -> bool:
        """Remove item from cache.

        Args:
            key: Cache key to invalidate

        Returns:
            True if item was found and removed
        """
        try:
            del self._cache[key]
            return True
        except KeyError:
            return False

    def clear(self) -> None:
        """Clear all cached items."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1%}",
        }


class SearchCache(APICache):
    """Specialized cache for search queries."""

    def __init__(self, maxsize: int = 500, ttl: int = 600) -> None:
        """Initialize search cache with 10-minute TTL."""
        super().__init__(maxsize=maxsize, ttl=ttl)

    def search_key(
        self,
        source: str,
        query: str,
        limit: int = 10,
        offset: int = 0,
        **filters: Any,
    ) -> str:
        """Generate cache key for search query."""
        return self._make_key(
            f"search:{source}",
            query.lower().strip(),
            limit=limit,
            offset=offset,
            **filters,
        )


class PaperCache(APICache):
    """Specialized cache for paper details."""

    def __init__(self, maxsize: int = 2000, ttl: int = 3600) -> None:
        """Initialize paper cache with 1-hour TTL."""
        super().__init__(maxsize=maxsize, ttl=ttl)

    def paper_key(self, source: str, paper_id: str) -> str:
        """Generate cache key for paper details."""
        return self._make_key(f"paper:{source}", paper_id)


class BibTeXCache(APICache):
    """Specialized cache for BibTeX entries."""

    def __init__(self, maxsize: int = 1000, ttl: int = 86400) -> None:
        """Initialize BibTeX cache with 24-hour TTL."""
        super().__init__(maxsize=maxsize, ttl=ttl)

    def bibtex_key(self, paper_id: str) -> str:
        """Generate cache key for BibTeX entry."""
        return self._make_key("bibtex", paper_id)


# Global cache instances
_search_cache: SearchCache | None = None
_paper_cache: PaperCache | None = None
_bibtex_cache: BibTeXCache | None = None


def get_search_cache() -> SearchCache:
    """Get global search cache instance."""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache()
    return _search_cache


def get_paper_cache() -> PaperCache:
    """Get global paper cache instance."""
    global _paper_cache
    if _paper_cache is None:
        _paper_cache = PaperCache()
    return _paper_cache


def get_bibtex_cache() -> BibTeXCache:
    """Get global BibTeX cache instance."""
    global _bibtex_cache
    if _bibtex_cache is None:
        _bibtex_cache = BibTeXCache()
    return _bibtex_cache


def clear_all_caches() -> None:
    """Clear all cache instances."""
    if _search_cache:
        _search_cache.clear()
    if _paper_cache:
        _paper_cache.clear()
    if _bibtex_cache:
        _bibtex_cache.clear()


def get_all_cache_stats() -> dict[str, dict[str, Any]]:
    """Get statistics from all caches."""
    return {
        "search": get_search_cache().stats,
        "paper": get_paper_cache().stats,
        "bibtex": get_bibtex_cache().stats,
    }
