"""Tests for Pydantic models."""

from datetime import date

import pytest
from pydantic import ValidationError

from academix.models import (
    Author,
    GetBibTeXInput,
    Paper,
    PaperSource,
    SearchPapersInput,
    SearchResult,
)


class TestAuthor:
    """Tests for Author model."""

    def test_basic_author(self):
        """Test basic author creation."""
        author = Author(name="John Smith")
        assert author.name == "John Smith"
        assert author.orcid is None
        assert author.affiliation is None

    def test_full_author(self):
        """Test author with all fields."""
        author = Author(
            name="John Smith",
            orcid="0000-0001-2345-6789",
            affiliation="MIT",
            author_id="A123",
        )
        assert author.name == "John Smith"
        assert author.orcid == "0000-0001-2345-6789"
        assert author.affiliation == "MIT"

    def test_whitespace_stripping(self):
        """Test that whitespace is stripped."""
        author = Author(name="  John Smith  ")
        assert author.name == "John Smith"


class TestPaper:
    """Tests for Paper model."""

    def test_minimal_paper(self):
        """Test paper with minimal required fields."""
        paper = Paper(
            id="W12345",
            title="Test Paper",
            source=PaperSource.OPENALEX,
        )
        assert paper.id == "W12345"
        assert paper.title == "Test Paper"
        assert paper.source == PaperSource.OPENALEX
        assert paper.authors == []
        assert paper.citation_count == 0

    def test_full_paper(self):
        """Test paper with all fields."""
        paper = Paper(
            id="W12345",
            title="Test Paper",
            authors=[Author(name="John Smith")],
            abstract="This is the abstract.",
            year=2024,
            published_date=date(2024, 1, 15),
            venue="Nature",
            volume="123",
            issue="4",
            pages="100-110",
            doi="10.1038/nature12345",
            arxiv_id="2401.12345",
            url="https://example.com/paper",
            pdf_url="https://example.com/paper.pdf",
            citation_count=100,
            source=PaperSource.OPENALEX,
        )
        assert paper.year == 2024
        assert paper.doi == "10.1038/nature12345"
        assert paper.citation_count == 100

    def test_doi_normalization(self):
        """Test DOI prefix stripping."""
        paper = Paper(
            id="W12345",
            title="Test",
            doi="https://doi.org/10.1038/nature12345",
            source=PaperSource.OPENALEX,
        )
        assert paper.doi == "10.1038/nature12345"

    def test_year_validation(self):
        """Test year range validation."""
        # Valid year
        paper = Paper(
            id="W12345",
            title="Test",
            year=2024,
            source=PaperSource.OPENALEX,
        )
        assert paper.year == 2024

        # Invalid year - too old
        with pytest.raises(ValidationError):
            Paper(
                id="W12345",
                title="Test",
                year=1800,
                source=PaperSource.OPENALEX,
            )


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_empty_result(self):
        """Test empty search result."""
        result = SearchResult(
            total_results=0,
            returned_count=0,
            papers=[],
            query="test",
            source=PaperSource.OPENALEX,
        )
        assert result.total_results == 0
        assert result.has_more is False

    def test_with_papers(self):
        """Test search result with papers."""
        papers = [
            Paper(id="W1", title="Paper 1", source=PaperSource.OPENALEX),
            Paper(id="W2", title="Paper 2", source=PaperSource.OPENALEX),
        ]
        result = SearchResult(
            total_results=100,
            returned_count=2,
            papers=papers,
            query="test",
            source=PaperSource.OPENALEX,
            has_more=True,
        )
        assert result.total_results == 100
        assert len(result.papers) == 2
        assert result.has_more is True


class TestSearchPapersInput:
    """Tests for SearchPapersInput validation."""

    def test_valid_input(self):
        """Test valid search input."""
        input_data = SearchPapersInput(
            query="machine learning",
            limit=10,
        )
        assert input_data.query == "machine learning"
        assert input_data.limit == 10

    def test_query_required(self):
        """Test that query is required."""
        with pytest.raises(ValidationError):
            SearchPapersInput(limit=10)  # type: ignore[call-arg]

    def test_query_min_length(self):
        """Test minimum query length."""
        with pytest.raises(ValidationError):
            SearchPapersInput(query="")

    def test_limit_range(self):
        """Test limit validation."""
        # Too high
        with pytest.raises(ValidationError):
            SearchPapersInput(query="test", limit=200)

        # Too low
        with pytest.raises(ValidationError):
            SearchPapersInput(query="test", limit=0)

    def test_year_range_validation(self):
        """Test year range validation."""
        # Valid range
        input_data = SearchPapersInput(
            query="test",
            year_from=2020,
            year_to=2024,
        )
        assert input_data.year_from == 2020
        assert input_data.year_to == 2024

        # Invalid range (to < from)
        with pytest.raises(ValidationError):
            SearchPapersInput(
                query="test",
                year_from=2024,
                year_to=2020,
            )

    def test_whitespace_stripping(self):
        """Test whitespace stripping."""
        input_data = SearchPapersInput(query="  machine learning  ")
        assert input_data.query == "machine learning"


class TestGetBibTeXInput:
    """Tests for GetBibTeXInput validation."""

    def test_valid_single_id(self):
        """Test single paper ID."""
        input_data = GetBibTeXInput(paper_ids=["10.1038/nature12345"])
        assert len(input_data.paper_ids) == 1

    def test_valid_multiple_ids(self):
        """Test multiple paper IDs."""
        input_data = GetBibTeXInput(paper_ids=["10.1038/nature12345", "2401.12345"])
        assert len(input_data.paper_ids) == 2

    def test_empty_list(self):
        """Test empty paper ID list."""
        with pytest.raises(ValidationError):
            GetBibTeXInput(paper_ids=[])

    def test_max_ids(self):
        """Test maximum paper IDs limit."""
        # 50 is max
        ids = [f"doi{i}" for i in range(51)]
        with pytest.raises(ValidationError):
            GetBibTeXInput(paper_ids=ids)
