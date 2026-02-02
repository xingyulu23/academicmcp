"""arXiv API client.

arXiv is a preprint repository for physics, mathematics, computer science, etc.
Uses the official 'arxiv' Python package.
"""

import asyncio
import logging
from typing import Any, cast

import arxiv  # type: ignore[import-untyped]

from ..models import Author, Paper, PaperSource, SearchResult
from .base import BaseClient

logger = logging.getLogger(__name__)


class ArxivClient(BaseClient):
    """Client for arXiv API using the official arxiv package.

    arXiv provides:
    - Preprints in physics, math, CS, and related fields
    - No authentication required
    - Official Python SDK
    """

    SOURCE = PaperSource.ARXIV

    def __init__(
        self,
        timeout: float = 30.0,
        delay_seconds: float = 3.0,
    ) -> None:
        """Initialize arXiv client.

        Args:
            timeout: Request timeout in seconds
            delay_seconds: Delay between API requests (be polite!)
        """
        super().__init__(timeout=timeout)
        self.delay_seconds = delay_seconds
        self._arxiv_client = arxiv.Client(
            page_size=100,
            delay_seconds=delay_seconds,
            num_retries=3,
        )

    def _parse_result(self, result: arxiv.Result) -> Paper:
        """Parse arxiv.Result to Paper model."""
        # Parse authors
        authors = [Author(name=author.name) for author in result.authors]

        # Extract arXiv ID from entry_id
        arxiv_id = result.entry_id
        if arxiv_id:
            # Format: http://arxiv.org/abs/2401.12345v1
            arxiv_id = arxiv_id.split("/")[-1]
            # Remove version suffix for cleaner ID
            if "v" in arxiv_id:
                arxiv_id = arxiv_id.rsplit("v", 1)[0]

        # Get DOI if available
        doi = result.doi

        return Paper(
            id=f"arxiv:{arxiv_id}" if arxiv_id else "",
            title=result.title.replace("\n", " ").strip(),
            authors=authors,
            abstract=result.summary.replace("\n", " ").strip() if result.summary else None,
            year=result.published.year if result.published else None,
            published_date=result.published.date() if result.published else None,
            venue=f"arXiv preprint arXiv:{arxiv_id}",
            doi=doi,
            arxiv_id=arxiv_id,
            url=result.entry_id,
            pdf_url=result.pdf_url,
            source=PaperSource.ARXIV,
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        sort: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        venue: str | None = None,
        **kwargs: Any,
    ) -> SearchResult:
        """Search for papers on arXiv.

        Query syntax:
        - ti:"text" - Search in title
        - au:"name" - Search by author
        - abs:"text" - Search in abstract
        - cat:cs.AI - Filter by category
        - all:"text" - Search all fields

        Args:
            query: Search query with optional field prefixes
            limit: Maximum results
            offset: Results to skip (for pagination)
            sort: Sort order (relevance, publication_date, citation_count)
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            venue: Not directly supported (arXiv categories instead)

        Returns:
            SearchResult with matching papers
        """
        # Check cache
        cache_key = self._search_cache.search_key(
            "arxiv", query, limit, offset, year_from=year_from, year_to=year_to, sort=sort
        )
        cached = self._search_cache.get(cache_key)
        if cached:
            return cast(SearchResult, cached)

        # Build search query
        search_query = query

        # arXiv doesn't have native year filtering in the simple API,
        # we'll filter results after retrieval if needed

        # Determine sort criterion
        sort_criterion = arxiv.SortCriterion.Relevance
        if sort == "publication_date":
            sort_criterion = arxiv.SortCriterion.SubmittedDate
        elif sort == "citation_count":
            # arXiv API doesn't support citation count sorting
            logger.debug("Citation sort not supported by arXiv, defaulting to relevance")

        # Create search object
        search = arxiv.Search(
            query=search_query,
            max_results=limit + offset,  # Fetch enough to handle offset
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending,
        )

        try:
            # Run the blocking arxiv client in a thread pool
            results = await asyncio.to_thread(lambda: list(self._arxiv_client.results(search)))

            # Apply offset
            results = results[offset : offset + limit]

            # Parse results and filter by year if needed
            papers = []
            for result in results:
                try:
                    paper = self._parse_result(result)

                    # Year filter
                    if year_from and paper.year and paper.year < year_from:
                        continue
                    if year_to and paper.year and paper.year > year_to:
                        continue

                    papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to parse arXiv result: {e}")
                    continue

            result = SearchResult(
                total_results=len(papers),  # arXiv doesn't give exact total
                returned_count=len(papers),
                offset=offset,
                has_more=len(results) == limit,  # Assume more if we got full page
                papers=papers,
                query=query,
                source=PaperSource.ARXIV,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
            raise

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get paper details by arXiv ID.

        Args:
            paper_id: arXiv ID (e.g., '2401.12345' or 'arxiv:2401.12345')

        Returns:
            Paper details or None if not found
        """
        # Normalize ID
        arxiv_id = paper_id
        if arxiv_id.lower().startswith("arxiv:"):
            arxiv_id = arxiv_id[6:]

        # Check cache
        cache_key = self._paper_cache.paper_key("arxiv", arxiv_id)
        cached = self._paper_cache.get(cache_key)
        if cached:
            return cast(Paper, cached)

        try:
            search = arxiv.Search(id_list=[arxiv_id])

            results = await asyncio.to_thread(lambda: list(self._arxiv_client.results(search)))

            if results:
                paper = self._parse_result(results[0])
                self._paper_cache.set(cache_key, paper)
                return paper

            return None

        except Exception as e:
            logger.warning(f"arXiv get_paper failed for {paper_id}: {e}")
            return None

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for papers by author on arXiv.

        Args:
            author_name: Author name
            limit: Maximum results
            offset: Pagination offset

        Returns:
            SearchResult with author's papers
        """
        # Use arXiv author search syntax
        return await self.search(
            query=f'au:"{author_name}"',
            limit=limit,
            offset=offset,
        )

    async def search_by_category(
        self,
        category: str,
        query: str | None = None,
        limit: int = 20,
    ) -> SearchResult:
        """Search papers by arXiv category.

        Common categories:
        - cs.AI - Artificial Intelligence
        - cs.LG - Machine Learning
        - cs.CL - Computation and Language
        - cs.CV - Computer Vision
        - stat.ML - Statistics/Machine Learning
        - math.OC - Optimization and Control

        Args:
            category: arXiv category code
            query: Additional search query
            limit: Maximum results

        Returns:
            SearchResult with papers in category
        """
        search_query = f"cat:{category}"
        if query:
            search_query = f"{search_query} AND {query}"

        return await self.search(query=search_query, limit=limit)
