"""CrossRef API client.

CrossRef is the DOI registration authority.
API Documentation: https://api.crossref.org

Key feature: Authoritative DOI resolution and metadata.
"""

import logging
from typing import Any, cast

from ..bibtex import generate_bibtex
from ..cache import get_bibtex_cache
from ..models import Author, Paper, PaperSource, SearchResult
from .base import BaseClient

logger = logging.getLogger(__name__)


class CrossRefClient(BaseClient):
    """Client for CrossRef API.

    CrossRef provides:
    - DOI resolution and metadata
    - Publisher-authoritative bibliographic data
    - Reference lists and citation data

    Rate limits:
    - Polite pool (with email): Higher limits, priority access
    - Anonymous: Lower limits
    """

    BASE_URL = "https://api.crossref.org"
    SOURCE = PaperSource.CROSSREF

    def __init__(
        self,
        email: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize CrossRef client.

        Args:
            email: Email for polite pool access (recommended)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.email = email
        self._bibtex_cache = get_bibtex_cache()
        if email:
            self.user_agent = f"Academix/0.1.0 (mailto:{email})"

    def _build_params(self, **kwargs: Any) -> dict[str, Any]:
        """Build request parameters with mailto if provided."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        if self.email:
            params["mailto"] = self.email
        return params

    def _parse_work(self, work: dict[str, Any]) -> Paper:
        """Parse CrossRef work object to Paper model."""
        # Parse authors
        authors = []
        for author_data in work.get("author", []):
            name_parts = []
            if author_data.get("given"):
                name_parts.append(author_data["given"])
            if author_data.get("family"):
                name_parts.append(author_data["family"])

            if name_parts:
                authors.append(
                    Author(
                        name=" ".join(name_parts),
                        orcid=author_data.get("ORCID"),
                        affiliation=self._get_affiliation(author_data),
                    )
                )

        # Extract title
        title_list = work.get("title", [])
        title = title_list[0] if title_list else "Untitled"

        # Extract venue
        venue_list = work.get("container-title", [])
        venue = venue_list[0] if venue_list else None

        # Extract date
        year = None
        date_parts = None

        for date_field in ["published-print", "published-online", "created"]:
            date_info = work.get(date_field, {})
            if date_info and date_info.get("date-parts"):
                date_parts = date_info["date-parts"][0]
                break

        if date_parts:
            year = date_parts[0] if len(date_parts) > 0 else None

        # Extract pages
        pages = work.get("page")

        return Paper(
            id=work.get("DOI", ""),
            title=title,
            authors=authors,
            abstract=work.get("abstract"),
            year=year,
            venue=venue,
            volume=work.get("volume"),
            issue=work.get("issue"),
            pages=pages,
            doi=work.get("DOI"),
            url=work.get("URL") or f"https://doi.org/{work.get('DOI')}",
            citation_count=work.get("is-referenced-by-count", 0),
            source=PaperSource.CROSSREF,
        )

    def _get_affiliation(self, author_data: dict[str, Any]) -> str | None:
        """Extract first affiliation from author data."""
        affiliations = author_data.get("affiliation", [])
        if affiliations and isinstance(affiliations[0], dict):
            return affiliations[0].get("name")
        elif affiliations and isinstance(affiliations[0], str):
            return affiliations[0]
        return None

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
        """Search for works on CrossRef.

        Args:
            query: Search query
            limit: Maximum results (max 1000)
            offset: Pagination offset
            sort: Sort order (relevance, publication_date, citation_count)
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            venue: Filter by container title (journal/proceedings)

        Returns:
            SearchResult with matching works
        """
        # Check cache
        cache_key = self._search_cache.search_key(
            "crossref",
            query,
            limit,
            offset,
            year_from=year_from,
            year_to=year_to,
            venue=venue,
            sort=sort,
        )
        cached = self._search_cache.get(cache_key)
        if cached:
            return cast(SearchResult, cached)

        # Build filter
        filters = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}")
        if year_to:
            filters.append(f"until-pub-date:{year_to}")

        # Map sort parameter
        api_sort = None
        if sort == "publication_date":
            api_sort = "published"
        elif sort == "citation_count":
            api_sort = "is-referenced-by-count"
        elif sort == "relevance":
            api_sort = "relevance"

        params = self._build_params(
            query=query,
            rows=min(limit, 1000),
            offset=offset,
            filter=",".join(filters) if filters else None,
            sort=api_sort,
        )

        try:
            response = await self._get(f"{self.BASE_URL}/works", params=params)
            data = response.json()

            message = data.get("message", {})
            papers = []

            for work in message.get("items", []):
                try:
                    paper = self._parse_work(work)

                    # Post-filter by venue if specified
                    if venue and paper.venue and venue.lower() not in paper.venue.lower():
                        continue

                    papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to parse CrossRef work: {e}")
                    continue

            total = message.get("total-results", len(papers))

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=offset + len(papers) < total,
                papers=papers,
                query=query,
                source=PaperSource.CROSSREF,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"CrossRef search failed: {e}")
            raise

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get work details by DOI.

        Args:
            paper_id: DOI (with or without prefix)

        Returns:
            Paper details or None if not found
        """
        # Normalize DOI
        doi = paper_id
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("http://doi.org/"):
            doi = doi[15:]
        elif doi.startswith("doi:"):
            doi = doi[4:]

        # Check cache
        cache_key = self._paper_cache.paper_key("crossref", doi)
        cached = self._paper_cache.get(cache_key)
        if cached:
            return cast(Paper, cached)

        params = self._build_params()

        try:
            response = await self._get(f"{self.BASE_URL}/works/{doi}", params=params)
            data = response.json()

            paper = self._parse_work(data.get("message", {}))
            self._paper_cache.set(cache_key, paper)
            return paper

        except Exception as e:
            logger.warning(f"CrossRef get_paper failed for {paper_id}: {e}")
            return None

    async def resolve_doi(self, doi: str) -> Paper | None:
        """Resolve a DOI to get full metadata.

        This is CrossRef's core function - authoritative DOI resolution.

        Args:
            doi: DOI to resolve

        Returns:
            Paper metadata or None if DOI not found
        """
        return await self.get_paper(doi)

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for works by author name.

        Args:
            author_name: Author name to search
            limit: Maximum results
            offset: Pagination offset

        Returns:
            SearchResult with author's works
        """
        # CrossRef uses query.author for author searches
        cache_key = self._search_cache.search_key("crossref_author", author_name, limit, offset)
        cached = self._search_cache.get(cache_key)
        if cached:
            return cast(SearchResult, cached)

        params = self._build_params(
            **{"query.author": author_name},
            rows=min(limit, 1000),
            offset=offset,
        )

        try:
            response = await self._get(f"{self.BASE_URL}/works", params=params)
            data = response.json()

            message = data.get("message", {})
            papers = [self._parse_work(work) for work in message.get("items", [])]

            total = message.get("total-results", len(papers))

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=offset + len(papers) < total,
                papers=papers,
                query=f"author:{author_name}",
                source=PaperSource.CROSSREF,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"CrossRef author search failed: {e}")
            raise

    async def get_bibtex(self, paper_id: str) -> str | None:
        """Get BibTeX entry for a paper by DOI.

        Generates BibTeX from CrossRef metadata.

        Args:
            paper_id: DOI (with or without prefix)

        Returns:
            BibTeX entry string or None if paper not found
        """
        cache_key = self._bibtex_cache.bibtex_key(f"crossref:{paper_id}")
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
            paper_ids: List of DOIs

        Returns:
            Dictionary mapping paper_id to BibTeX entry (or None if not found)
        """
        results: dict[str, str | None] = {}
        for paper_id in paper_ids:
            results[paper_id] = await self.get_bibtex(paper_id)
        return results
