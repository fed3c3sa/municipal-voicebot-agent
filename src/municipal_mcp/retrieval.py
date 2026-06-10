"""Hybrid document retrieval: lexical (Italian full-text) + vector, fused by RRF.

The vector arm and the lexical arm each rank the chunks independently; the two
rankings are merged with weighted Reciprocal Rank Fusion (RRF):

    score = alpha * 1/(k + rank_vector) + (1 - alpha) * 1/(k + rank_lexical)

alpha controls the balance (1.0 = pure vector, 0.0 = pure lexical). When the
vector arm is disabled (alpha == 0 or vector_search_enabled is false) we skip the
query embedding entirely and run a plain lexical search.
"""

from __future__ import annotations

from .config import get_settings
from .db import get_connection, vector_literal
from .embeddings import embed_query
from .models import SearchResult

# Hybrid query: rank by vector and by lexical relevance, then fuse with RRF.
_HYBRID_SQL = """
WITH semantic AS (
    SELECT id, RANK() OVER (ORDER BY embedding <=> %(qvec)s::vector) AS rank
    FROM docs.chunks
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %(qvec)s::vector
    LIMIT %(pool)s
),
lexical AS (
    SELECT id, RANK() OVER (
        ORDER BY ts_rank_cd(content_tsv, plainto_tsquery('italian', %(qtext)s)) DESC
    ) AS rank
    FROM docs.chunks
    WHERE content_tsv @@ plainto_tsquery('italian', %(qtext)s)
    ORDER BY ts_rank_cd(content_tsv, plainto_tsquery('italian', %(qtext)s)) DESC
    LIMIT %(pool)s
),
fused AS (
    SELECT
        c.id,
        COALESCE(%(alpha)s * (1.0 / (%(k)s + s.rank)), 0)
        + COALESCE((1 - %(alpha)s) * (1.0 / (%(k)s + l.rank)), 0) AS score
    FROM docs.chunks c
    LEFT JOIN semantic s ON s.id = c.id
    LEFT JOIN lexical l ON l.id = c.id
    WHERE s.id IS NOT NULL OR l.id IS NOT NULL
)
SELECT
    f.score,
    ch.content, ch.heading_path, ch.chunk_index, ch.full_text,
    d.title, d.category, d.source_url, d.doc_date
FROM fused f
JOIN docs.chunks ch ON ch.id = f.id
JOIN docs.documents d ON d.id = ch.document_id
ORDER BY f.score DESC
LIMIT %(top_k)s
"""

# Lexical-only query (vector arm disabled).
_LEXICAL_SQL = """
SELECT
    ts_rank_cd(ch.content_tsv, plainto_tsquery('italian', %(qtext)s)) AS score,
    ch.content, ch.heading_path, ch.chunk_index, ch.full_text,
    d.title, d.category, d.source_url, d.doc_date
FROM docs.chunks ch
JOIN docs.documents d ON d.id = ch.document_id
WHERE ch.content_tsv @@ plainto_tsquery('italian', %(qtext)s)
ORDER BY score DESC
LIMIT %(top_k)s
"""


def should_use_vector(alpha: float, vector_enabled: bool) -> bool:
    """The vector arm runs only when it is enabled and given a non-zero weight."""
    return vector_enabled and alpha > 0.0


def hybrid_search(
    query: str,
    *,
    top_k: int | None = None,
    alpha: float | None = None,
    vector_enabled: bool | None = None,
) -> list[SearchResult]:
    """Search the document chunks and return the best matches."""
    settings = get_settings()
    top_k = settings.retrieval_top_k if top_k is None else top_k
    alpha = settings.retrieval_alpha if alpha is None else alpha
    if vector_enabled is None:
        vector_enabled = settings.vector_search_enabled

    use_vector = should_use_vector(alpha, vector_enabled)
    candidate_pool = max(50, top_k)

    with get_connection() as conn, conn.cursor() as cur:
        if use_vector:
            cur.execute(
                _HYBRID_SQL,
                {
                    "qvec": vector_literal(embed_query(query)),
                    "qtext": query,
                    "alpha": alpha,
                    "k": settings.rrf_k,
                    "pool": candidate_pool,
                    "top_k": top_k,
                },
            )
        else:
            cur.execute(_LEXICAL_SQL, {"qtext": query, "top_k": top_k})
        rows = cur.fetchall()

    return [SearchResult(**row) for row in rows]
