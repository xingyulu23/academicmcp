"""OpenAlex API client.

OpenAlex is an open catalog of the global research system.
API Documentation: https://docs.openalex.org
"""

import logging
from typing import Any, cast
from urllib.parse import quote_plus

from ..bibtex import generate_bibtex
from ..cache import get_bibtex_cache
from ..models import (
    Author,
    CitationNetworkEdge,
    CitationNetworkNode,
    CitationResult,
    Paper,
    PaperSource,
    SearchResult,
)
from .base import BaseClient

logger = logging.getLogger(__name__)


class OpenAlexClient(BaseClient):
    """Client for OpenAlex API.

    OpenAlex provides:
    - Comprehensive paper search
    - Citation counts and networks
    - Author and institution data
    - Free tier: 100,000 API calls/day with email
    """

    BASE_URL = "https://api.openalex.org"
    SOURCE = PaperSource.OPENALEX

    def __init__(
        self,
        email: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize OpenAlex client.

        Args:
            email: Email for polite pool (recommended for higher rate limits)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.email = email
        self._bibtex_cache = get_bibtex_cache()
        # Update user agent to include email for polite access
        if email:
            self.user_agent = f"Academix/0.1.0 (mailto:{email})"

    def _build_params(self, **kwargs: Any) -> dict[str, Any]:
        """Build request parameters with email if provided."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        if self.email:
            params["mailto"] = self.email
        return params

    def _parse_work(self, work: dict[str, Any]) -> Paper:
        """Parse OpenAlex work object to Paper model."""
        # Extract authors
        authors = []
        for authorship in work.get("authorships", []):
            author_data = authorship.get("author", {})
            author = Author(
                name=author_data.get("display_name", "Unknown"),
                orcid=author_data.get("orcid"),
                author_id=author_data.get("id"),
            )
            # Add affiliation from first institution
            institutions = authorship.get("institutions", [])
            if institutions:
                author.affiliation = institutions[0].get("display_name")
            authors.append(author)

        # Extract venue from primary location
        venue = None
        primary_location = work.get("primary_location", {})
        if primary_location:
            source = primary_location.get("source")
            if source:
                venue = source.get("display_name")

        # Extract DOI
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[16:]  # Remove prefix

        # Extract biblio info
        biblio = work.get("biblio", {})

        return Paper(
            id=work.get("id", "").split("/")[-1] if work.get("id") else "",
            title=work.get("display_name") or work.get("title") or "Untitled",
            authors=authors,
            abstract=self._reconstruct_abstract(work.get("abstract_inverted_index")),
            year=work.get("publication_year"),
            published_date=work.get("publication_date"),
            venue=venue,
            volume=biblio.get("volume"),
            issue=biblio.get("issue"),
            pages=self._format_pages(biblio.get("first_page"), biblio.get("last_page")),
            doi=doi,
            url=work.get("id"),  # OpenAlex URL
            pdf_url=self._get_pdf_url(work),
            citation_count=work.get("cited_by_count", 0),
            source=PaperSource.OPENALEX,
        )

    def _reconstruct_abstract(self, inverted_index: dict[str, list[int]] | None) -> str | None:
        """Reconstruct abstract from OpenAlex inverted index format."""
        if not inverted_index:
            return None

        # Build word list from inverted index
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        # Sort by position and join
        word_positions.sort(key=lambda x: x[0])
        return " ".join(word for _, word in word_positions)

    def _format_pages(self, first_page: str | None, last_page: str | None) -> str | None:
        """Format page range."""
        if first_page and last_page:
            return f"{first_page}--{last_page}"
        elif first_page:
            return first_page
        return None

    def _get_pdf_url(self, work: dict[str, Any]) -> str | None:
        """Extract PDF URL from work."""
        # Try primary location first
        primary = work.get("primary_location", {})
        if primary.get("is_oa") and primary.get("pdf_url"):
            return cast(str, primary["pdf_url"])

        # Check other locations
        for location in work.get("locations", []):
            if location.get("is_oa") and location.get("pdf_url"):
                return cast(str, location["pdf_url"])

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
        """Search for papers on OpenAlex.

        Args:
            query: Search query (searches title, abstract, fulltext)
            limit: Maximum results (1-200)
            offset: Pagination offset
            year_from: Filter by minimum publication year
            year_to: Filter by maximum publication year
            venue: Filter by venue name
            sort: Sort order (relevance, publication_date, citation_count)

        Returns:
            SearchResult with matching papers
        """
        # Check cache
        cache_key = self._search_cache.search_key(
            "openalex",
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
            logger.debug(f"Cache hit for OpenAlex search: {query}")
            return cast(SearchResult, cached)

        # Build filter string
        filters = []
        if year_from and year_to:
            filters.append(f"publication_year:{year_from}-{year_to}")
        elif year_from:
            filters.append(f"publication_year:>{year_from - 1}")
        elif year_to:
            filters.append(f"publication_year:<{year_to + 1}")

        if venue:
            filters.append(f"primary_location.source.display_name.search:{quote_plus(venue)}")

        # Map sort parameter
        api_sort = None
        if sort == "publication_date":
            api_sort = "publication_date:desc"
        elif sort == "citation_count":
            api_sort = "cited_by_count:desc"
        elif sort == "relevance":
            api_sort = "relevance_score:desc"

        per_page = 200
        params = self._build_params(
            search=query,
            per_page=per_page,
            page=1 + (offset // per_page) if per_page > 0 else 1,
            filter=",".join(filters) if filters else None,
            sort=api_sort,
        )

        try:
            response = await self._get(f"{self.BASE_URL}/works", params=params)
            data = response.json()

            papers = [self._parse_work(work) for work in data.get("results", [])]
            total = data.get("meta", {}).get("count", 0)

            # Fix pagination: slice to handle offset within page
            offset_within_page = offset % per_page
            papers = papers[offset_within_page:][:limit]

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=offset + len(papers) < total,
                papers=papers,
                query=query,
                source=PaperSource.OPENALEX,
            )

            # Cache result
            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"OpenAlex search failed: {e}")
            raise

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get paper details by OpenAlex ID, DOI, or other identifier.

        Args:
            paper_id: OpenAlex ID (W...), DOI, PMID, etc.

        Returns:
            Paper details or None if not found
        """
        # Check cache
        cache_key = self._paper_cache.paper_key("openalex", paper_id)
        cached = self._paper_cache.get(cache_key)
        if cached:
            return cast(Paper, cached)

        # Determine ID format
        if paper_id.startswith("W"):
            # OpenAlex native ID
            url = f"{self.BASE_URL}/works/{paper_id}"
        elif paper_id.startswith("10."):
            # DOI
            url = f"{self.BASE_URL}/works/doi:{paper_id}"
        elif paper_id.startswith("https://doi.org/"):
            # DOI URL
            url = f"{self.BASE_URL}/works/doi:{paper_id[16:]}"
        else:
            # Try as-is (could be PMID, MAG ID, etc.)
            url = f"{self.BASE_URL}/works/{paper_id}"

        params = self._build_params()

        try:
            response = await self._get(url, params=params)
            paper = self._parse_work(response.json())

            # Cache result
            self._paper_cache.set(cache_key, paper)
            return paper

        except Exception as e:
            logger.warning(f"OpenAlex get_paper failed for {paper_id}: {e}")
            return None

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> CitationResult:
        """Get papers that cite this paper.

        Args:
            paper_id: OpenAlex work ID or DOI
            limit: Maximum citing papers to return
            offset: Pagination offset

        Returns:
            CitationResult with citing papers
        """
        # First get the paper to ensure we have the OpenAlex ID
        paper = await self.get_paper(paper_id)
        if not paper:
            return CitationResult(
                paper_id=paper_id,
                citation_count=0,
                citing_papers=[],
                has_more=False,
            )

        # Extract OpenAlex ID
        openalex_id = paper.id
        if openalex_id.startswith("https://openalex.org/"):
            openalex_id = openalex_id.split("/")[-1]

        # Search for citing works
        per_page = 200
        params = self._build_params(
            filter=f"cites:{openalex_id}",
            per_page=per_page,
            page=1 + (offset // per_page) if per_page > 0 else 1,
        )

        try:
            response = await self._get(f"{self.BASE_URL}/works", params=params)
            data = response.json()

            citing_papers = [self._parse_work(work) for work in data.get("results", [])]
            total = data.get("meta", {}).get("count", 0)

            # Fix pagination: slice to handle offset within page
            offset_within_page = offset % per_page
            citing_papers = citing_papers[offset_within_page:][:limit]

            return CitationResult(
                paper_id=paper_id,
                citation_count=paper.citation_count,
                citing_papers=citing_papers,
                has_more=offset + len(citing_papers) < total,
            )

        except Exception as e:
            logger.error(f"OpenAlex get_citations failed: {e}")
            return CitationResult(
                paper_id=paper_id,
                citation_count=paper.citation_count if paper else 0,
                citing_papers=[],
                has_more=False,
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
        # Check cache
        cache_key = self._search_cache.search_key("openalex_author", author_name, limit, offset)
        cached = self._search_cache.get(cache_key)
        if cached:
            return cast(SearchResult, cached)

        per_page = 200
        params = self._build_params(
            filter=f"raw_author_name.search:{quote_plus(author_name)}",
            per_page=per_page,
            page=1 + (offset // per_page) if per_page > 0 else 1,
            sort="publication_year:desc",
        )

        try:
            response = await self._get(f"{self.BASE_URL}/works", params=params)
            data = response.json()

            papers = [self._parse_work(work) for work in data.get("results", [])]
            total = data.get("meta", {}).get("count", 0)

            # Fix pagination: slice to handle offset within page
            offset_within_page = offset % per_page
            papers = papers[offset_within_page:][:limit]

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=offset + len(papers) < total,
                papers=papers,
                query=f"author:{author_name}",
                source=PaperSource.OPENALEX,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"OpenAlex author search failed: {e}")
            raise

    async def get_citation_network(
        self,
        paper_id: str,
        depth: int = 1,
        max_nodes: int = 50,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get citation network around a paper.

        Args:
            paper_id: Central paper ID
            depth: Network depth (1 or 2)
            max_nodes: Maximum nodes to include
            direction: 'citing', 'cited', or 'both'

        Returns:
            Dictionary with 'nodes' and 'edges' for network visualization
        """
        nodes: list[CitationNetworkNode] = []
        edges: list[CitationNetworkEdge] = []
        seen_ids: set[str] = set()

        # Get center paper
        center = await self.get_paper(paper_id)
        if not center:
            return {"nodes": [], "edges": [], "center_paper_id": paper_id}

        # Add center node
        nodes.append(
            CitationNetworkNode(
                paper_id=center.id,
                title=center.title,
                year=center.year,
                citation_count=center.citation_count,
            )
        )
        seen_ids.add(center.id)

        # Get citing papers (papers that cite this paper)
        if direction in ("citing", "both") and len(nodes) < max_nodes:
            citations = await self.get_citations(paper_id, limit=min(20, max_nodes - len(nodes)))
            for citing_paper in citations.citing_papers:
                if citing_paper.id not in seen_ids and len(nodes) < max_nodes:
                    nodes.append(
                        CitationNetworkNode(
                            paper_id=citing_paper.id,
                            title=citing_paper.title,
                            year=citing_paper.year,
                            citation_count=citing_paper.citation_count,
                        )
                    )
                    edges.append(
                        CitationNetworkEdge(
                            source=citing_paper.id,
                            target=center.id,
                        )
                    )
                    seen_ids.add(citing_paper.id)

        # Get references (papers cited by this paper) - requires additional API call
        if direction in ("cited", "both") and len(nodes) < max_nodes:
            # OpenAlex provides references in the work object
            try:
                params = self._build_params()
                if center.id.startswith("https://"):
                    work_id = center.id.split("/")[-1]
                else:
                    work_id = center.id
                response = await self._get(f"{self.BASE_URL}/works/{work_id}", params=params)
                work_data = response.json()

                # Get referenced works (up to limit)
                referenced_ids = work_data.get("referenced_works", [])[
                    : min(20, max_nodes - len(nodes))
                ]

                for ref_id in referenced_ids:
                    if ref_id not in seen_ids and len(nodes) < max_nodes:
                        ref_paper = await self.get_paper(ref_id.split("/")[-1])
                        if ref_paper:
                            nodes.append(
                                CitationNetworkNode(
                                    paper_id=ref_paper.id,
                                    title=ref_paper.title,
                                    year=ref_paper.year,
                                    citation_count=ref_paper.citation_count,
                                )
                            )
                            edges.append(
                                CitationNetworkEdge(
                                    source=center.id,
                                    target=ref_paper.id,
                                )
                            )
                            seen_ids.add(ref_paper.id)
            except Exception as e:
                logger.warning(f"Failed to get references for {paper_id}: {e}")

        return {
            "center_paper_id": center.id,
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges],
            "depth": depth,
        }

    async def get_bibtex(self, paper_id: str) -> str | None:
        """Get BibTeX entry for a paper.

        Generates BibTeX from paper metadata since OpenAlex doesn't provide
        native BibTeX export.

        Args:
            paper_id: OpenAlex ID, DOI, or other identifier

        Returns:
            BibTeX entry string or None if paper not found
        """
        # Check cache
        cache_key = self._bibtex_cache.bibtex_key(f"openalex:{paper_id}")
        cached = self._bibtex_cache.get(cache_key)
        if cached:
            return cast(str, cached)

        # Get paper metadata and generate BibTeX
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
