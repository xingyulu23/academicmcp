"""Multi-source aggregator for academic paper search.

Combines results from multiple APIs with fallback logic.
"""

import asyncio
import logging
from typing import Any, cast

from .bibtex import generate_bibtex
from .cache import get_bibtex_cache
from .clients.arxiv_client import ArxivClient
from .clients.base import BaseClient
from .clients.crossref import CrossRefClient
from .clients.dblp import DBLPClient
from .clients.openalex import OpenAlexClient
from .clients.semantic import SemanticScholarClient
from .models import (
    CitationResult,
    Paper,
    PaperSource,
    RelatedPapersResult,
    SearchResult,
)

logger = logging.getLogger(__name__)


class AcademicAggregator:
    """Aggregates results from multiple academic APIs.

    Priority order:
    1. OpenAlex - Primary (best coverage, free tier)
    2. DBLP - For CS papers and native BibTeX
    3. Semantic Scholar - For recommendations
    4. arXiv - For preprints
    5. CrossRef - For DOI resolution
    """

    def __init__(
        self,
        email: str | None = None,
        semantic_scholar_api_key: str | None = None,
    ) -> None:
        """Initialize aggregator with all clients.

        Args:
            email: Email for polite access to OpenAlex and CrossRef
            semantic_scholar_api_key: API key for Semantic Scholar
        """
        self.openalex = OpenAlexClient(email=email)
        self.dblp = DBLPClient()
        self.semantic = SemanticScholarClient(api_key=semantic_scholar_api_key)
        self.arxiv = ArxivClient()
        self.crossref = CrossRefClient(email=email)

        self._bibtex_cache = get_bibtex_cache()

    async def close(self) -> None:
        """Close all client connections."""
        await asyncio.gather(
            self.openalex.close(),
            self.dblp.close(),
            self.semantic.close(),
            self.arxiv.close(),
            self.crossref.close(),
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        source: PaperSource | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        venue: str | None = None,
        sort: str | None = None,
        **kwargs: Any,
    ) -> SearchResult:
        """Search for papers across sources.

        Args:
            query: Search query
            limit: Maximum results
            offset: Pagination offset
            source: Preferred source (defaults to OpenAlex)
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            venue: Filter by venue
            sort: Sort order (relevance, publication_date, citation_count)

        Returns:
            SearchResult from the selected source
        """
        search_kwargs = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "year_from": year_from,
            "year_to": year_to,
            "venue": venue,
            "sort": sort,
        }

        # Select client based on source
        if source == PaperSource.DBLP:
            return await self.dblp.search(
                query,
                limit,
                offset,
                year_from=year_from,
                year_to=year_to,
                venue=venue,
                sort=sort,
            )
        elif source == PaperSource.SEMANTIC_SCHOLAR:
            return await self.semantic.search(
                query,
                limit,
                offset,
                year_from=year_from,
                year_to=year_to,
                venue=venue,
                sort=sort,
            )
        elif source == PaperSource.ARXIV:
            return await self.arxiv.search(
                query,
                limit,
                offset,
                year_from=year_from,
                year_to=year_to,
                venue=venue,
                sort=sort,
            )
        elif source == PaperSource.CROSSREF:
            return await self.crossref.search(
                query,
                limit,
                offset,
                year_from=year_from,
                year_to=year_to,
                venue=venue,
                sort=sort,
            )
        else:
            # Default to OpenAlex with fallback
            try:
                return await self.openalex.search(
                    query,
                    limit,
                    offset,
                    year_from=year_from,
                    year_to=year_to,
                    venue=venue,
                    sort=sort,
                )
            except Exception as e:
                logger.warning(f"OpenAlex search failed, trying DBLP: {e}")
                try:
                    return await self.dblp.search(
                        query,
                        limit,
                        offset,
                        year_from=year_from,
                        year_to=year_to,
                        venue=venue,
                        sort=sort,
                    )
                except Exception as e2:
                    logger.warning(f"DBLP search failed, trying Semantic Scholar: {e2}")
                    return await self.semantic.search(
                        query,
                        limit,
                        offset,
                        year_from=year_from,
                        year_to=year_to,
                        venue=venue,
                        sort=sort,
                    )

    async def get_paper(
        self,
        paper_id: str,
        source: PaperSource | None = None,
    ) -> Paper | None:
        """Get paper details by ID.

        Auto-detects source based on ID format:
        - DOI (10.xxx) -> OpenAlex/CrossRef
        - arXiv ID -> arXiv
        - DBLP key (contains /) -> DBLP
        - Semantic Scholar ID -> Semantic Scholar

        Args:
            paper_id: Paper identifier
            source: Preferred source

        Returns:
            Paper details or None if not found
        """
        # Auto-detect source from ID format
        if source is None:
            source = self._detect_source(paper_id)

        clients_to_try: list[tuple[PaperSource, BaseClient]] = []

        if source == PaperSource.DBLP:
            clients_to_try = [
                (PaperSource.DBLP, self.dblp),
                (PaperSource.OPENALEX, self.openalex),
            ]
        elif source == PaperSource.ARXIV:
            clients_to_try = [
                (PaperSource.ARXIV, self.arxiv),
                (PaperSource.OPENALEX, self.openalex),
            ]
        elif source == PaperSource.SEMANTIC_SCHOLAR:
            clients_to_try = [
                (PaperSource.SEMANTIC_SCHOLAR, self.semantic),
                (PaperSource.OPENALEX, self.openalex),
            ]
        elif source == PaperSource.CROSSREF:
            clients_to_try = [
                (PaperSource.CROSSREF, self.crossref),
                (PaperSource.OPENALEX, self.openalex),
            ]
        else:
            # Default to OpenAlex
            clients_to_try = [
                (PaperSource.OPENALEX, self.openalex),
                (PaperSource.CROSSREF, self.crossref),
                (PaperSource.SEMANTIC_SCHOLAR, self.semantic),
            ]

        for _, client in clients_to_try:
            try:
                paper = await client.get_paper(paper_id)
                if paper:
                    return paper
            except Exception as e:
                logger.debug(f"Client failed for {paper_id}: {e}")
                continue

        return None

    def _detect_source(self, paper_id: str) -> PaperSource:
        """Detect source from paper ID format."""
        paper_id_lower = paper_id.lower()

        if paper_id.startswith("10.") or "doi.org" in paper_id_lower:
            return PaperSource.OPENALEX  # DOI -> OpenAlex (best metadata)
        elif paper_id_lower.startswith("arxiv:") or self._looks_like_arxiv(paper_id):
            return PaperSource.ARXIV
        elif "/" in paper_id and not paper_id.startswith("http"):
            return PaperSource.DBLP
        elif len(paper_id) == 40 and paper_id.isalnum():
            return PaperSource.SEMANTIC_SCHOLAR  # S2 paper IDs are 40 chars
        else:
            return PaperSource.OPENALEX

    def _looks_like_arxiv(self, paper_id: str) -> bool:
        """Check if ID looks like an arXiv ID."""
        import re

        # Old format: hep-th/9901001
        # New format: 2401.12345
        old_pattern = r"^[a-z-]+/\d+$"
        new_pattern = r"^\d{4}\.\d{4,5}$"
        return bool(re.match(old_pattern, paper_id) or re.match(new_pattern, paper_id))

    async def get_bibtex(
        self,
        paper_id: str,
        use_dblp: bool = True,
    ) -> str | None:
        """Get BibTeX for a paper.

        Priority:
        1. DBLP native BibTeX (if use_dblp=True)
        2. Generate from paper metadata

        Args:
            paper_id: Paper identifier
            use_dblp: Try DBLP for native BibTeX first

        Returns:
            BibTeX entry string or None
        """
        # Check cache
        cache_key = self._bibtex_cache.bibtex_key(paper_id)
        cached = self._bibtex_cache.get(cache_key)
        if cached:
            return cast(str, cached)

        # Try DBLP for native BibTeX
        if use_dblp:
            try:
                bibtex = await self.dblp.get_bibtex(paper_id)
                if bibtex:
                    self._bibtex_cache.set(cache_key, bibtex)
                    return bibtex
            except Exception as e:
                logger.debug(f"DBLP BibTeX failed for {paper_id}: {e}")

        # Fall back to generating from metadata
        paper = await self.get_paper(paper_id)
        if paper:
            bibtex = generate_bibtex(paper)
            self._bibtex_cache.set(cache_key, bibtex)
            return bibtex

        return None

    async def get_bibtex_batch(
        self,
        paper_ids: list[str],
        use_dblp: bool = True,
    ) -> dict[str, str | None]:
        """Get BibTeX for multiple papers.

        Args:
            paper_ids: List of paper identifiers
            use_dblp: Try DBLP for native BibTeX first

        Returns:
            Dictionary mapping paper_id to BibTeX entry
        """
        results: dict[str, str | None] = {}

        # Process in parallel
        tasks = [self.get_bibtex(paper_id, use_dblp=use_dblp) for paper_id in paper_ids]
        bibtex_results = await asyncio.gather(*tasks, return_exceptions=True)

        for paper_id, result in zip(paper_ids, bibtex_results, strict=True):
            if isinstance(result, Exception):
                logger.warning(f"BibTeX failed for {paper_id}: {result}")
                results[paper_id] = None
            else:
                results[paper_id] = cast(str, result) if result is not None else None

        return results

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> CitationResult:
        """Get papers that cite this paper.

        Uses OpenAlex as primary source for citations.

        Args:
            paper_id: Paper identifier
            limit: Maximum citing papers
            offset: Pagination offset

        Returns:
            CitationResult with citing papers
        """
        # Try OpenAlex first (best citation data)
        try:
            return await self.openalex.get_citations(paper_id, limit, offset)
        except Exception as e:
            logger.warning(f"OpenAlex citations failed: {e}")

        # Return empty result if OpenAlex fails
        paper = await self.get_paper(paper_id)
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
        source: PaperSource | None = None,
    ) -> SearchResult:
        """Search for papers by author.

        Args:
            author_name: Author name
            limit: Maximum results
            offset: Pagination offset
            source: Preferred source

        Returns:
            SearchResult with author's papers
        """
        if source == PaperSource.DBLP:
            return await self.dblp.search_by_author(author_name, limit, offset)
        elif source == PaperSource.SEMANTIC_SCHOLAR:
            return await self.semantic.search_by_author(author_name, limit, offset)
        elif source == PaperSource.ARXIV:
            return await self.arxiv.search_by_author(author_name, limit, offset)
        elif source == PaperSource.CROSSREF:
            return await self.crossref.search_by_author(author_name, limit, offset)
        else:
            # Default to OpenAlex
            try:
                return await self.openalex.search_by_author(author_name, limit, offset)
            except Exception as e:
                logger.warning(f"OpenAlex author search failed: {e}")
                return await self.semantic.search_by_author(author_name, limit, offset)

    async def get_related_papers(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> RelatedPapersResult:
        """Get related paper recommendations.

        Uses Semantic Scholar's AI-powered recommendations.

        Args:
            paper_id: Paper identifier
            limit: Maximum recommendations

        Returns:
            RelatedPapersResult with recommended papers
        """
        return await self.semantic.get_related_papers(paper_id, limit)

    async def get_citation_network(
        self,
        paper_id: str,
        depth: int = 1,
        max_nodes: int = 50,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get citation network around a paper.

        Uses OpenAlex for citation network data.

        Args:
            paper_id: Central paper ID
            depth: Network depth (1 or 2)
            max_nodes: Maximum nodes
            direction: 'citing', 'cited', or 'both'

        Returns:
            Network data with nodes and edges
        """
        return await self.openalex.get_citation_network(paper_id, depth, max_nodes, direction)
