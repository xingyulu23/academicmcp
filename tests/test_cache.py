"""Tests for cache module."""


from academix.cache import (
    APICache,
    BibTeXCache,
    PaperCache,
    SearchCache,
    clear_all_caches,
    get_bibtex_cache,
    get_paper_cache,
    get_search_cache,
)


class TestAPICache:
    """Tests for base APICache class."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = APICache(maxsize=100, ttl=300)
        cache.set("key1", "value1")

        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self):
        """Test getting non-existent key."""
        cache = APICache(maxsize=100, ttl=300)

        assert cache.get("nonexistent") is None

    def test_invalidate(self):
        """Test cache invalidation."""
        cache = APICache(maxsize=100, ttl=300)
        cache.set("key1", "value1")

        assert cache.invalidate("key1") is True
        assert cache.get("key1") is None

    def test_invalidate_nonexistent(self):
        """Test invalidating non-existent key."""
        cache = APICache(maxsize=100, ttl=300)

        assert cache.invalidate("nonexistent") is False

    def test_clear(self):
        """Test clearing all cache entries."""
        cache = APICache(maxsize=100, ttl=300)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_stats(self):
        """Test cache statistics."""
        cache = APICache(maxsize=100, ttl=300)
        cache.set("key1", "value1")

        # Generate hits and misses
        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("nonexistent")  # miss

        stats = cache.stats

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_make_key(self):
        """Test cache key generation."""
        cache = APICache()

        key1 = cache._make_key("prefix", "arg1", "arg2", foo="bar")
        key2 = cache._make_key("prefix", "arg1", "arg2", foo="bar")
        key3 = cache._make_key("prefix", "arg1", "arg2", foo="baz")

        assert key1 == key2
        assert key1 != key3


class TestSearchCache:
    """Tests for SearchCache."""

    def test_search_key_generation(self):
        """Test search cache key generation."""
        cache = SearchCache()

        key1 = cache.search_key("openalex", "machine learning", limit=10, offset=0)
        key2 = cache.search_key("openalex", "machine learning", limit=10, offset=0)
        key3 = cache.search_key("openalex", "deep learning", limit=10, offset=0)

        assert key1 == key2
        assert key1 != key3

    def test_case_insensitive_query(self):
        """Test that queries are case-insensitive."""
        cache = SearchCache()

        key1 = cache.search_key("openalex", "Machine Learning")
        key2 = cache.search_key("openalex", "machine learning")

        assert key1 == key2


class TestPaperCache:
    """Tests for PaperCache."""

    def test_paper_key_generation(self):
        """Test paper cache key generation."""
        cache = PaperCache()

        key1 = cache.paper_key("openalex", "W12345")
        key2 = cache.paper_key("openalex", "W12345")
        key3 = cache.paper_key("dblp", "W12345")

        assert key1 == key2
        assert key1 != key3


class TestBibTeXCache:
    """Tests for BibTeXCache."""

    def test_bibtex_key_generation(self):
        """Test BibTeX cache key generation."""
        cache = BibTeXCache()

        key1 = cache.bibtex_key("10.1038/nature12345")
        key2 = cache.bibtex_key("10.1038/nature12345")
        key3 = cache.bibtex_key("10.1038/nature67890")

        assert key1 == key2
        assert key1 != key3


class TestGlobalCaches:
    """Tests for global cache instances."""

    def test_get_search_cache(self):
        """Test getting global search cache."""
        cache1 = get_search_cache()
        cache2 = get_search_cache()

        assert cache1 is cache2

    def test_get_paper_cache(self):
        """Test getting global paper cache."""
        cache1 = get_paper_cache()
        cache2 = get_paper_cache()

        assert cache1 is cache2

    def test_get_bibtex_cache(self):
        """Test getting global BibTeX cache."""
        cache1 = get_bibtex_cache()
        cache2 = get_bibtex_cache()

        assert cache1 is cache2

    def test_clear_all_caches(self):
        """Test clearing all caches."""
        search_cache = get_search_cache()
        paper_cache = get_paper_cache()
        bibtex_cache = get_bibtex_cache()

        search_cache.set("test_key", "test_value")
        paper_cache.set("test_key", "test_value")
        bibtex_cache.set("test_key", "test_value")

        clear_all_caches()

        assert search_cache.get("test_key") is None
        assert paper_cache.get("test_key") is None
        assert bibtex_cache.get("test_key") is None
