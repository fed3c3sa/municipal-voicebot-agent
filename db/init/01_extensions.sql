-- Extensions and schemas. Runs first (file names are applied in order).
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector: vector(N) columns + ANN indexes
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- enables the appointment no-overlap exclusion constraint

CREATE SCHEMA IF NOT EXISTS docs;     -- municipal documents + retrieval chunks
CREATE SCHEMA IF NOT EXISTS booking;  -- appointments + cancellation log
