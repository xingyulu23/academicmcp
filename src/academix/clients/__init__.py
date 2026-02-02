"""API clients for academic data sources."""

from .arxiv_client import ArxivClient
from .base import BaseClient
from .crossref import CrossRefClient
from .dblp import DBLPClient
from .openalex import OpenAlexClient
from .semantic import SemanticScholarClient

__all__ = [
    "BaseClient",
    "OpenAlexClient",
    "DBLPClient",
    "SemanticScholarClient",
    "ArxivClient",
    "CrossRefClient",
]
