"""Request and response schemas for the embedding service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., description="Texts to embed.")
    is_query: bool = Field(
        default=False,
        description="If true, apply the query instruction prompt. Documents use no prompt.",
    )


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
