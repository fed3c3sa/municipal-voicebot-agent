"""HTTP client for the embedding service.

Shared by the ingestion script (documents) and the search tool (queries) so the
same encoding path is always used.
"""

from __future__ import annotations

import httpx

from .config import get_settings


def embed_texts(texts: list[str], *, is_query: bool, timeout: float = 60.0) -> list[list[float]]:
    """Return one embedding per input text. Empty input returns an empty list."""
    if not texts:
        return []
    settings = get_settings()
    url = settings.embedding_service_url.rstrip("/") + "/embed"
    response = httpx.post(
        url,
        json={"texts": texts, "is_query": is_query},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def embed_query(text: str, *, timeout: float = 60.0) -> list[float]:
    """Embed a single search query (applies the query instruction prompt)."""
    return embed_texts([text], is_query=True, timeout=timeout)[0]
