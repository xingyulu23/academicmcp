# Academic MCP Server

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)

A Model Context Protocol (MCP) server for searching, downloading, and analyzing academic papers from multiple sources.

Aggregates data from **OpenAlex**, **DBLP**, **Semantic Scholar**, **arXiv**, and **CrossRef** to provide a unified academic research interface for LLMs.

Designed for seamless integration with large language models like **Claude Desktop** and **OpenCode**.

## Features

- **🔍 Multi-Source Search**: Unified search across OpenAlex (100K+ free calls/day), DBLP (CS papers), Semantic Scholar (AI recommendations), arXiv (preprints), and CrossRef (DOI resolution).
- **🧠 Smart ID Resolution**: Automatically detects and handles DOIs, arXiv IDs, OpenAlex IDs, Semantic Scholar IDs, and DBLP keys.
- **📚 BibTeX Export**: Native BibTeX support from DBLP (high quality) with automatic fallback generation for other sources. Supports batch export.
- **📊 Citation Analysis**: Retrieve citation counts, citing papers, and generate citation network data for visualization.
- **🤖 AI Recommendations**: Leverage Semantic Scholar's AI engine to find related papers based on content and citations.
- **⚡ Asynchronous**: Built with `httpx` and `asyncio` for high-performance concurrent API requests.

## Installation

### Quick Start (for Users)

If you are using `uv` (recommended):

```bash
uv tool install academix
```

Or with `pip`:

```bash
pip install academix
```

### Development Setup (for Contributors)

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-org/academix.git
    cd academix
    ```

2.  **Install dependencies**:
    ```bash
    uv sync
    ```

3.  **Run the server**:
    ```bash
    uv run academix
    ```

## Configuration

### 1. Claude Desktop Integration

To use this server with Claude Desktop, add the following to your configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "academix": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/academix", 
        "academix"
      ],
      "env": {
        "ACADEMIX_EMAIL": "your.email@example.com",
        "SEMANTIC_SCHOLAR_API_KEY": "optional_api_key"
      }
    }
  }
}
```

> **Note**: Replace `/absolute/path/to/academix` with the actual path where you cloned the repository. Setting `ACADEMIX_EMAIL` is highly recommended to access the "polite pool" for OpenAlex and CrossRef (higher rate limits).

### 2. OpenCode Integration

For OpenCode, modify your configuration file (usually at `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "academix": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "--directory",
        "/absolute/path/to/academix",
        "academix"
      ],
      "environment": {
        "ACADEMIX_EMAIL": "your.email@example.com",
        "SEMANTIC_SCHOLAR_API_KEY": "optional_api_key"
      },
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

**Configuration Details:**
- **type**: Must be `"local"`.
- **command**: The full command array to run the server. Use `uv run` pointing to the directory.
- **directory**: Replace `/absolute/path/to/academix` with your actual path.
- **environment**: Add API keys or email here. `ACADEMIX_EMAIL` is recommended.
- **timeout**: Optional. Increased to `10000` (10s) to handle network latency.

## Data Source Coverage

### Feature Support Matrix

| Feature | OpenAlex | DBLP | CrossRef | Semantic Scholar | arXiv |
|---------|:--------:|:----:|:--------:|:----------------:|:-----:|
| Paper Search | ✅ | ✅ | ✅ | ✅ | ✅ |
| Get Paper Details | ✅ | ✅ | ✅ | ✅ | ✅ |
| BibTeX Export | ✅ | ✅ Native | ✅ | ✅ | ✅ |
| Citation Retrieval | ✅ | ❌ | ❌ | ✅ | ❌ |
| Author Search | ✅ | ✅ | ✅ | ✅ | ✅ |
| Related Papers (AI) | ❌ | ❌ | ❌ | ✅ | ❌ |

### BibTeX Quality by Source

| Source | Quality | Notes |
|--------|---------|-------|
| **DBLP** | ⭐⭐⭐ Excellent | Native BibTeX export. Best for CS papers. Includes complete venue info. |
| **CrossRef** | ⭐⭐ Good | Accurate metadata from publishers. Requires valid DOI. |
| **arXiv** | ⭐⭐ Good | Correct preprint info. Entry type is `@misc` with `eprint` field. |
| **Semantic Scholar** | ⭐⭐ Good | Generated from metadata. May lack venue details. |
| **OpenAlex** | ⭐ Variable | Generated from metadata. Some fields may be incomplete. |

**Recommendation**: For CS papers, prioritize DBLP for BibTeX. For papers with DOI, CrossRef provides reliable metadata.

## MCP Tools

| Tool | Description |
|------|-------------|
| `academic_search_papers` | Search papers by keywords, title, author, DOI, date, venue. Supports sorting by relevance, date, or citations. |
| `academic_get_paper_details` | Get full metadata for a paper using any supported ID format. |
| `academic_get_bibtex` | Export BibTeX citations (single or batch). Prioritizes DBLP for high-quality metadata. |
| `academic_get_citations` | Get papers that cite a given paper (via OpenAlex). |
| `academic_search_author` | Find all papers by an author name. |
| `academic_get_related_papers` | AI-powered related paper recommendations (via Semantic Scholar). |
| `academic_get_citation_network` | Get citation network data (nodes/edges) for visualization. |
| `academic_cache_stats` | View cache hit rates and statistics. |

## Usage Examples

### Search for Papers
Find papers about "LLM agents" sorted by citation count:
```javascript
use academic_search_papers with:
{
  "query": "LLM agents",
  "limit": 5,
  "sort": "citation_count"
}
```

### Get BibTeX for a List of Papers
Generate BibTeX for multiple papers (mixed ID formats supported):
```javascript
use academic_get_bibtex with:
{
  "paper_ids": "10.1038/nature12345, 10.48550/arXiv.2310.08560"
}
```

### Analyze Citations
Find who is citing a specific paper:
```javascript
use academic_get_citations with:
{
  "paper_id": "W2741809807" // OpenAlex ID or DOI
}
```

## API Sources & Rate Limits

| Source | Rate Limits | Authentication | Best For |
|--------|-------------|----------------|----------|
| **OpenAlex** | 100K/day (with email) | Email (optional) | General search, citations, author data |
| **DBLP** | Reasonable use | None | CS papers, high-quality BibTeX |
| **Semantic Scholar** | 100/5min (higher with key) | API key (optional) | AI Recommendations |
| **arXiv** | Unlimited (polite) | None | Preprints (CS, Math, Physics) |
| **CrossRef** | Dynamic | Email (optional) | DOI resolution |

## Development

### Run Tests
```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=academix
```

### Project Structure
```
academix/
├── src/academix/
│   ├── server.py          # MCP server entry point
│   ├── aggregator.py      # Orchestrator for multiple API clients
│   ├── clients/           # Individual API client implementations
│   │   ├── openalex.py
│   │   ├── dblp.py
│   │   ├── semantic.py
│   │   ├── arxiv_client.py
│   │   └── crossref.py
│   └── models.py          # Pydantic data models
├── tests/                 # Unit and integration tests
├── pyproject.toml         # Dependencies and config
└── README.md
```

## License

MIT License
