"""Ingest municipal HTML documents into Postgres.

Runs on the HOST (outside Docker). For each HTML file it:
  1. extracts metadata (title, category, date, source url) from the <head>,
  2. splits the body into chunks (chunking.chunk_html),
  3. embeds every chunk through the embedding service,
  4. upserts the document and its chunks, storing the whole document text on the
     first chunk (chunk_index = 0).

Re-running is idempotent: a document with the same slug is replaced.

Point PG_HOST and EMBEDDING_SERVICE_URL at the published container ports, e.g.
    PG_HOST=localhost EMBEDDING_SERVICE_URL=http://localhost:8001 \
        python scripts/ingest.py --reset
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from municipal_mcp.chunking import Chunk, chunk_html
from municipal_mcp.db import close_pool, get_connection, vector_literal
from municipal_mcp.embeddings import embed_texts

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"


@dataclass
class DocumentMeta:
    slug: str
    title: str
    category: str | None
    source_url: str | None
    doc_date: date | None


def extract_metadata(html: str, slug: str) -> DocumentMeta:
    """Read the document metadata from the HTML <head>."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else slug

    def meta(name: str) -> str | None:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    raw_date = meta("date")
    return DocumentMeta(
        slug=slug,
        title=title,
        category=meta("category"),
        source_url=meta("source_url"),
        doc_date=date.fromisoformat(raw_date) if raw_date else None,
    )


def text_to_embed(chunk: Chunk) -> str:
    """Prepend the heading path so the embedding carries section context."""
    if chunk.heading_path:
        return f"{chunk.heading_path}\n{chunk.content}"
    return chunk.content


def ingest_file(conn, path: Path) -> int:
    """Ingest a single HTML file. Returns the number of chunks stored."""
    html = path.read_text(encoding="utf-8")
    meta = extract_metadata(html, slug=path.stem)
    chunks = chunk_html(html)
    if not chunks:
        print(f"  skip {path.name}: no extractable content")
        return 0

    full_text = "\n\n".join(chunk.content for chunk in chunks)
    embeddings = embed_texts([text_to_embed(chunk) for chunk in chunks], is_query=False)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM docs.documents WHERE slug = %s", (meta.slug,))
        cur.execute(
            """
            INSERT INTO docs.documents (slug, title, category, source_url, doc_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (meta.slug, meta.title, meta.category, meta.source_url, meta.doc_date),
        )
        document_id = cur.fetchone()["id"]
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """
                INSERT INTO docs.chunks
                    (document_id, chunk_index, content, heading_path, full_text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    document_id,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.heading_path or None,
                    full_text if chunk.chunk_index == 0 else None,
                    vector_literal(embedding),
                ),
            )
    conn.commit()
    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest municipal HTML documents into Postgres.")
    parser.add_argument("--documents-dir", type=Path, default=DOCUMENTS_DIR)
    parser.add_argument("--reset", action="store_true", help="Delete all documents before ingesting.")
    args = parser.parse_args()

    files = sorted(args.documents_dir.glob("*.html"))
    if not files:
        print(f"No HTML files found in {args.documents_dir}")
        return

    try:
        with get_connection() as conn:
            if args.reset:
                with conn.cursor() as cur:
                    cur.execute("TRUNCATE docs.documents RESTART IDENTITY CASCADE")
                conn.commit()
                print("Reset: cleared docs.documents")

            total_docs = 0
            total_chunks = 0
            for path in files:
                count = ingest_file(conn, path)
                if count:
                    total_docs += 1
                    total_chunks += count
                    print(f"  ingested {path.name}: {count} chunks")

        print(f"Done. {total_docs} documents, {total_chunks} chunks.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
