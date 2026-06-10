"""Split an HTML document into retrieval chunks.

Strategy: walk the DOM in order, treat h1..h6 as section boundaries, and group
the paragraphs/list-items under the current heading. Each chunk remembers its
heading path (e.g. "Carta d'identita > Costi"), which the ingestion step
prepends before embedding for extra context. Oversized sections are split with
a small character overlap.

This is a pure function with no I/O, so it is trivial to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

_DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside"]
_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
_BLOCK_TAGS = ["p", "li", "td", "th", "dt", "dd"]


@dataclass
class Chunk:
    """One retrieval chunk: body text plus the section heading path it sits under."""

    content: str
    heading_path: str
    chunk_index: int


def chunk_html(html: str, *, max_chars: int = 1200, overlap: int = 150) -> list[Chunk]:
    """Return ordered chunks extracted from an HTML string."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    heading_stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    raw_chunks: list[tuple[str, str]] = []  # (heading_path, text)

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        heading_path = " > ".join(title for _, title in heading_stack)
        for piece in _split_with_overlap(text, max_chars, overlap):
            raw_chunks.append((heading_path, piece))

    for element in root.find_all(_HEADING_TAGS + _BLOCK_TAGS):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name in _HEADING_TAGS:
            flush()
            level = int(element.name[1])
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
        else:
            buffer.append(text)
    flush()

    return [
        Chunk(content=text, heading_path=heading_path, chunk_index=index)
        for index, (heading_path, text) in enumerate(raw_chunks)
    ]


def _split_with_overlap(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split text into windows of at most max_chars with a small overlap."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return pieces
