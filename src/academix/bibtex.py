"""BibTeX generation from paper metadata."""

import re
import unicodedata

from .models import Author, Paper

# LaTeX escape mappings for special characters
LATEX_ESCAPES: dict[str, str] = {
    "ä": '{\\"a}',
    "ö": '{\\"o}',
    "ü": '{\\"u}',
    "Ä": '{\\"A}',
    "Ö": '{\\"O}',
    "Ü": '{\\"U}',
    "ß": "{\\ss}",
    "é": "{\\'e}",
    "è": "{\\`e}",
    "ê": "{\\^e}",
    "ë": '{\\"e}',
    "á": "{\\'a}",
    "à": "{\\`a}",
    "â": "{\\^a}",
    "ã": "{\\~a}",
    "ó": "{\\'o}",
    "ò": "{\\`o}",
    "ô": "{\\^o}",
    "õ": "{\\~o}",
    "ú": "{\\'u}",
    "ù": "{\\`u}",
    "û": "{\\^u}",
    "í": "{\\'i}",
    "ì": "{\\`i}",
    "î": "{\\^i}",
    "ï": '{\\"i}',
    "ñ": "{\\~n}",
    "ç": "{\\c{c}}",
    "Ç": "{\\c{C}}",
    "ø": "{\\o}",
    "Ø": "{\\O}",
    "å": "{\\aa}",
    "Å": "{\\AA}",
    "æ": "{\\ae}",
    "Æ": "{\\AE}",
    "œ": "{\\oe}",
    "Œ": "{\\OE}",
    "&": "\\&",
    "%": "\\%",
    "$": "\\$",
    "#": "\\#",
    "_": "\\_",
    "{": "\\{",
    "}": "\\}",
    "~": "{\\textasciitilde}",
    "^": "{\\textasciicircum}",
}


def escape_latex(text: str) -> str:
    """Escape special characters for BibTeX/LaTeX.

    Args:
        text: Input text

    Returns:
        LaTeX-escaped text
    """
    if not text:
        return ""

    result = []
    for char in text:
        if char in LATEX_ESCAPES:
            result.append(LATEX_ESCAPES[char])
        else:
            result.append(char)
    return "".join(result)


def generate_bibtex_key(paper: Paper) -> str:
    """Generate a BibTeX citation key for a paper.

    Format: FirstAuthorLastName + Year + FirstTitleWord
    Example: Smith2024Neural

    Args:
        paper: Paper metadata

    Returns:
        BibTeX citation key
    """
    parts = []

    # First author's last name
    if paper.authors:
        first_author = paper.authors[0].name
        # Extract last name (handle "Last, First" and "First Last" formats)
        if "," in first_author:
            last_name = first_author.split(",")[0].strip()
        else:
            name_parts = first_author.split()
            last_name = name_parts[-1] if name_parts else "Unknown"
        # Remove accents and special characters
        last_name = unicodedata.normalize("NFKD", last_name)
        last_name = "".join(c for c in last_name if c.isalnum())
        parts.append(last_name.capitalize())
    else:
        parts.append("Unknown")

    # Year
    if paper.year:
        parts.append(str(paper.year))

    # First significant word from title
    if paper.title:
        # Remove common words
        stop_words = {"a", "an", "the", "on", "in", "of", "for", "to", "and", "with"}
        words = re.findall(r"\b[a-zA-Z]+\b", paper.title)
        for word in words:
            if word.lower() not in stop_words:
                # Remove accents
                word = unicodedata.normalize("NFKD", word)
                word = "".join(c for c in word if c.isalnum())
                parts.append(word.capitalize())
                break

    return "".join(parts) if parts else "unknown"


def format_authors_bibtex(authors: list[Author]) -> str:
    """Format author list for BibTeX.

    BibTeX format: "Last1, First1 and Last2, First2 and Last3, First3"

    Args:
        authors: List of Author objects

    Returns:
        BibTeX-formatted author string
    """
    if not authors:
        return ""

    formatted = []
    for author in authors:
        name = author.name.strip()
        # Handle already-formatted "Last, First" format
        if "," in name:
            formatted.append(escape_latex(name))
        else:
            # Convert "First Last" to "Last, First"
            parts = name.split()
            if len(parts) >= 2:
                last = parts[-1]
                first = " ".join(parts[:-1])
                formatted.append(f"{escape_latex(last)}, {escape_latex(first)}")
            else:
                formatted.append(escape_latex(name))

    return " and ".join(formatted)


def determine_entry_type(paper: Paper) -> str:
    """Determine the BibTeX entry type for a paper.

    Args:
        paper: Paper metadata

    Returns:
        BibTeX entry type (article, inproceedings, misc, etc.)
    """
    venue_lower = (paper.venue or "").lower()

    # Conference indicators
    conference_keywords = [
        "conference",
        "proceedings",
        "workshop",
        "symposium",
        "icml",
        "neurips",
        "iclr",
        "cvpr",
        "iccv",
        "eccv",
        "acl",
        "emnlp",
        "naacl",
        "aaai",
        "ijcai",
        "sigchi",
        "sigmod",
        "vldb",
        "icse",
        "fse",
        "issta",
        "pldi",
    ]

    # Journal indicators
    journal_keywords = [
        "journal",
        "transactions",
        "review",
        "letters",
        "nature",
        "science",
        "cell",
        "lancet",
        "nejm",
        "ieee",
        "acm",
        "springer",
        "elsevier",
    ]

    # Check for arXiv
    if paper.arxiv_id or "arxiv" in venue_lower:
        return "misc"

    # Check for conference
    for keyword in conference_keywords:
        if keyword in venue_lower:
            return "inproceedings"

    # Check for journal
    for keyword in journal_keywords:
        if keyword in venue_lower:
            return "article"

    # Default based on presence of volume/pages
    if paper.volume and paper.pages:
        return "article"

    return "misc"


def generate_bibtex(paper: Paper, custom_key: str | None = None) -> str:
    """Generate a BibTeX entry from paper metadata.

    Args:
        paper: Paper metadata
        custom_key: Optional custom citation key

    Returns:
        Complete BibTeX entry string
    """
    entry_type = determine_entry_type(paper)
    key = custom_key or paper.bibtex_key or generate_bibtex_key(paper)

    lines = [f"@{entry_type}{{{key},"]

    # Required fields
    if paper.authors:
        lines.append(f"  author = {{{format_authors_bibtex(paper.authors)}}},")

    if paper.title:
        lines.append(f"  title = {{{escape_latex(paper.title)}}},")

    # Entry-type specific fields
    if entry_type == "article":
        if paper.venue:
            lines.append(f"  journal = {{{escape_latex(paper.venue)}}},")
    elif entry_type == "inproceedings" and paper.venue:
        lines.append(f"  booktitle = {{{escape_latex(paper.venue)}}},")

    # Common optional fields
    if paper.year:
        lines.append(f"  year = {{{paper.year}}},")

    if paper.volume:
        lines.append(f"  volume = {{{paper.volume}}},")

    if paper.issue:
        lines.append(f"  number = {{{paper.issue}}},")

    if paper.pages:
        # Normalize page range to use double dash
        pages = paper.pages.replace("–", "--").replace("-", "--")
        # Avoid triple dashes
        pages = re.sub(r"-{3,}", "--", pages)
        lines.append(f"  pages = {{{pages}}},")

    if paper.doi:
        lines.append(f"  doi = {{{paper.doi}}},")

    if paper.arxiv_id:
        lines.append(f"  eprint = {{{paper.arxiv_id}}},")
        lines.append("  archiveprefix = {arXiv},")

    if paper.url:
        lines.append(f"  url = {{{paper.url}}},")

    # Abstract (optional, can be long)
    if paper.abstract:
        # Truncate very long abstracts
        abstract = paper.abstract
        if len(abstract) > 1000:
            abstract = abstract[:997] + "..."
        lines.append(f"  abstract = {{{escape_latex(abstract)}}},")

    # Remove trailing comma from last field
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("}")

    return "\n".join(lines)


def generate_bibtex_batch(papers: list[Paper]) -> str:
    """Generate BibTeX entries for multiple papers.

    Args:
        papers: List of Paper objects

    Returns:
        Combined BibTeX entries separated by blank lines
    """
    entries = []
    used_keys: set[str] = set()

    for paper in papers:
        key = paper.bibtex_key or generate_bibtex_key(paper)

        # Ensure unique keys
        original_key = key
        counter = 1
        while key in used_keys:
            key = f"{original_key}{chr(ord('a') + counter - 1)}"
            counter += 1
        used_keys.add(key)

        entries.append(generate_bibtex(paper, custom_key=key))

    return "\n\n".join(entries)


def parse_bibtex_key_from_entry(bibtex: str) -> str | None:
    """Extract the citation key from a BibTeX entry.

    Args:
        bibtex: BibTeX entry string

    Returns:
        Citation key or None if not found
    """
    match = re.search(r"@\w+\{([^,]+),", bibtex)
    return match.group(1).strip() if match else None
