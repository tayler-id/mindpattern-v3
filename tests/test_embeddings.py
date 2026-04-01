"""Tests for memory/embeddings.py pure math functions.

Tests cosine_similarity, dot_similarity, serialize/deserialize round-trip,
and batch_similarities (used for dedup filtering throughout the pipeline).
No model loading — fastembed is never imported.
"""

import math
import struct

import numpy as np
import pytest

from memory.embeddings import (
    batch_similarities,
    cosine_similarity,
    deserialize_f32,
    dot_similarity,
    serialize_f32,
)


# ── cosine_similarity ───────────────────────────────────────────────────


def test_cosine_similarity_identical_vectors():
    """Identical normalized vectors should have similarity ~1.0."""
    vec = [1.0, 0.0, 0.0]
    assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_identical_non_unit_vectors():
    """Identical non-unit vectors should still have similarity ~1.0."""
    vec = [3.0, 4.0, 0.0]
    assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal_vectors():
    """Orthogonal vectors should have similarity 0.0."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_opposite_vectors():
    """Opposite vectors should have similarity -1.0."""
    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_similarity_zero_vector_returns_zero():
    """A zero vector should produce similarity 0.0 (not NaN/error)."""
    zero = [0.0, 0.0, 0.0]
    nonzero = [1.0, 2.0, 3.0]
    assert cosine_similarity(zero, nonzero) == 0.0
    assert cosine_similarity(nonzero, zero) == 0.0
    assert cosine_similarity(zero, zero) == 0.0


def test_cosine_similarity_known_angle():
    """45-degree angle vectors should have similarity cos(pi/4) ~ 0.7071."""
    a = [1.0, 0.0]
    b = [1.0, 1.0]
    expected = math.cos(math.pi / 4)
    assert cosine_similarity(a, b) == pytest.approx(expected, abs=1e-4)


# ── dot_similarity ──────────────────────────────────────────────────────


def test_dot_similarity_unit_vectors():
    """Dot product of orthogonal unit vectors is 0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert dot_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_dot_similarity_scaled():
    """Dot product of [3,4] . [3,4] = 25."""
    v = [3.0, 4.0]
    assert dot_similarity(v, v) == pytest.approx(25.0, abs=1e-4)


# ── serialize / deserialize round-trip ──────────────────────────────────


def test_serialize_deserialize_roundtrip():
    """Serializing then deserializing should return the original vector."""
    original = [0.1, 0.2, 0.3, -0.5, 1.0]
    blob = serialize_f32(original)
    recovered = deserialize_f32(blob)
    assert len(recovered) == len(original)
    for a, b in zip(original, recovered):
        assert a == pytest.approx(b, abs=1e-6)


def test_serialize_produces_correct_byte_length():
    """Each float32 is 4 bytes, so N floats -> 4*N bytes."""
    vec = [0.0] * 384
    blob = serialize_f32(vec)
    assert len(blob) == 384 * 4


# ── batch_similarities (dedup logic) ────────────────────────────────────


def _make_blob(vec: list[float]) -> bytes:
    """Helper: serialize a float vector to the format batch_similarities expects."""
    return serialize_f32(vec)


def test_batch_dedup_removes_similar_items():
    """Items above the similarity threshold should be returned (i.e. flagged as dupes).

    batch_similarities returns all (index, sim) pairs above threshold.
    A dedup pass would remove items whose sim >= threshold vs an existing item.
    """
    # Two nearly identical vectors (should be "duplicates")
    query = [1.0, 0.0, 0.0]
    candidate_similar = [0.99, 0.1, 0.0]  # very close to query
    candidate_different = [0.0, 0.0, 1.0]  # orthogonal

    blobs = [_make_blob(candidate_similar), _make_blob(candidate_different)]
    results = batch_similarities(query, blobs, threshold=0.9)

    # Only the similar candidate should pass the threshold
    returned_indices = {idx for idx, _ in results}
    assert 0 in returned_indices, "Similar item should exceed threshold"
    assert 1 not in returned_indices, "Dissimilar item should be below threshold"


def test_batch_dedup_keeps_dissimilar_items():
    """When all candidates are dissimilar to the query, none should exceed threshold."""
    query = [1.0, 0.0, 0.0]
    candidates = [
        [0.0, 1.0, 0.0],  # orthogonal
        [0.0, 0.0, 1.0],  # orthogonal
        [-1.0, 0.0, 0.0],  # opposite
    ]
    blobs = [_make_blob(c) for c in candidates]
    results = batch_similarities(query, blobs, threshold=0.5)

    assert len(results) == 0, "No dissimilar items should pass threshold=0.5"


def test_batch_similarities_no_threshold_returns_all():
    """With no threshold, all candidates should be returned."""
    query = [1.0, 0.0]
    candidates = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    blobs = [_make_blob(c) for c in candidates]
    results = batch_similarities(query, blobs, threshold=None)

    assert len(results) == 3


def test_batch_similarities_sorted_descending():
    """Results should be sorted by similarity, highest first."""
    query = [1.0, 0.0, 0.0]
    candidates = [
        [0.0, 0.0, 1.0],   # sim ~ 0
        [1.0, 0.0, 0.0],   # sim ~ 1
        [0.5, 0.5, 0.0],   # sim ~ 0.5 (not normalized, dot product)
    ]
    blobs = [_make_blob(c) for c in candidates]
    results = batch_similarities(query, blobs, threshold=None)

    sims = [sim for _, sim in results]
    assert sims == sorted(sims, reverse=True), "Results should be descending by similarity"


def test_batch_similarities_empty_embeddings():
    """An empty embeddings list should return an empty result."""
    query = [1.0, 0.0, 0.0]
    results = batch_similarities(query, [], threshold=None)
    assert results == []
