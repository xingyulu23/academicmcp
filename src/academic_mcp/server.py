"""Academic MCP Server.

MCP server for academic paper search, analysis, and BibTeX retrieval.
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .aggregator import AcademicAggregator
from .cache import get_all_cache_stats
from .models import Paper, SearchResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global aggregator instance
_aggregator: AcademicAggregator | None = None


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[None]:
    """Manage server lifecycle - initialize and cleanup resources.

    This context manager:
    - Initializes the global aggregator on startup
    - Closes all httpx clients on shutdown to prevent connection leaks
    """
    global _aggregator
    _aggregator = AcademicAggregator(
        email=os.environ.get("ACADEMIC_MCP_EMAIL"),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
    )
    logger.info("Academic MCP Server initialized")
    try:
        yield
    finally:
        if _aggregator is not None:
            await _aggregator.close()
            _aggregator = None
            logger.info("Academic MCP Server shutdown complete")


# Initialize MCP server with lifespan for proper resource management
mcp = FastMCP("academic_mcp", lifespan=lifespan)


def get_aggregator() -> AcademicAggregator:
    global _aggregator
    if _aggregator is None:
        raise RuntimeError("Aggregator not initialized. Server lifespan not started.")
    return _aggregator


def _format_api_error(e: Exception) -> str:
    """Format API error for user display."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 404:
            return "Resource not found. Please check the ID is correct."
        elif status == 403:
            return "Access denied. This resource may require authentication."
        elif status == 429:
            return "Rate limit exceeded. Please wait before making more requests."
        elif status >= 500:
            return f"Server error ({status}). The API may be temporarily unavailable."
        return f"HTTP error {status}: {e.response.text[:200]}"
    elif isinstance(e, httpx.TimeoutException):
        return "Request timed out. Please try again."
    elif isinstance(e, httpx.ConnectError):
        return "Connection failed. Please check your network."
    return f"Unexpected error: {type(e).__name__}: {str(e)[:200]}"


def format_paper_markdown(paper: Paper, index: int | None = None) -> str:
    """Format a paper as markdown."""
    prefix = f"{index}. " if index else ""
    lines = [f"{prefix}**{paper.title}**"]

    if paper.authors:
        author_names = ", ".join(a.name for a in paper.authors[:5])
        if len(paper.authors) > 5:
            author_names += f" et al. ({len(paper.authors)} authors)"
        lines.append(f"   *Authors*: {author_names}")

    if paper.year:
        lines.append(f"   *Year*: {paper.year}")

    if paper.venue:
        lines.append(f"   *Venue*: {paper.venue}")

    if paper.citation_count:
        lines.append(f"   *Citations*: {paper.citation_count}")

    if paper.doi:
        lines.append(f"   *DOI*: {paper.doi}")
    elif paper.arxiv_id:
        lines.append(f"   *arXiv*: {paper.arxiv_id}")

    if paper.abstract:
        abstract = paper.abstract[:300] + "..." if len(paper.abstract) > 300 else paper.abstract
        lines.append(f"   *Abstract*: {abstract}")

    lines.append(f"   *ID*: `{paper.id}`")

    return "\n".join(lines)


# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool(
    name="academic_search_papers",
    annotations=ToolAnnotations(
        title="Search Academic Papers",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_search_papers(
    query: str = Field(..., description="Search query (keywords, title, etc.)"),
    title: str | None = Field(default=None, description="Filter by paper title"),
    author: str | None = Field(default=None, description="Filter by author name"),
    doi: str | None = Field(default=None, description="Search by exact DOI"),
    year_from: int | None = Field(default=None, description="Filter papers from this year"),
    year_to: int | None = Field(default=None, description="Filter papers until this year"),
    venue: str | None = Field(default=None, description="Filter by journal/conference"),
    sort: Literal["relevance", "publication_date", "citation_count"] = Field(
        default="relevance",
        description="Sort order: relevance, publication_date, or citation_count",
    ),
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
    response_format: Literal["markdown", "json"] = Field(
        default="markdown", description="Output format: markdown or json"
    ),
) -> str:
    """Search for academic papers across multiple databases.

    Searches OpenAlex (primary), with fallback to DBLP and Semantic Scholar.

    **Search Tips:**
    - Use specific keywords for better results
    - Combine with author/year/venue filters for precision
    - Use DOI for exact paper lookup
    - Use `sort` to order by date or citations (default: relevance)

    **Examples:**
    - `query="attention is all you need"` - Find the Transformer paper
    - `query="machine learning", author="Hinton"` - Papers by Geoffrey Hinton
    - `query="neural networks", year_from=2020, year_to=2024` - Recent papers
    - `query="LLM", sort="publication_date"` - Newest LLM papers
    - `query="deep learning", sort="citation_count"` - Most cited deep learning papers

    Returns:
        Formatted search results with paper titles, authors, years, and IDs.
    """
    try:
        aggregator = get_aggregator()

        # Handle DOI as direct lookup
        if doi:
            paper = await aggregator.get_paper(doi)
            if paper:
                if response_format == "json":
                    return json.dumps(paper.model_dump(), indent=2, default=str)
                return format_paper_markdown(paper)
            return f"No paper found for DOI: {doi}"

        # Build effective query
        effective_query = query
        if title:
            effective_query = f"title:{title} {query}".strip()

        if author:
            effective_query = f"author:{author} {effective_query}".strip()

        result = await aggregator.search(
            query=effective_query,
            limit=limit,
            offset=offset,
            year_from=year_from,
            year_to=year_to,
            venue=venue,
            sort=sort,
        )

        if response_format == "json":
            return json.dumps(result.model_dump(), indent=2, default=str)

        # Format as markdown
        lines = [f"# Search Results for: {query}", ""]
        lines.append(f"Found **{result.total_results}** papers (showing {result.returned_count})")
        lines.append(f"Source: {result.source.value}")
        if sort and sort != "relevance":
            lines.append(f"Sorted by: {sort}")
        lines.append("")

        for i, paper in enumerate(result.papers, 1 + offset):
            lines.append(format_paper_markdown(paper, i))
            lines.append("")

        if result.has_more:
            lines.append(
                f"*More results available. Use `offset={offset + limit}` to see next page.*"
            )

        return "\n".join(lines)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_search_papers: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_search_papers: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_get_paper_details",
    annotations=ToolAnnotations(
        title="Get Paper Details",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_get_paper_details(
    paper_id: str = Field(..., description="Paper ID (OpenAlex ID, DOI, arXiv ID, or DBLP key)"),
    response_format: Literal["markdown", "json"] = Field(
        default="markdown", description="Output format: markdown or json"
    ),
) -> str:
    """Get detailed metadata for a specific paper.

    Supports multiple ID formats:
    - DOI: `10.1038/nature12345`
    - arXiv: `2401.12345` or `arxiv:2401.12345`
    - OpenAlex: `W2741809807`
    - DBLP: `journals/nature/Smith2024`

    Returns:
        Complete paper metadata including title, authors, abstract, venue, citations.
    """
    try:
        aggregator = get_aggregator()

        paper = await aggregator.get_paper(paper_id)
        if not paper:
            return f"Paper not found: {paper_id}"

        if response_format == "json":
            return json.dumps(paper.model_dump(), indent=2, default=str)

        # Format as markdown
        lines = [f"# {paper.title}", ""]

        if paper.authors:
            lines.append("## Authors")
            for author in paper.authors:
                affiliation = f" ({author.affiliation})" if author.affiliation else ""
                lines.append(f"- {author.name}{affiliation}")
            lines.append("")

        lines.append("## Publication Info")
        if paper.year:
            lines.append(f"- **Year**: {paper.year}")
        if paper.venue:
            lines.append(f"- **Venue**: {paper.venue}")
        if paper.volume:
            lines.append(f"- **Volume**: {paper.volume}")
        if paper.issue:
            lines.append(f"- **Issue**: {paper.issue}")
        if paper.pages:
            lines.append(f"- **Pages**: {paper.pages}")
        lines.append(f"- **Citations**: {paper.citation_count}")
        lines.append("")

        lines.append("## Identifiers")
        if paper.doi:
            lines.append(f"- **DOI**: [{paper.doi}](https://doi.org/{paper.doi})")
        if paper.arxiv_id:
            lines.append(f"- **arXiv**: [{paper.arxiv_id}](https://arxiv.org/abs/{paper.arxiv_id})")
        lines.append(f"- **ID**: `{paper.id}`")
        if paper.url:
            lines.append(f"- **URL**: {paper.url}")
        if paper.pdf_url:
            lines.append(f"- **PDF**: {paper.pdf_url}")
        lines.append("")

        if paper.abstract:
            lines.append("## Abstract")
            lines.append(paper.abstract)
            lines.append("")

        return "\n".join(lines)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_get_paper_details: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_get_paper_details: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_get_bibtex",
    annotations=ToolAnnotations(
        title="Get BibTeX Citation",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_get_bibtex(
    paper_ids: str = Field(..., description="Paper ID(s), comma-separated for batch export"),
    use_dblp: bool = Field(default=True, description="Try DBLP for native BibTeX first"),
) -> str:
    """Export BibTeX citations for papers.

    Supports single paper or batch export:
    - Single: `paper_ids="10.1038/nature12345"`
    - Batch: `paper_ids="10.1038/nature12345,2401.12345,W2741809807"`

    BibTeX sources:
    - DBLP: Native BibTeX export (highest quality for CS papers)
    - Generated: Created from paper metadata if DBLP unavailable

    Returns:
        Valid BibTeX entries ready for use in LaTeX/bibliography managers.
    """
    try:
        aggregator = get_aggregator()

        # Parse paper IDs
        ids = [pid.strip() for pid in paper_ids.split(",") if pid.strip()]

        if not ids:
            return "Error: No paper IDs provided"

        if len(ids) == 1:
            # Single paper
            bibtex = await aggregator.get_bibtex(ids[0], use_dblp=use_dblp)
            if bibtex:
                return f"```bibtex\n{bibtex}\n```"
            return f"Could not generate BibTeX for: {ids[0]}"

        # Batch export
        results = await aggregator.get_bibtex_batch(ids, use_dblp=use_dblp)

        entries = []
        failed = []
        for paper_id, bibtex in results.items():
            if bibtex:
                entries.append(bibtex)
            else:
                failed.append(paper_id)

        output = []
        if entries:
            output.append("```bibtex")
            output.append("\n\n".join(entries))
            output.append("```")

        if failed:
            output.append(f"\n*Failed to generate BibTeX for: {', '.join(failed)}*")

        output.append(f"\n*Generated {len(entries)} BibTeX entries*")

        return "\n".join(output)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_get_bibtex: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_get_bibtex: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_get_citations",
    annotations=ToolAnnotations(
        title="Get Paper Citations",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_get_citations(
    paper_id: str = Field(..., description="Paper ID to get citations for"),
    limit: int = Field(default=20, ge=1, le=100, description="Maximum citing papers to return"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
    response_format: Literal["markdown", "json"] = Field(
        default="markdown", description="Output format: markdown or json"
    ),
) -> str:
    """Get papers that cite a given paper.

    Returns citation count and list of citing papers with metadata.
    Uses OpenAlex for comprehensive citation data.

    Returns:
        Citation count and list of citing papers.
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_citations(paper_id, limit=limit, offset=offset)

        if response_format == "json":
            return json.dumps(result.model_dump(), indent=2, default=str)

        lines = [f"# Citations for: {paper_id}", ""]
        lines.append(f"**Total Citations**: {result.citation_count}")
        lines.append(f"**Showing**: {len(result.citing_papers)} citing papers")
        lines.append("")

        if result.citing_papers:
            lines.append("## Citing Papers")
            for i, paper in enumerate(result.citing_papers, 1 + offset):
                lines.append(format_paper_markdown(paper, i))
                lines.append("")
        else:
            lines.append("*No citing papers found or citation data unavailable.*")

        if result.has_more:
            lines.append(
                f"*More citations available. Use `offset={offset + limit}` for next page.*"
            )

        return "\n".join(lines)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_get_citations: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_get_citations: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_search_author",
    annotations=ToolAnnotations(
        title="Search Papers by Author",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_search_author(
    author_name: str = Field(..., description="Author name to search"),
    limit: int = Field(default=20, ge=1, le=100, description="Maximum papers to return"),
    offset: int = Field(default=0, ge=0, description="Pagination offset"),
    year_from: int | None = Field(default=None, description="Filter papers from this year"),
    year_to: int | None = Field(default=None, description="Filter papers until this year"),
    response_format: Literal["markdown", "json"] = Field(
        default="markdown", description="Output format: markdown or json"
    ),
) -> str:
    """Search for papers by a specific author.

    Finds all papers by the given author name across databases.

    **Examples:**
    - `author_name="Geoffrey Hinton"` - All papers by Hinton
    - `author_name="Yann LeCun", year_from=2020` - Recent LeCun papers

    Returns:
        List of papers by the author with metadata.
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.search_by_author(author_name, limit=limit, offset=offset)

        # Apply year filter if specified - create copy to avoid cache mutation
        if year_from or year_to:
            filtered_papers = [
                paper
                for paper in result.papers
                if not (year_from and paper.year and paper.year < year_from)
                and not (year_to and paper.year and paper.year > year_to)
            ]
            # Create new SearchResult to avoid mutating cached object
            result = SearchResult(
                total_results=result.total_results,
                returned_count=len(filtered_papers),
                offset=result.offset,
                has_more=result.has_more,
                papers=filtered_papers,
                query=result.query,
                source=result.source,
            )

        if response_format == "json":
            return json.dumps(result.model_dump(), indent=2, default=str)

        lines = [f"# Papers by: {author_name}", ""]
        lines.append(f"Found **{result.total_results}** papers (showing {result.returned_count})")
        lines.append("")

        for i, paper in enumerate(result.papers, 1 + offset):
            lines.append(format_paper_markdown(paper, i))
            lines.append("")

        if result.has_more:
            lines.append(f"*More papers available. Use `offset={offset + limit}` for next page.*")

        return "\n".join(lines)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_search_author: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_search_author: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_get_related_papers",
    annotations=ToolAnnotations(
        title="Get Related Papers",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_get_related_papers(
    paper_id: str = Field(..., description="Paper ID to find related papers for"),
    limit: int = Field(default=10, ge=1, le=50, description="Maximum recommendations"),
    response_format: Literal["markdown", "json"] = Field(
        default="markdown", description="Output format: markdown or json"
    ),
) -> str:
    """Get AI-powered related paper recommendations.

    Uses Semantic Scholar's recommendation engine to find papers similar
    to the given paper based on content and citation relationships.

    **Great for:**
    - Literature review expansion
    - Finding follow-up work
    - Discovering related research areas

    Returns:
        List of recommended related papers.
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_related_papers(paper_id, limit=limit)

        if response_format == "json":
            return json.dumps(result.model_dump(), indent=2, default=str)

        lines = [f"# Related Papers for: {paper_id}", ""]
        lines.append(f"Source: {result.recommendation_source}")
        lines.append(f"Found **{len(result.related_papers)}** related papers")
        lines.append("")

        if result.related_papers:
            for i, paper in enumerate(result.related_papers, 1):
                lines.append(format_paper_markdown(paper, i))
                lines.append("")
        else:
            lines.append("*No related papers found. Try a different paper ID.*")

        return "\n".join(lines)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_get_related_papers: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_get_related_papers: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_get_citation_network",
    annotations=ToolAnnotations(
        title="Get Citation Network",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def academic_get_citation_network(
    paper_id: str = Field(..., description="Central paper ID"),
    depth: int = Field(
        default=1, ge=1, le=1, description="Network depth (currently only 1 supported)"
    ),
    max_nodes: int = Field(default=50, ge=10, le=200, description="Maximum nodes"),
    direction: Literal["citing", "cited", "both"] = Field(
        default="both", description="Direction: citing, cited, or both"
    ),
) -> str:
    """Get citation network data for visualization.

    Returns a graph structure with:
    - **Nodes**: Papers with title, year, and citation count
    - **Edges**: Citation relationships (source cites target)

    **Directions:**
    - `citing`: Papers that cite this paper
    - `cited`: Papers this paper cites (references)
    - `both`: Both directions

    **Output Format:** JSON for use with graph visualization tools.

    Returns:
        JSON with nodes and edges for citation network visualization.
    """
    try:
        aggregator = get_aggregator()

        network = await aggregator.get_citation_network(
            paper_id, depth=depth, max_nodes=max_nodes, direction=direction
        )

        # Always return JSON for network data (best for visualization)
        output = {
            "center_paper_id": network.get("center_paper_id"),
            "depth": network.get("depth"),
            "node_count": len(network.get("nodes", [])),
            "edge_count": len(network.get("edges", [])),
            "nodes": network.get("nodes", []),
            "edges": network.get("edges", []),
        }

        return json.dumps(output, indent=2)
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"API error in academic_get_citation_network: {e}")
        return f"**Error**: {_format_api_error(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in academic_get_citation_network: {e}")
        return "**Error**: An unexpected error occurred. Please try again."


@mcp.tool(
    name="academic_cache_stats",
    annotations=ToolAnnotations(
        title="Get Cache Statistics",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def academic_cache_stats() -> str:
    """Get cache statistics for debugging.

    Returns hit rates and sizes for search, paper, and BibTeX caches.
    """
    stats = get_all_cache_stats()
    return json.dumps(stats, indent=2)


def main() -> None:
    """Run the MCP server."""
    logger.info("Starting Academic MCP Server...")
    mcp.run()


if __name__ == "__main__":
    main()
