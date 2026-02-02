"""DBLP API client.

DBLP is the Computer Science Bibliography.
API Documentation: https://dblp.org/faq/How+to+use+the+dblp+search+API.html

Key feature: Native BibTeX export support!
"""

import logging
from typing import Any, cast

from ..cache import get_bibtex_cache
from ..models import Author, Paper, PaperSource, SearchResult
from .base import BaseClient

logger = logging.getLogger(__name__)


class DBLPClient(BaseClient):
    """Client for DBLP API.

    DBLP provides:
    - Computer science paper search
    - Native BibTeX export (unique feature!)
    - Author pages and venue information
    - No authentication required
    """

    BASE_URL = "https://dblp.org"
    SOURCE = PaperSource.DBLP

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize DBLP client."""
        super().__init__(timeout=timeout)
        self._bibtex_cache = get_bibtex_cache()

    def _parse_hit(self, hit: dict[str, Any]) -> Paper:
        """Parse DBLP hit object to Paper model."""
        info = hit.get("info", {})

        # Parse authors
        authors = []
        author_info = info.get("authors", {}).get("author", [])
        if isinstance(author_info, dict):
            author_info = [author_info]
        for author_data in author_info:
            if isinstance(author_data, str):
                authors.append(Author(name=author_data))
            elif isinstance(author_data, dict):
                # Handle cases where author data might be complex or just text
                name = author_data.get("text") or author_data.get("@text") or "Unknown"
                if isinstance(name, list):
                    name = name[0] if name else "Unknown"
                authors.append(
                    Author(
                        name=str(name),
                        author_id=author_data.get("@pid"),
                    )
                )

        # Extract year
        year = info.get("year")
        if year:
            try:
                year = int(year)
            except ValueError:
                year = None

        # Determine venue
        venue = info.get("venue")
        if isinstance(venue, list):
            venue = venue[0] if venue else None

        # Get DOI
        doi = info.get("doi")
        if doi and not isinstance(doi, str):  # Handle list or other types
            doi = None
        elif doi and not doi.startswith("10."):
            doi = None

        # Extract DBLP key for BibTeX retrieval
        # The key is usually in 'key' or '@id' or 'url'
        dblp_key = info.get("key") or hit.get("@id", "")
        # Remove base URL if present in key
        if dblp_key and dblp_key.startswith("https://dblp.org/rec/"):
            dblp_key = dblp_key.replace("https://dblp.org/rec/", "").replace(".html", "")

        return Paper(
            id=dblp_key,
            title=info.get("title", "Untitled"),
            authors=authors,
            year=year,
            venue=venue,
            volume=info.get("volume"),
            pages=info.get("pages"),
            doi=doi,
            url=info.get("url") or info.get("ee"),
            source=PaperSource.DBLP,
            bibtex_key=self._generate_bibtex_key_from_dblp(dblp_key),
        )

    def _generate_bibtex_key_from_dblp(self, dblp_key: str | None) -> str | None:
        """Generate a BibTeX key from DBLP key.

        DBLP keys are like: journals/nature/SmithJones2024
        We convert to: DBLP:SmithJones2024
        """
        if not dblp_key:
            return None
        if "/" in dblp_key:
            parts = dblp_key.split("/")
            return f"DBLP:{parts[-1]}"
        return f"DBLP:{dblp_key}"

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
        """Search for papers on DBLP.

        Args:
            query: Search query
            limit: Maximum results (max 1000)
            offset: First result to return
            sort: Sort order (ignored by DBLP)
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            venue: Filter by venue (conference/journal)

        Returns:
            SearchResult with matching papers
        """
        # Check cache
        cache_key = self._search_cache.search_key(
            "dblp",
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

        if sort and sort != "relevance":
            logger.debug(f"Sort option '{sort}' not supported by DBLP, ignoring")

        # Build query with filters
        search_query = query
        if year_from or year_to:
            year_filter = f"year:{year_from or '*'}:{year_to or '*'}"
            search_query = f"{query} {year_filter}"
        if venue:
            search_query = f"{query} venue:{venue}"

        params = {
            "q": search_query,
            "format": "json",
            "h": min(limit, 1000),  # Max 1000
            "f": offset,
        }

        try:
            response = await self._get(f"{self.BASE_URL}/search/publ/api", params=params)
            data = response.json()

            result_data = data.get("result", {})
            hits = result_data.get("hits", {})

            papers = []
            hit_list = hits.get("hit", [])
            if isinstance(hit_list, dict):
                hit_list = [hit_list]

            for hit in hit_list:
                try:
                    papers.append(self._parse_hit(hit))
                except Exception as e:
                    logger.warning(f"Failed to parse DBLP hit: {e}")
                    continue

            total = int(hits.get("@total", 0))

            result = SearchResult(
                total_results=total,
                returned_count=len(papers),
                offset=offset,
                has_more=offset + len(papers) < total,
                papers=papers,
                query=query,
                source=PaperSource.DBLP,
            )

            self._search_cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"DBLP search failed: {e}")
            raise

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get paper details by DBLP key.

        Args:
            paper_id: DBLP key (e.g., 'journals/nature/Smith2024')

        Returns:
            Paper details or None if not found
        """
        # Check cache
        cache_key = self._paper_cache.paper_key("dblp", paper_id)
        cached = self._paper_cache.get(cache_key)
        if cached:
            return cast(Paper, cached)

        # DBLP doesn't have a direct lookup by key for JSON metadata efficiently
        # But we can search for the key specifically using a structured query or exact match
        # DBLP key format: journals/nature/Smith2024

        # If it looks like a DBLP key, we can try to fetch the BibTeX first to confirm existence
        # or use the key in the search query directly if supported.

        # Current strategy: Use the last part (key) for search, but this is flaky for common names.
        # Better strategy: Search with the full key if possible or parse the key.

        try:
            result = await self.search(paper_id, limit=5)

            if result.papers:
                # Check if papers exist before access
                if hasattr(result.papers[0], "id") and result.papers[0].id:
                    dblp_key = result.papers[0].id

                    # Check for direct match if it was a key search
                    if "/" in paper_id and (paper_id in dblp_key or dblp_key in paper_id):
                        paper = result.papers[0]
                        self._paper_cache.set(cache_key, paper)
                        return paper

                    # If specific ID format but no exact match in title/etc
                    if "/" in paper_id:
                        # DBLP search is fuzzy, so we trust the first result if we searched for a key
                        paper = result.papers[0]
                        self._paper_cache.set(cache_key, paper)
                        return paper

            return None

        except Exception as e:
            logger.warning(f"DBLP get_paper failed for {paper_id}: {e}")
            return None

        except Exception as e:
            logger.warning(f"DBLP get_paper failed for {paper_id}: {e}")
            return None

    async def get_bibtex(self, paper_id: str) -> str | None:
        """Get native BibTeX entry from DBLP.

        This is DBLP's unique feature - direct BibTeX export!

        Args:
            paper_id: DBLP key or paper title to search

        Returns:
            BibTeX entry string or None if not found
        """
        # Check cache
        cache_key = self._bibtex_cache.bibtex_key(f"dblp:{paper_id}")
        cached = self._bibtex_cache.get(cache_key)
        if cached:
            return cast(str, cached)

        # If paper_id is a DBLP key, try direct BibTeX fetch
        if "/" in paper_id:
            try:
                # DBLP provides BibTeX at /{key}.bib
                # Key format: journals/nature/Smith2024 -> https://dblp.org/rec/journals/nature/Smith2024.bib
                url = f"{self.BASE_URL}/rec/{paper_id}.bib"
                response = await self._get(url)

                if response.status_code == 200:
                    bibtex = response.text.strip()
                    if bibtex and (bibtex.startswith("@") or "author =" in bibtex):
                        self._bibtex_cache.set(cache_key, bibtex)
                        return bibtex
            except Exception as e:
                # Log full traceback for debugging TypeError
                logger.debug(f"Direct BibTeX fetch failed for {paper_id}: {e}")

        # Search and get BibTeX for first match
        try:
            result = await self.search(paper_id, limit=1)
            if result.papers:
                # Use property access safely or check dict
                if hasattr(result.papers[0], "id") and result.papers[0].id:
                    dblp_key = result.papers[0].id
                    if dblp_key:
                        url = f"{self.BASE_URL}/rec/{dblp_key}.bib"
                        response = await self._get(url)

                        if response.status_code == 200:
                            bibtex = response.text.strip()
                            if bibtex and bibtex.startswith("@"):
                                self._bibtex_cache.set(cache_key, bibtex)
                                return bibtex
        except Exception as e:
            logger.warning(f"DBLP BibTeX search failed for {paper_id}: {e}")

        return None

    async def get_bibtex_batch(self, paper_ids: list[str]) -> dict[str, str | None]:
        """Get BibTeX entries for multiple papers.

        Args:
            paper_ids: List of DBLP keys or search terms

        Returns:
            Dictionary mapping paper_id to BibTeX entry (or None if not found)
        """
        results = {}
        for paper_id in paper_ids:
            results[paper_id] = await self.get_bibtex(paper_id)
        return results

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for papers by author on DBLP.

        Args:
            author_name: Author name to search
            limit: Maximum results
            offset: Pagination offset

        Returns:
            SearchResult with author's papers
        """
        # DBLP uses author:name syntax
        return await self.search(
            query=f"author:{author_name}",
            limit=limit,
            offset=offset,
        )
