"""Pytest configuration and fixtures for academix tests."""

import pytest
import respx


@pytest.fixture
def mock_openalex():
    """Mock OpenAlex API responses."""
    with respx.mock(base_url="https://api.openalex.org") as respx_mock:
        yield respx_mock


@pytest.fixture
def mock_dblp():
    """Mock DBLP API responses."""
    with respx.mock(base_url="https://dblp.org") as respx_mock:
        yield respx_mock


@pytest.fixture
def mock_semantic_scholar():
    """Mock Semantic Scholar API responses."""
    with respx.mock(base_url="https://api.semanticscholar.org") as respx_mock:
        yield respx_mock


@pytest.fixture
def mock_crossref():
    """Mock CrossRef API responses."""
    with respx.mock(base_url="https://api.crossref.org") as respx_mock:
        yield respx_mock


@pytest.fixture
def sample_paper_openalex():
    """Sample OpenAlex paper response."""
    return {
        "id": "https://openalex.org/W2741809807",
        "display_name": "Attention Is All You Need",
        "title": "Attention Is All You Need",
        "publication_year": 2017,
        "publication_date": "2017-06-12",
        "cited_by_count": 100000,
        "doi": "https://doi.org/10.48550/arXiv.1706.03762",
        "authorships": [
            {
                "author": {
                    "id": "https://openalex.org/A123",
                    "display_name": "Ashish Vaswani",
                    "orcid": None,
                },
                "institutions": [{"display_name": "Google Brain"}],
            },
            {
                "author": {
                    "id": "https://openalex.org/A456",
                    "display_name": "Noam Shazeer",
                    "orcid": None,
                },
                "institutions": [],
            },
        ],
        "primary_location": {
            "source": {"display_name": "Advances in Neural Information Processing Systems"},
            "is_oa": True,
            "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
        },
        "abstract_inverted_index": {
            "The": [0],
            "dominant": [1],
            "sequence": [2],
            "transduction": [3],
            "models": [4],
        },
        "biblio": {"volume": "30", "issue": None, "first_page": "5998", "last_page": "6008"},
    }


@pytest.fixture
def sample_paper_dblp():
    """Sample DBLP paper response."""
    return {
        "result": {
            "hits": {
                "@total": "1",
                "hit": [
                    {
                        "@id": "journals/corr/VaswaniSPUJGKP17",
                        "info": {
                            "key": "journals/corr/VaswaniSPUJGKP17",
                            "title": "Attention Is All You Need",
                            "year": "2017",
                            "venue": "CoRR",
                            "authors": {
                                "author": [
                                    {"text": "Ashish Vaswani", "@pid": "123"},
                                    {"text": "Noam Shazeer", "@pid": "456"},
                                ]
                            },
                            "doi": "10.48550/arXiv.1706.03762",
                            "url": "https://arxiv.org/abs/1706.03762",
                        },
                    }
                ],
            }
        }
    }


@pytest.fixture
def sample_bibtex():
    """Sample BibTeX entry."""
    return """@inproceedings{DBLP:VaswaniSPUJGKP17,
  author    = {Ashish Vaswani and
               Noam Shazeer and
               Niki Parmar},
  title     = {Attention Is All You Need},
  booktitle = {Advances in Neural Information Processing Systems 30},
  year      = {2017},
  pages     = {5998--6008}
}"""


@pytest.fixture
def sample_search_result_openalex(sample_paper_openalex):
    """Sample OpenAlex search response."""
    return {
        "meta": {"count": 1, "db_response_time_ms": 50, "page": 1, "per_page": 10},
        "results": [sample_paper_openalex],
    }
