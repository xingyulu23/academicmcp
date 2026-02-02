"""Tests for BibTeX generation."""


from academix.bibtex import (
    escape_latex,
    format_authors_bibtex,
    generate_bibtex,
    generate_bibtex_key,
)
from academix.models import Author, Paper, PaperSource


class TestEscapeLatex:
    """Tests for LaTeX escaping."""

    def test_escape_special_chars(self):
        """Test escaping of special characters."""
        assert "&" in escape_latex("A & B")
        assert "\\&" in escape_latex("A & B")

    def test_escape_umlauts(self):
        """Test escaping of German umlauts."""
        result = escape_latex("Müller")
        assert '{\\"u}' in result

    def test_escape_accents(self):
        """Test escaping of accented characters."""
        result = escape_latex("résumé")
        assert "{\\'e}" in result

    def test_empty_string(self):
        """Test empty string handling."""
        assert escape_latex("") == ""

    def test_no_special_chars(self):
        """Test string without special characters."""
        assert escape_latex("Hello World") == "Hello World"


class TestFormatAuthorsBibtex:
    """Tests for author formatting."""

    def test_single_author(self):
        """Test single author formatting."""
        authors = [Author(name="John Smith")]
        result = format_authors_bibtex(authors)
        assert "Smith, John" in result

    def test_multiple_authors(self):
        """Test multiple authors with 'and' separator."""
        authors = [
            Author(name="John Smith"),
            Author(name="Jane Doe"),
        ]
        result = format_authors_bibtex(authors)
        assert " and " in result
        assert "Smith, John" in result
        assert "Doe, Jane" in result

    def test_already_formatted(self):
        """Test already-formatted 'Last, First' names."""
        authors = [Author(name="Smith, John")]
        result = format_authors_bibtex(authors)
        assert "Smith, John" in result

    def test_empty_authors(self):
        """Test empty author list."""
        assert format_authors_bibtex([]) == ""


class TestGenerateBibtexKey:
    """Tests for BibTeX key generation."""

    def test_basic_key(self):
        """Test basic key generation."""
        paper = Paper(
            id="test123",
            title="Neural Networks for NLP",
            authors=[Author(name="John Smith")],
            year=2024,
            source=PaperSource.OPENALEX,
        )
        key = generate_bibtex_key(paper)
        assert "Smith" in key
        assert "2024" in key
        assert "Neural" in key

    def test_no_authors(self):
        """Test key generation without authors."""
        paper = Paper(
            id="test123",
            title="A Paper",
            authors=[],
            year=2024,
            source=PaperSource.OPENALEX,
        )
        key = generate_bibtex_key(paper)
        assert "Unknown" in key

    def test_skip_stop_words(self):
        """Test that stop words are skipped in key."""
        paper = Paper(
            id="test123",
            title="The Art of Programming",
            authors=[Author(name="John Smith")],
            year=2024,
            source=PaperSource.OPENALEX,
        )
        key = generate_bibtex_key(paper)
        # Should use "Art" not "The"
        assert "Art" in key


class TestGenerateBibtex:
    """Tests for full BibTeX generation."""

    def test_article_bibtex(self):
        """Test article BibTeX generation."""
        paper = Paper(
            id="test123",
            title="Machine Learning Methods",
            authors=[
                Author(name="John Smith"),
                Author(name="Jane Doe"),
            ],
            year=2024,
            venue="Nature Machine Intelligence",
            volume="5",
            pages="123--145",
            doi="10.1038/example",
            source=PaperSource.OPENALEX,
        )
        bibtex = generate_bibtex(paper)

        assert "@article{" in bibtex
        assert "author = {" in bibtex
        assert "title = {Machine Learning Methods}" in bibtex
        assert "journal = {Nature Machine Intelligence}" in bibtex
        assert "year = {2024}" in bibtex
        assert "volume = {5}" in bibtex
        assert "pages = {123--145}" in bibtex
        assert "doi = {10.1038/example}" in bibtex

    def test_inproceedings_bibtex(self):
        """Test conference paper BibTeX generation."""
        paper = Paper(
            id="test123",
            title="Deep Learning Conference Paper",
            authors=[Author(name="John Smith")],
            year=2024,
            venue="Proceedings of ICML 2024",
            pages="100--110",
            source=PaperSource.OPENALEX,
        )
        bibtex = generate_bibtex(paper)

        assert "@inproceedings{" in bibtex
        assert "booktitle = {" in bibtex

    def test_arxiv_bibtex(self):
        """Test arXiv paper BibTeX generation."""
        paper = Paper(
            id="arxiv:2401.12345",
            title="An arXiv Preprint",
            authors=[Author(name="John Smith")],
            year=2024,
            arxiv_id="2401.12345",
            source=PaperSource.ARXIV,
        )
        bibtex = generate_bibtex(paper)

        assert "@misc{" in bibtex
        assert "eprint = {2401.12345}" in bibtex
        assert "archiveprefix = {arXiv}" in bibtex

    def test_custom_key(self):
        """Test custom BibTeX key."""
        paper = Paper(
            id="test123",
            title="A Paper",
            authors=[Author(name="John Smith")],
            year=2024,
            source=PaperSource.OPENALEX,
        )
        bibtex = generate_bibtex(paper, custom_key="customkey2024")

        assert "@" in bibtex
        assert "{customkey2024," in bibtex
