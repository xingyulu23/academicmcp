"""Base client class for academic API clients."""

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..cache import get_paper_cache, get_search_cache
from ..models import CitationResult, Paper, PaperSource, SearchResult

logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """Abstract base class for academic API clients."""

    # Default timeout for HTTP requests
    DEFAULT_TIMEOUT = 30.0

    # Source identifier
    SOURCE: PaperSource

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            timeout: HTTP request timeout in seconds
            user_agent: Custom User-Agent header
        """
        self.timeout = timeout
        self.user_agent = user_agent or "Academix/0.1.0 (https://github.com/academix)"
        self._client: httpx.AsyncClient | None = None
        self._search_cache = get_search_cache()
        self._paper_cache = get_paper_cache()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with error handling.

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request arguments

        Returns:
            HTTP response

        Raises:
            httpx.HTTPStatusError: For 4xx/5xx responses
            httpx.TimeoutException: For request timeouts
        """
        client = await self._get_client()

        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Timeout for {url}: {e}")
            raise

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request."""
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request."""
        return await self._request("POST", url, **kwargs)

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        sort: str | None = None,
        **kwargs: Any,
    ) -> SearchResult:
        """Search for papers.

        Args:
            query: Search query
            limit: Maximum results to return
            offset: Pagination offset
            sort: Sort order (relevance, publication_date, citation_count)
            **kwargs: Additional search parameters

        Returns:
            SearchResult with matching papers
        """
        ...

    @abstractmethod
    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get paper details by ID.

        Args:
            paper_id: Paper identifier

        Returns:
            Paper details or None if not found
        """
        ...

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> CitationResult:
        """Get papers that cite this paper.

        Args:
            paper_id: Paper identifier
            limit: Maximum citing papers to return
            offset: Pagination offset

        Returns:
            CitationResult with citing papers

        Note:
            Default implementation returns empty result.
            Override in subclasses that support citations.
        """
        return CitationResult(
            paper_id=paper_id,
            citation_count=0,
            citing_papers=[],
            has_more=False,
        )

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for papers by author.

        Args:
            author_name: Author name to search
            limit: Maximum results
            offset: Pagination offset

        Returns:
            SearchResult with author's papers

        Note:
            Default implementation uses general search.
            Override for specialized author search.
        """
        return await self.search(
            query=f"author:{author_name}",
            limit=limit,
            offset=offset,
        )
