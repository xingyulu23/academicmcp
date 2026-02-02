"""Pydantic models for academic paper data."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class PaperSource(str, Enum):
    """Source API for paper data."""

    OPENALEX = "openalex"
    DBLP = "dblp"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    CROSSREF = "crossref"


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


class Author(BaseModel):
    """Author information."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., description="Full name of the author")
    orcid: str | None = Field(default=None, description="ORCID identifier")
    affiliation: str | None = Field(default=None, description="Institution affiliation")
    author_id: str | None = Field(default=None, description="Source-specific author ID")


class Paper(BaseModel):
    """Academic paper metadata."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., description="Unique identifier (source-specific)")
    title: str = Field(..., description="Paper title")
    authors: list[Author] = Field(default_factory=list, description="List of authors")
    abstract: str | None = Field(default=None, description="Paper abstract")
    year: int | None = Field(default=None, ge=1900, le=2100, description="Publication year")
    published_date: date | None = Field(default=None, description="Publication date")
    venue: str | None = Field(default=None, description="Journal or conference name")
    volume: str | None = Field(default=None, description="Volume number")
    issue: str | None = Field(default=None, description="Issue number")
    pages: str | None = Field(default=None, description="Page range (e.g., '123-145')")
    doi: str | None = Field(default=None, description="Digital Object Identifier")
    arxiv_id: str | None = Field(default=None, description="arXiv identifier")
    url: str | None = Field(default=None, description="URL to paper")
    pdf_url: str | None = Field(default=None, description="Direct link to PDF")
    citation_count: int = Field(default=0, ge=0, description="Number of citations")
    source: PaperSource = Field(..., description="Data source API")
    bibtex_key: str | None = Field(default=None, description="Generated BibTeX citation key")

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, v: str | None) -> str | None:
        """Normalize DOI format."""
        if v is None:
            return None
        # Remove common prefixes
        v = v.strip()
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
            if v.lower().startswith(prefix.lower()):
                v = v[len(prefix) :]
        return v


class Citation(BaseModel):
    """Citation relationship between papers."""

    citing_paper_id: str = Field(..., description="ID of the citing paper")
    cited_paper_id: str = Field(..., description="ID of the cited paper")
    context: str | None = Field(default=None, description="Citation context text")


class SearchResult(BaseModel):
    """Search results container."""

    total_results: int = Field(..., ge=0, description="Total number of matching papers")
    returned_count: int = Field(..., ge=0, description="Number of papers in this response")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    has_more: bool = Field(default=False, description="Whether more results are available")
    papers: list[Paper] = Field(default_factory=list, description="List of papers")
    query: str = Field(..., description="Original search query")
    source: PaperSource = Field(..., description="Data source used")


class AuthorSearchResult(BaseModel):
    """Author search results."""

    total_results: int = Field(..., ge=0)
    authors: list[Author] = Field(default_factory=list)


class CitationResult(BaseModel):
    """Citation analysis result."""

    paper_id: str = Field(..., description="Target paper ID")
    citation_count: int = Field(default=0, ge=0, description="Total citations")
    citing_papers: list[Paper] = Field(
        default_factory=list, description="Papers that cite this paper"
    )
    has_more: bool = Field(default=False)


class RelatedPapersResult(BaseModel):
    """Related papers recommendation result."""

    paper_id: str = Field(..., description="Source paper ID")
    related_papers: list[Paper] = Field(default_factory=list)
    recommendation_source: str = Field(default="semantic_scholar")


class CitationNetworkNode(BaseModel):
    """Node in citation network."""

    paper_id: str
    title: str
    year: int | None = None
    citation_count: int = 0


class CitationNetworkEdge(BaseModel):
    """Edge in citation network (citation relationship)."""

    source: str = Field(..., description="Citing paper ID")
    target: str = Field(..., description="Cited paper ID")


class CitationNetwork(BaseModel):
    """Citation network graph data."""

    center_paper_id: str = Field(..., description="Central paper ID")
    nodes: list[CitationNetworkNode] = Field(default_factory=list)
    edges: list[CitationNetworkEdge] = Field(default_factory=list)
    depth: int = Field(default=1, ge=1, le=3, description="Network depth")


# Input models for MCP tools


class SearchPapersInput(BaseModel):
    """Input for paper search tool."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    query: str = Field(
        ..., min_length=1, max_length=500, description="Search query (keywords, title, etc.)"
    )
    title: str | None = Field(
        default=None, max_length=300, description="Filter by paper title (partial match)"
    )
    author: str | None = Field(default=None, max_length=200, description="Filter by author name")
    doi: str | None = Field(default=None, description="Search by exact DOI")
    year_from: int | None = Field(
        default=None, ge=1900, le=2100, description="Filter papers from this year"
    )
    year_to: int | None = Field(
        default=None, ge=1900, le=2100, description="Filter papers until this year"
    )
    venue: str | None = Field(
        default=None, max_length=200, description="Filter by journal/conference name"
    )
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN, description="Output format"
    )

    @field_validator("year_to")
    @classmethod
    def validate_year_range(cls, v: int | None, info: ValidationInfo) -> int | None:
        """Ensure year_to >= year_from."""
        year_from = info.data.get("year_from")
        if v is not None and year_from is not None and v < year_from:
            raise ValueError("year_to must be >= year_from")
        return v


class GetPaperDetailsInput(BaseModel):
    """Input for paper details tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    paper_id: str = Field(..., min_length=1, description="Paper ID (OpenAlex, DOI, arXiv ID)")
    source: PaperSource | None = Field(
        default=None, description="Preferred data source (auto-detect if not specified)"
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetBibTeXInput(BaseModel):
    """Input for BibTeX export tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    paper_ids: list[str] = Field(
        ..., min_length=1, max_length=50, description="Paper IDs to export"
    )
    use_dblp: bool = Field(default=True, description="Try DBLP for native BibTeX export first")


class GetCitationsInput(BaseModel):
    """Input for citations tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    paper_id: str = Field(..., min_length=1, description="Paper ID to get citations for")
    limit: int = Field(default=20, ge=1, le=100, description="Max citing papers to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SearchAuthorInput(BaseModel):
    """Input for author search tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    author_name: str = Field(..., min_length=2, max_length=200, description="Author name to search")
    limit: int = Field(default=20, ge=1, le=100, description="Max papers to return")
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetRelatedPapersInput(BaseModel):
    """Input for related papers tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    paper_id: str = Field(..., min_length=1, description="Paper ID to find related papers for")
    limit: int = Field(default=10, ge=1, le=50, description="Max related papers to return")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GetCitationNetworkInput(BaseModel):
    """Input for citation network tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    paper_id: str = Field(..., min_length=1, description="Central paper ID")
    depth: int = Field(
        default=1, ge=1, le=1, description="Network depth (currently only 1 supported)"
    )
    max_nodes: int = Field(default=50, ge=10, le=200, description="Maximum nodes in network")
    direction: str = Field(
        default="both",
        description="Direction: 'citing' (papers that cite), 'cited' (references), or 'both'",
    )
