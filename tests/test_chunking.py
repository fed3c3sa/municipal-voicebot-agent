"""Unit tests for the HTML chunker (pure, no I/O)."""

from __future__ import annotations

from municipal_mcp.chunking import chunk_html

SAMPLE = """
<html><body><main>
  <nav>menu da ignorare</nav>
  <h1>Carta d'identita</h1>
  <h2>Costi</h2>
  <p>Il costo e' di 22,21 euro.</p>
  <h2>Orari</h2>
  <p>Aperto il lunedi.</p>
  <ul><li>martedi mattina</li></ul>
  <footer>piè di pagina</footer>
</main></body></html>
"""


def test_chunks_have_sequential_indexes():
    chunks = chunk_html(SAMPLE)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_heading_path_is_tracked():
    chunks = chunk_html(SAMPLE)
    costi = next(chunk for chunk in chunks if "22,21" in chunk.content)
    assert costi.heading_path == "Carta d'identita > Costi"


def test_dropped_tags_are_ignored():
    chunks = chunk_html(SAMPLE)
    joined = " ".join(chunk.content for chunk in chunks)
    assert "menu da ignorare" not in joined
    assert "piè di pagina" not in joined


def test_list_items_are_captured():
    chunks = chunk_html(SAMPLE)
    joined = " ".join(chunk.content for chunk in chunks)
    assert "martedi mattina" in joined


def test_long_section_is_split_with_overlap():
    long_text = "parola " * 500  # ~3500 chars
    html = f"<html><body><h1>T</h1><p>{long_text}</p></body></html>"
    chunks = chunk_html(html, max_chars=1000, overlap=100)
    assert len(chunks) > 1
    assert all(len(chunk.content) <= 1000 for chunk in chunks)
