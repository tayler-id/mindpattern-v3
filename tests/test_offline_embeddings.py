"""The deterministic embedding double in tests/conftest.py.

It replaces the fastembed model for tests that run real clustering and
similarity code, so its geometry is load-bearing: topical texts must sit
above the thresholds those modules use, unrelated texts below them.
"""

import numpy as np

from tests.conftest import deterministic_embedding
from memory.embeddings import EMBEDDING_DIM, embed_text, embed_texts
from preflight.trends import CLUSTER_SIMILARITY
from memory.trends import TREND_MATCH_THRESHOLD


def test_vectors_are_unit_length_at_model_dimension():
    vec = deterministic_embedding("Claude Code becomes #1 AI coding assistant")
    assert vec.shape == (EMBEDDING_DIM,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_same_text_gives_the_same_vector():
    a = deterministic_embedding("GPT-5 benchmarks leaked")
    b = deterministic_embedding("GPT-5 benchmarks leaked")
    assert np.array_equal(a, b)


def test_empty_text_still_embeds():
    vec = deterministic_embedding("")
    assert vec.shape == (EMBEDDING_DIM,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5


def test_texts_about_one_subject_cluster_together():
    a = deterministic_embedding(
        "Claude Code becomes #1 AI coding assistant. Claude Code overtakes Copilot"
    )
    b = deterministic_embedding(
        "Claude Code review: the best AI coding tool. After 3 months with Claude Code"
    )
    assert float(a @ b) >= CLUSTER_SIMILARITY


def test_a_trend_topic_matches_a_finding_about_it():
    topic = deterministic_embedding("Claude Code launch")
    finding = deterministic_embedding(
        "Claude Code becomes the top AI coding tool. Claude Code overtook GitHub Copilot"
    )
    assert float(topic @ finding) >= TREND_MATCH_THRESHOLD


def test_unrelated_texts_stay_apart():
    a = deterministic_embedding("Claude Code becomes #1 AI coding assistant")
    b = deterministic_embedding("A novel approach to transformer quantization")
    assert float(a @ b) < 0.5


def test_fixture_serves_the_module_entry_points(offline_embeddings):
    single = embed_text("Claude Code launch")
    batch = embed_texts(["Claude Code launch", "GPT-5 benchmarks leaked"])
    assert len(single) == EMBEDDING_DIM
    assert batch[0] == single
    assert len(batch) == 2
