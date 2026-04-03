"""Tests for social/writers.py — draft orchestration via Writer→Critic loop.

Covers:
- write_drafts() returns per-platform results with expected keys
- write_drafts(platforms=[...]) filters to only requested platforms
- A failure on one platform does not abort the other
- _load_voice_guide() returns empty string when file is missing
"""

from unittest.mock import MagicMock, patch

import pytest

import social.writers as writers_module
from social.writers import write_drafts, _load_voice_guide


# ── Helpers ────────────────────────────────────────────────────────────────

RESULT_KEYS = {"content", "iterations", "critic_verdict", "policy_errors",
               "humanized", "error"}

SAMPLE_BRIEF = {
    "anchor": "Test anchor",
    "reaction": "Test reaction",
    "confidence": "high",
    "do_not_include": [],
}

SAMPLE_CONFIG = {
    "social": {"max_iterations": 1, "max_writer_workers": 2},
}


@pytest.fixture(autouse=True)
def _reset_voice_cache():
    """Reset the module-level _VOICE_GUIDE cache between tests."""
    writers_module._VOICE_GUIDE = None
    yield
    writers_module._VOICE_GUIDE = None


def _make_patches():
    """Return the standard set of patches for write_drafts tests.

    Mocks:
    - run_agent_with_files → returns a dict with 'text' key
    - run_claude_prompt → returns (cleaned_text, 0) for humanizer
    - review_draft → returns APPROVED on first pass
    - deterministic_validate → returns no errors
    - memory.get_db → returns a MagicMock db
    """
    mock_run_agent = patch(
        "social.writers.run_agent_with_files",
        return_value={"text": "Draft content here"},
    )
    mock_run_prompt = patch(
        "social.writers.run_claude_prompt",
        return_value=("Humanized content", 0),
    )
    mock_review = patch(
        "social.critics.review_draft",
        return_value={"verdict": "APPROVED", "feedback": "", "scores": {}},
    )
    mock_policy = patch(
        "social.critics.deterministic_validate",
        return_value=[],
    )
    mock_db = patch("memory.get_db", return_value=MagicMock())
    mock_voice = patch.object(
        writers_module, "_load_voice_guide", return_value="voice guide text"
    )
    return mock_run_agent, mock_run_prompt, mock_review, mock_policy, mock_db, mock_voice


# ── Tests ──────────────────────────────────────────────────────────────────


def test_write_drafts_returns_per_platform_results():
    """write_drafts() returns a dict keyed by platform with correct shape."""
    patches = _make_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        results = write_drafts(
            db=MagicMock(),
            brief=SAMPLE_BRIEF,
            config=SAMPLE_CONFIG,
        )

    # Both default platforms present
    assert "bluesky" in results
    assert "linkedin" in results

    # Each result has the expected keys
    for platform in ("bluesky", "linkedin"):
        assert set(results[platform].keys()) == RESULT_KEYS
        assert results[platform]["error"] is None
        assert results[platform]["critic_verdict"] == "APPROVED"


def test_write_drafts_platform_filter_limits_output():
    """write_drafts(platforms=['bluesky']) only produces a bluesky result."""
    patches = _make_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        results = write_drafts(
            db=MagicMock(),
            brief=SAMPLE_BRIEF,
            config=SAMPLE_CONFIG,
            platforms=["bluesky"],
        )

    assert "bluesky" in results
    assert "linkedin" not in results
    assert set(results["bluesky"].keys()) == RESULT_KEYS


def test_write_drafts_single_platform_failure_isolated():
    """If one platform's writer raises, the other platform still succeeds."""
    call_count = {"n": 0}

    def _side_effect(*args, **kwargs):
        call_count["n"] += 1
        # Fail for the first call (one platform), succeed for the second
        if call_count["n"] <= 1:
            raise RuntimeError("Simulated writer crash")
        return {"text": "Good draft"}

    mock_run_agent = patch(
        "social.writers.run_agent_with_files",
        side_effect=_side_effect,
    )
    mock_run_prompt = patch(
        "social.writers.run_claude_prompt",
        return_value=("Humanized content", 0),
    )
    mock_review = patch(
        "social.critics.review_draft",
        return_value={"verdict": "APPROVED", "feedback": "", "scores": {}},
    )
    mock_policy = patch(
        "social.critics.deterministic_validate",
        return_value=[],
    )
    mock_db = patch("memory.get_db", return_value=MagicMock())
    mock_voice = patch.object(
        writers_module, "_load_voice_guide", return_value="voice guide text"
    )

    with mock_run_agent, mock_run_prompt, mock_review, mock_policy, mock_db, mock_voice:
        results = write_drafts(
            db=MagicMock(),
            brief=SAMPLE_BRIEF,
            config=SAMPLE_CONFIG,
            platforms=["bluesky", "linkedin"],
        )

    # Both platforms present in results
    assert "bluesky" in results
    assert "linkedin" in results

    # One succeeded, one failed — order is nondeterministic with threads
    errors = [p for p in results if results[p].get("error")]
    successes = [p for p in results if not results[p].get("error")]

    assert len(errors) == 1, "Exactly one platform should have failed"
    assert len(successes) == 1, "Exactly one platform should have succeeded"

    failed = results[errors[0]]
    assert failed["critic_verdict"] == "ERROR"
    assert failed["content"] == ""
    assert "Simulated writer crash" in failed["error"]

    ok = results[successes[0]]
    assert ok["error"] is None
    assert ok["critic_verdict"] == "APPROVED"


def test_load_voice_guide_returns_empty_string_when_missing():
    """_load_voice_guide() returns '' when voice.md does not exist."""
    with patch.object(writers_module, "_VOICE_GUIDE_PATH") as mock_path:
        mock_path.exists.return_value = False
        result = _load_voice_guide()

    assert result == ""
