"""Semantic Scholar API client.

Semantic Scholar is an AI-powered research tool.
API Documentation: https://api.semanticscholar.org

Key features: Citation networks, paper recommendations, author profiles.
"""

import logging
from typing import Any, cast

import httpx

from ..bibtex import generate_bibtex
from ..cache import get_bibtex_cache
from ..models import Author, CitationResult, Paper, PaperSource, RelatedPapersResult, SearchResult
from .base import BaseClient

logger = logging.getLogger(__name__)


class SemanticScholarClient(BaseClient):
    """Client for Semantic Scholar API.

    Semantic Scholar provides:
    - AI-powered paper search
    - Paper recommendations
    - Citation network analysis
    - Author profiles and metrics

    Rate limits:
    - Without API key: 100 requests per 5 minutes
    - With API key: ~100 requests per second
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1"
    SOURCE = PaperSource.SEMANTIC_SCHOLAR

    # Fields to request from the API
    PAPER_FIELDS = [
        "paperId",
        "title",
        "abstract",
        "year",
        "venue",
        "authors",
        "citationCount",
        "externalIds",
        "url",
        "publicationDate",
        "journal",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Semantic Scholar client.

        Args:
            api_key: API key for higher rate limits (optional)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.api_key = api_key
        self._bibtex_cache = get_bibtex_cache()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with API key header if provided."""
        client = await super()._get_client()
        if self.api_key and "x-api-key" not in client.headers:
            client.headers["x-api-key"] = self.api_key
        return client

    def _parse_paper(self, data: dict[str, Any]) -> Paper:
        """Parse Semantic Scholar paper object to Paper model."""
        # Parse authors
        authors = []
        for author_data in data.get("authors", []):
            authors.append(
                Author(
                    name=author_data.get("name", "Unknown"),
                    author_id=author_data.get("authorId"),
                )
            )

        # Extract external IDs
        external_ids = data.get("externalIds", {}) or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")

        # Get journal/venue info
        journal = data.get("journal", {}) or {}
        venue = data.get("venue") or journal.get("name")
        volume = journal.get("volume")

        return Paper(
            id=data.get("paperId", ""),
            title=data.get("title", "Untitled"),
            authors=authors,
            abstract=data.get("abstract"),
            year=data.get("year"),
            published_date=data.get("publicationDate"),
            venue=venue,
            volume=volume,
            doi=doi,
            arxiv_id=arxiv_id,
            url=data.get("url"),
            citation_count=data.get("citationCount", 0),
            source=PaperSource.SEMANTIC_SCHOLAR,
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
        """Search for papers on Semantic Scholar.

        Args:
            query: Search query
            limit: Maximum results (1-100)
            offset: Pagination offset
            sort: Sort order (relevance, publication_date, citation_count)
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            venue: Filter by venue (not directly supported, post-filter)

        Returns:
            SearchResult with matching papers
        """
        # Check cache
        cache_key = self._search_cache.search_key(
            "semantic", query, limit, offset, year_from=year_from, year_to=year_to, sort=sort
        )
        cached = self._search_cache.get(cache_key)
        if cached:
            return cast(SearchResult, cached)

        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "fields": ",".join(self.PAPER_FIELDS),
        }

        # Add sort parameter
        if sort == "publication_date":
            params["sort"] = "publicationDate:desc"
        elif sort == "citation_count":
            params["sort"] = "citationCount:desc"
        elif sort == "relevance":
            # Default behavior, no param needed
            pass

        # Add year filter
        if year_from or year_to:
            year_filter = f"{year_from or ''}-{year_to or ''}"
            params["year"] = year_filter

        try:
            response = await self._get(f"{self.BASE_URL}/paper/search", params=params)
            data = response.json()

            papers = []
            for paper_data in data.get("data", []):
                try:
                    paper = self._parse_paper(paper_data)
                    # Post-filter by venue if specified
                    if venue and paper.venue and venue.lower() not in paper.venue.lower():
                        continue
                    papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to parse S2 paper: {e}")
                    continue

            total = data.get("total", len(papers))

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=data.get("next") is not None,
                papers=papers,
                query=query,
                source=PaperSource.SEMANTIC_SCHOLAR,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
            raise

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get paper details by Semantic Scholar ID, DOI, or arXiv ID.

        Args:
            paper_id: S2 paper ID, DOI, arXiv ID, etc.

        Returns:
            Paper details or None if not found
        """
        # Check cache
        cache_key = self._paper_cache.paper_key("semantic", paper_id)
        cached = self._paper_cache.get(cache_key)
        if cached:
            return cast(Paper, cached)

        # Determine ID format
        if paper_id.startswith("10."):
            # Check for arXiv DOI format (10.48550/arXiv.XXXX.XXXXX)
            if "arxiv." in paper_id.lower():
                # Extract arXiv ID from DOI: 10.48550/arXiv.1706.03762 -> 1706.03762
                parts = paper_id.lower().split("arxiv.")
                if len(parts) > 1:
                    lookup_id = f"ARXIV:{parts[1]}"
                else:
                    lookup_id = f"DOI:{paper_id}"
            else:
                lookup_id = f"DOI:{paper_id}"
        elif paper_id.lower().startswith("arxiv:"):
            lookup_id = f"ARXIV:{paper_id[6:]}"
        elif "." in paper_id and not paper_id.startswith("10."):
            # Might be arXiv ID
            lookup_id = f"ARXIV:{paper_id}"
        else:
            # Assume S2 paper ID
            lookup_id = paper_id

        params = {"fields": ",".join(self.PAPER_FIELDS)}

        try:
            response = await self._get(f"{self.BASE_URL}/paper/{lookup_id}", params=params)
            paper = self._parse_paper(response.json())

            self._paper_cache.set(cache_key, paper)
            return paper

        except Exception as e:
            logger.warning(f"S2 get_paper failed for {paper_id}: {e}")
            return None

    async def get_related_papers(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> RelatedPapersResult:
        """Get recommended related papers using Semantic Scholar's AI.

        This is Semantic Scholar's unique feature - AI-powered recommendations!

        Args:
            paper_id: Paper ID to get recommendations for
            limit: Maximum recommendations to return

        Returns:
            RelatedPapersResult with recommended papers
        """
        # First ensure we have a valid S2 paper ID
        paper = await self.get_paper(paper_id)
        if not paper:
            return RelatedPapersResult(
                paper_id=paper_id,
                related_papers=[],
                recommendation_source="semantic_scholar",
            )

        s2_id = paper.id

        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 100),
        }

        try:
            # Use recommendations API
            response = await self._get(
                f"{self.RECOMMENDATIONS_URL}/papers/forpaper/{s2_id}", params=params
            )
            data = response.json()

            related_papers = []
            for paper_data in data.get("recommendedPapers", []):
                try:
                    related_papers.append(self._parse_paper(paper_data))
                except Exception as e:
                    logger.warning(f"Failed to parse recommended paper: {e}")
                    continue

            return RelatedPapersResult(
                paper_id=paper_id,
                related_papers=related_papers,
                recommendation_source="semantic_scholar",
            )

        except Exception as e:
            logger.warning(f"S2 recommendations failed for {paper_id}: {e}")
            return RelatedPapersResult(
                paper_id=paper_id,
                related_papers=[],
                recommendation_source="semantic_scholar",
            )

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for papers by author name.

        Args:
            author_name: Author name to search
            limit: Maximum results
            offset: Pagination offset

        Returns:
            SearchResult with author's papers
        """
        # First search for the author
        params = {
            "query": author_name,
            "limit": 5,
            "fields": "authorId,name,paperCount",
        }

        try:
            response = await self._get(f"{self.BASE_URL}/author/search", params=params)
            data = response.json()

            authors = data.get("data", [])
            if not authors:
                # Fall back to paper search with author filter
                return await self.search(f"author:{author_name}", limit=limit, offset=offset)

            # Get papers from the first matching author
            author_id = authors[0].get("authorId")

            paper_params = {
                "fields": ",".join(self.PAPER_FIELDS),
                "limit": min(limit, 100),
                "offset": offset,
            }

            paper_response = await self._get(
                f"{self.BASE_URL}/author/{author_id}/papers", params=paper_params
            )
            paper_data = paper_response.json()

            papers = []
            for paper_item in paper_data.get("data", []):
                try:
                    papers.append(self._parse_paper(paper_item))
                except Exception as e:
                    logger.warning(f"Failed to parse author paper: {e}")
                    continue

            return SearchResult(
                total_results=len(papers),  # S2 doesn't provide total in this endpoint
                returned_count=len(papers),
                offset=offset,
                has_more=len(papers) == limit,
                papers=papers,
                query=f"author:{author_name}",
                source=PaperSource.SEMANTIC_SCHOLAR,
            )

        except Exception as e:
            logger.error(f"S2 author search failed: {e}")
            raise

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> CitationResult:
        """Get papers that cite this paper.

        Args:
            paper_id: S2 paper ID, DOI, or arXiv ID
            limit: Maximum citing papers to return
            offset: Pagination offset

        Returns:
            CitationResult with citing papers
        """
        paper = await self.get_paper(paper_id)
        if not paper:
            return CitationResult(
                paper_id=paper_id,
                citation_count=0,
                citing_papers=[],
                has_more=False,
            )

        s2_id = paper.id

        params = {
            "fields": ",".join(self.PAPER_FIELDS),
            "limit": min(limit, 100),
            "offset": offset,
        }

        try:
            response = await self._get(f"{self.BASE_URL}/paper/{s2_id}/citations", params=params)
            data = response.json()

            citing_papers = []
            for item in data.get("data", []):
                citing_paper_data = item.get("citingPaper", {})
                if citing_paper_data:
                    try:
                        citing_papers.append(self._parse_paper(citing_paper_data))
                    except Exception as e:
                        logger.warning(f"Failed to parse citing paper: {e}")
                        continue

            total = data.get("total", paper.citation_count or 0)

            return CitationResult(
                paper_id=paper_id,
                citation_count=total,
                citing_papers=citing_papers,
                has_more=data.get("next") is not None,
            )

        except Exception as e:
            logger.warning(f"S2 get_citations failed for {paper_id}: {e}")
            return CitationResult(
                paper_id=paper_id,
                citation_count=paper.citation_count if paper else 0,
                citing_papers=[],
                has_more=False,
            )

    async def get_bibtex(self, paper_id: str) -> str | None:
        """Get BibTeX entry for a paper.

        Generates BibTeX from Semantic Scholar metadata.

        Args:
            paper_id: S2 paper ID, DOI, or arXiv ID

        Returns:
            BibTeX entry string or None if paper not found
        """
        cache_key = self._bibtex_cache.bibtex_key(f"semantic:{paper_id}")
        cached = self._bibtex_cache.get(cache_key)
        if cached:
            return cast(str, cached)

        paper = await self.get_paper(paper_id)
        if paper:
            bibtex = generate_bibtex(paper)
            self._bibtex_cache.set(cache_key, bibtex)
            return bibtex

        return None

    async def get_bibtex_batch(self, paper_ids: list[str]) -> dict[str, str | None]:
        """Get BibTeX entries for multiple papers.

        Args:
            paper_ids: List of paper identifiers

        Returns:
            Dictionary mapping paper_id to BibTeX entry (or None if not found)
        """
        results: dict[str, str | None] = {}
        for paper_id in paper_ids:
            results[paper_id] = await self.get_bibtex(paper_id)
        return results
