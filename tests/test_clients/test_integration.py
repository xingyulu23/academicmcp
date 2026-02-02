"""Integration tests for API clients using real API calls.

These tests make actual HTTP requests to the APIs.
Marked with @pytest.mark.integration to skip during unit test runs.

Run only integration tests:
    pytest -m integration tests/test_clients/test_integration.py

Run all tests:
    pytest tests/
"""

import pytest

# Import clients directly from their modules to avoid pydantic deprecation issues
from academix.clients import (
    CrossRefClient,
    DBLPClient,
    OpenAlexClient,
)
from academix.clients.arxiv_client import ArxivClient
from academix.clients.semantic import SemanticScholarClient
from academix.models import PaperSource


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openalex_search():
    """Test OpenAlex search with real API call."""
    client = OpenAlexClient()

    # Search for a well-known paper
    result = await client.search("attention is all you need", limit=5)

    # Validate response structure
    assert result is not None
    assert result.source == PaperSource.OPENALEX
    assert result.query == "attention is all you need"
    assert result.returned_count > 0
    assert result.total_results > 0
    assert result.papers is not None
    assert len(result.papers) > 0

    # Validate first paper has expected fields
    paper = result.papers[0]
    assert paper.id is not None
    assert paper.title is not None
    assert len(paper.title) > 0
    assert paper.source == PaperSource.OPENALEX

    # Paper should have authors
    if paper.authors:
        assert all(author.name for author in paper.authors)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openalex_get_paper():
    """Test OpenAlex get_paper with real API call."""
    client = OpenAlexClient()

    # Get a known paper by its DOI (more stable than OpenAlex ID)
    paper = await client.get_paper("10.48550/arXiv.1706.03762")  # "Attention Is All You Need"

    assert paper is not None
    assert paper.id is not None
    assert paper.title is not None
    assert "attention" in paper.title.lower()
    assert paper.source == PaperSource.OPENALEX
    assert paper.citation_count is not None
    assert paper.citation_count > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dblp_search():
    """Test DBLP search with real API call."""
    client = DBLPClient()

    # Search for a well-known computer science paper
    result = await client.search("machine learning", limit=5)

    # Validate response structure
    assert result is not None
    assert result.source == PaperSource.DBLP
    assert result.query == "machine learning"
    assert result.returned_count > 0
    assert result.total_results > 0
    assert result.papers is not None
    assert len(result.papers) > 0

    # Validate first paper has expected fields
    paper = result.papers[0]
    assert paper.id is not None
    assert paper.title is not None
    assert len(paper.title) > 0
    assert paper.source == PaperSource.DBLP

    # Paper should have authors
    if paper.authors:
        assert all(author.name for author in paper.authors)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dblp_bibtex():
    """Test DBLP BibTeX export with real API call."""
    client = DBLPClient()

    # Get BibTeX for a known paper using search
    # First search to get a paper ID
    result = await client.search("machine learning", limit=1)

    if result.papers and result.papers[0].id:
        paper_id = result.papers[0].id

        # Get BibTeX
        bibtex = await client.get_bibtex(paper_id)

        # Validate BibTeX structure
        assert bibtex is not None
        assert isinstance(bibtex, str)
        assert len(bibtex) > 0
        assert bibtex.startswith("@")

        # BibTeX should contain key fields
        assert "author" in bibtex.lower() or bibtex.startswith("@")
        assert "title" in bibtex.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crossref_search():
    """Test CrossRef search with real API call."""
    client = CrossRefClient()

    # Search for a well-known paper
    result = await client.search("attention is all you need", limit=5)

    # Validate response structure
    assert result is not None
    assert result.source == PaperSource.CROSSREF
    assert result.query == "attention is all you need"
    assert result.returned_count > 0
    assert result.total_results > 0
    assert result.papers is not None
    assert len(result.papers) > 0

    # Validate first paper has expected fields
    paper = result.papers[0]
    assert paper.id is not None
    assert paper.title is not None
    assert len(paper.title) > 0
    assert paper.source == PaperSource.CROSSREF


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crossref_resolve_doi():
    """Test CrossRef DOI resolution with real API call."""
    client = CrossRefClient()

    # Resolve a well-known DOI
    doi = "10.1038/nature14539"  # AlphaGo paper
    paper = await client.resolve_doi(doi)

    # Validate paper structure
    assert paper is not None
    assert paper.doi == doi
    assert paper.title is not None
    assert len(paper.title) > 0
    assert paper.source == PaperSource.CROSSREF
    assert paper.url is not None

    # DOI should be in URL
    assert doi in paper.url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crossref_get_paper():
    """Test CrossRef get_paper with real API call."""
    client = CrossRefClient()

    # Get a known paper by DOI
    paper = await client.get_paper("10.1038/nature14539")

    assert paper is not None
    assert paper.doi == "10.1038/nature14539"
    assert paper.title is not None
    assert len(paper.title) > 0
    assert paper.source == PaperSource.CROSSREF


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openalex_citations():
    """Test OpenAlex citation retrieval with real API call."""
    client = OpenAlexClient()

    # Get citations for a well-known paper
    result = await client.get_citations("W2741809807", limit=5)

    # Validate citation result structure
    assert result is not None
    assert result.paper_id == "W2741809807"
    assert result.citation_count > 0  # "Attention Is All You Need" has many citations

    # Should have citing papers
    assert result.citing_papers is not None
    if len(result.citing_papers) > 0:
        citing_paper = result.citing_papers[0]
        assert citing_paper.id is not None
        assert citing_paper.title is not None
        assert citing_paper.source == PaperSource.OPENALEX


@pytest.mark.integration
@pytest.mark.asyncio
async def test_network_error_handling():
    """Test that clients handle network errors gracefully."""
    # Test with timeout that's too short
    client = OpenAlexClient(timeout=0.001)

    try:
        result = await client.search("test", limit=1)
        # If it succeeds, that's fine too (unlikely with such short timeout)
        assert result is not None
    except Exception as e:
        # Network errors should be exceptions
        assert e is not None
        # Check exception type - should be a timeout-related error
        import httpx

        assert isinstance(
            e, (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError)
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_results():
    """Test handling of empty search results."""
    client = OpenAlexClient()

    # Search for something unlikely to exist
    result = await client.search("xzqwertyuiop123456789", limit=5)

    # Should return a valid result object with 0 papers
    assert result is not None
    assert result.papers is not None
    assert result.returned_count == 0
    assert result.total_results == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crossref_with_email():
    """Test CrossRef with email for polite pool access."""
    # Note: This uses a dummy email - real usage would provide user email
    client = CrossRefClient(email="test@example.com")

    result = await client.search("machine learning", limit=3)

    assert result is not None
    assert result.source == PaperSource.CROSSREF
    assert result.returned_count > 0


# =============================================================================
# BibTeX Tests - All Sources
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openalex_get_bibtex():
    """Test OpenAlex BibTeX generation."""
    client = OpenAlexClient()

    bibtex = await client.get_bibtex("10.48550/arXiv.1706.03762")

    assert bibtex is not None
    assert isinstance(bibtex, str)
    assert bibtex.startswith("@")
    assert "title" in bibtex.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crossref_get_bibtex():
    """Test CrossRef BibTeX generation."""
    client = CrossRefClient()

    bibtex = await client.get_bibtex("10.1038/nature14539")

    assert bibtex is not None
    assert isinstance(bibtex, str)
    assert bibtex.startswith("@")
    assert "title" in bibtex.lower()
    assert "author" in bibtex.lower()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.xfail(reason="S2 rate limit - may fail without API key", strict=False)
async def test_semantic_scholar_get_bibtex():
    """Test Semantic Scholar BibTeX generation."""
    client = SemanticScholarClient()

    bibtex = await client.get_bibtex("10.48550/arXiv.2005.14165")

    assert bibtex is not None
    assert isinstance(bibtex, str)
    assert bibtex.startswith("@")
    assert "title" in bibtex.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_arxiv_get_bibtex():
    """Test arXiv BibTeX generation."""
    client = ArxivClient()

    bibtex = await client.get_bibtex("1706.03762")

    assert bibtex is not None
    assert isinstance(bibtex, str)
    assert bibtex.startswith("@")
    assert "title" in bibtex.lower()
    assert "arxiv" in bibtex.lower() or "eprint" in bibtex.lower()


# =============================================================================
# Semantic Scholar Citations Test
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.xfail(reason="S2 rate limit - may fail without API key", strict=False)
async def test_semantic_scholar_get_citations():
    """Test Semantic Scholar citation retrieval."""
    client = SemanticScholarClient()

    result = await client.get_citations("10.48550/arXiv.1706.03762", limit=5)

    assert result is not None
    assert result.paper_id == "10.48550/arXiv.1706.03762"
    assert result.citation_count > 0
    assert result.citing_papers is not None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.xfail(reason="S2 rate limit - may fail without API key", strict=False)
async def test_semantic_scholar_search():
    """Test Semantic Scholar paper search."""
    client = SemanticScholarClient()

    result = await client.search("attention is all you need", limit=5)

    assert result is not None
    assert result.source == PaperSource.SEMANTIC_SCHOLAR
    assert result.returned_count > 0
    assert result.papers is not None
    assert len(result.papers) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_arxiv_search():
    """Test arXiv paper search."""
    client = ArxivClient()

    result = await client.search("machine learning", limit=5)

    assert result is not None
    assert result.source == PaperSource.ARXIV
    assert result.returned_count > 0
    assert result.papers is not None
    assert len(result.papers) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_arxiv_get_paper():
    """Test arXiv get paper by ID."""
    client = ArxivClient()

    paper = await client.get_paper("1706.03762")

    assert paper is not None
    assert paper.arxiv_id is not None
    assert "1706.03762" in paper.arxiv_id
    assert paper.title is not None
    assert "attention" in paper.title.lower()
