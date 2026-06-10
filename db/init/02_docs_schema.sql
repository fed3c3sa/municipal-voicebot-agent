-- Document retrieval schema.
--
-- A document is split into ordered chunks. Each chunk carries its own
-- embedding and a generated Italian tsvector for lexical (BM25-style) search.
-- The full plain text of the document is stored ONLY on the first chunk
-- (chunk_index = 0): it is retrievable but never embedded or indexed.
--
-- Note: the vector dimension below (1024) matches Qwen/Qwen3-Embedding-0.6B.
-- If you change EMBEDDING_DIM, change the vector(...) size here too.

CREATE TABLE IF NOT EXISTS docs.documents (
    id          BIGSERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,   -- derived from the source filename; used for idempotent re-ingest
    title       TEXT NOT NULL,
    category    TEXT,
    source_url  TEXT,
    doc_date    DATE,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS docs.chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES docs.documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    heading_path TEXT,
    full_text    TEXT,                  -- populated only on chunk_index = 0; not indexed
    embedding    vector(1024),
    content_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('italian', content)) STORED,
    UNIQUE (document_id, chunk_index)
);

-- Vector ANN index (cosine). The query operator must be <=> to use it.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON docs.chunks USING hnsw (embedding vector_cosine_ops);

-- Lexical index over the Italian tsvector.
CREATE INDEX IF NOT EXISTS chunks_content_tsv_gin
    ON docs.chunks USING gin (content_tsv);
