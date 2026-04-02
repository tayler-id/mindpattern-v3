"""Embedding model management and vector operations.

Loads BAAI/bge-small-en-v1.5 (384-dim) ONCE at module import time.
All vectors are normalized by the model, so cosine similarity = dot product.
"""

import os
import struct
from pathlib import Path

import numpy as np

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
FASTEMBED_CACHE_ENV = "FASTEMBED_CACHE_DIR"
DEFAULT_FASTEMBED_CACHE_DIR = Path.home() / ".cache" / "mindpattern" / "fastembed"

# Persist fastembed's ONNX cache outside /var/folders (macOS purges tmp dirs,
# which leaves dangling symlinks and silently breaks the RESEARCH phase).
FASTEMBED_CACHE_DIR = str(DEFAULT_FASTEMBED_CACHE_DIR)

# Module-level singleton — loads once on first import
_model = None


def resolve_fastembed_cache_dir() -> Path:
    """Return the persistent fastembed cache directory."""
    return Path(os.environ.get(FASTEMBED_CACHE_ENV, FASTEMBED_CACHE_DIR)).expanduser()


def create_text_embedding():
    """Create the fastembed TextEmbedding model with the project cache path."""
    from fastembed import TextEmbedding

    cache_dir = resolve_fastembed_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(cache_dir))


def _get_model():
    """Get or initialize the embedding model singleton."""
    global _model
    if _model is None:
        _model = create_text_embedding()
    return _model


def embed_text(text: str) -> list[float]:
    """Generate a 384-dim embedding for the given text."""
    model = _get_model()
    return list(model.embed([text]))[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-generate embeddings for multiple texts."""
    if not texts:
        return []
    model = _get_model()
    return [e.tolist() for e in model.embed(texts)]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    bge-small embeddings are L2-normalized, so this is equivalent to dot product.
    We still normalize defensively in case of edge cases.
    """
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def dot_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Dot product similarity (fast path for normalized vectors)."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    return float(np.dot(a, b))


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float vector to bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_f32(blob: bytes) -> list[float]:
    """Deserialize bytes back to a float vector."""
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def batch_similarities(
    query_vec: list[float],
    embeddings: list[bytes],
    threshold: float | None = None,
) -> list[tuple[int, float]]:
    """Compute similarities between a query vector and a list of serialized embeddings.

    Returns list of (index, similarity) tuples, optionally filtered by threshold.
    Sorted by similarity descending.
    """
    q = np.array(query_vec, dtype=np.float32)
    results = []
    for i, blob in enumerate(embeddings):
        emb = np.array(deserialize_f32(blob), dtype=np.float32)
        sim = float(np.dot(q, emb))
        if threshold is None or sim >= threshold:
            results.append((i, sim))
    results.sort(key=lambda x: -x[1])
    return results
