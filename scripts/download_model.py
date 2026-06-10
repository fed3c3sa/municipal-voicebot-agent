"""Optional helper: pre-download the embedding model into ./models.

The embedder container also downloads the model automatically on first boot,
so this script is just a convenience to warm the cache ahead of time.

Usage (needs `pip install huggingface_hub` on the host):
    python scripts/download_model.py
"""

from __future__ import annotations

import os

from huggingface_hub import snapshot_download

MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")
# Matches the container layout: HF_HOME=/models -> cache under /models/hub.
CACHE_DIR = os.path.join(os.environ.get("MODELS_DIR", "./models"), "hub")


def main() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    print(f"Downloading {MODEL_NAME} into {CACHE_DIR} ...")
    path = snapshot_download(repo_id=MODEL_NAME, cache_dir=CACHE_DIR)
    print(f"Done. Model files at: {path}")


if __name__ == "__main__":
    main()
