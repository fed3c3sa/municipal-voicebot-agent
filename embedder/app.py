"""Tiny embedding service.

    POST /embed  {"texts": [...], "is_query": bool} -> {"embeddings": [[...], ...]}
    GET  /health -> {"status": "ok"}

Queries get the model's built-in "query" instruction prompt; documents get no
prompt. The ingestion script and the search tool both call this service, so the
exact same encoding is used at write time and at query time.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sentence_transformers import SentenceTransformer

from .models import EmbedRequest, EmbedResponse

MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
QUERY_PROMPT_NAME = os.environ.get("EMBEDDING_QUERY_PROMPT_NAME", "query")

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Load the model once and reuse it."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the model during startup so the healthcheck only passes once the
    # service can actually serve embeddings.
    get_model()
    yield


app = FastAPI(title="Codroipo embedding service", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    if not request.texts:
        return EmbedResponse(embeddings=[])
    model = get_model()
    if request.is_query:
        vectors = model.encode(request.texts, prompt_name=QUERY_PROMPT_NAME)
    else:
        vectors = model.encode(request.texts)
    return EmbedResponse(embeddings=[vector.tolist() for vector in vectors])
