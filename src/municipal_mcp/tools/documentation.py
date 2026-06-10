"""The search_documentation tool.

Prompt and docstring are in English (they form the tool schema the voice agent
reads), but the returned text is always in Italian.
"""

from __future__ import annotations

from ..models import SearchResult
from ..retrieval import hybrid_search

# Keep each passage short so the voice model does not overflow its context.
_MAX_PASSAGE_CHARS = 600


def _section_label(result: SearchResult) -> str:
    """Return the most specific heading available for a result."""
    if result.heading_path:
        return result.heading_path.split(" > ")[-1]
    return result.title


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _MAX_PASSAGE_CHARS:
        return text
    return text[:_MAX_PASSAGE_CHARS].rstrip() + "..."


def format_results(results: list[SearchResult]) -> str:
    """Build a compact Italian answer from the retrieved passages."""
    if not results:
        return (
            "Non ho trovato informazioni nei documenti del Comune di Codroipo "
            "per questa richiesta. Puo' riformulare la domanda o contattare il "
            "centralino allo 0432 824500."
        )

    lines = ["Ho trovato queste informazioni nei documenti del Comune di Codroipo:"]
    for index, result in enumerate(results, start=1):
        lines.append(f"\n{index}. {result.title} ({_section_label(result)})")
        lines.append(_shorten(result.content))
    return "\n".join(lines)


def register(mcp) -> None:
    """Register the documentation tool on the given FastMCP server."""

    @mcp.tool
    def search_documentation(query: str, top_k: int | None = None) -> str:
        """Search the Codroipo municipal documents to answer a citizen question.

        Use this for any question about municipal services, offices, opening
        hours, contacts, local taxes (ILIA, TARIC), certificates, and procedures.
        Returns the most relevant passages in Italian with their source titles.

        Args:
            query: The citizen question or keywords, written in Italian.
            top_k: Optional maximum number of passages to return.
        """
        results = hybrid_search(query, top_k=top_k)
        return format_results(results)
