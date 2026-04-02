# memory/embeddings.py

## Purpose
Embedding model management and vector operations for similarity search and dedup.

## API
- `embed_text(text) -> list[float]` — Single text embedding (requires fastembed)
- `embed_texts(texts) -> list[list[float]]` — Batch embeddings (requires fastembed)
- `cosine_similarity(a, b) -> float` — Cosine similarity, handles zero vectors safely
- `dot_similarity(a, b) -> float` — Raw dot product (fast path for normalized vectors)
- `serialize_f32(vector) -> bytes` — Pack float vector to SQLite BLOB
- `deserialize_f32(blob) -> list[float]` — Unpack BLOB to float vector
- `batch_similarities(query, embeddings, threshold?) -> list[tuple[int, float]]` — Compute similarities against serialized blobs, filter by threshold, sort descending

## Test Coverage
- `tests/test_embeddings.py` — 15 tests covering all pure math functions
- Tests do NOT import embed_text/embed_texts (require fastembed model download)

## Known Issues
- Thread safety: module-level `_model` singleton not thread-safe for concurrent imports
- `batch_similarities` uses dot product (not cosine), assumes normalized vectors

## Last Updated
2026-04-02 — convention fix: `Optional[float]` → `float | None` (line 76)
