"""Tests for the humanizer agent upgrade — file existence and integration."""

from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ── Agent file tests ─────────────────────────────────────────────────


def test_humanizer_agent_file_exists():
    p = PROJECT_ROOT / "agents" / "humanizer.md"
    assert p.exists(), "agents/humanizer.md must exist"
    content = p.read_text()
    assert "Two-Pass Process" in content
    assert "AI Writing Patterns" in content


def test_humanizer_references_exist():
    p = PROJECT_ROOT / "agents" / "references" / "ai-writing-patterns.md"
    assert p.exists(), "agents/references/ai-writing-patterns.md must exist"
    content = p.read_text()
    assert "Inflated significance" in content
    assert "BEFORE:" in content
    assert "AFTER:" in content


def test_humanizer_agent_has_all_pattern_categories():
    content = (PROJECT_ROOT / "agents" / "humanizer.md").read_text()
    for category in [
        "Content Patterns",
        "Language Patterns",
        "Style Patterns",
        "Communication Artifacts",
        "Filler and Hedging",
    ]:
        assert category in content, f"Missing pattern category: {category}"


def test_humanizer_agent_no_voice_guide_placeholder():
    """The agent file should NOT have a {voice_guide} placeholder — voice is
    inlined in the prompt, not in the system prompt file."""
    content = (PROJECT_ROOT / "agents" / "humanizer.md").read_text()
    assert "{voice_guide}" not in content


# ── Function integration tests ───────────────────────────────────────


def test_humanize_loads_voice_guide():
    """_humanize() should include voice guide content in the prompt."""
    from social.writers import _humanize

    with patch("social.writers.run_claude_prompt") as mock_run:
        mock_run.return_value = ("Cleaned output", 0)
        _humanize("Test draft", "bluesky")

        call_args = mock_run.call_args
        prompt = call_args[0][0]  # first positional arg
        assert "Voice Guide (AUTHORITATIVE" in prompt
        assert "Banned Words" in prompt  # from voice.md


def test_humanize_uses_system_prompt_file():
    """_humanize() should pass agents/humanizer.md as system_prompt_file."""
    from social.writers import _humanize

    with patch("social.writers.run_claude_prompt") as mock_run:
        mock_run.return_value = ("Cleaned output", 0)
        _humanize("Test draft", "linkedin")

        call_args = mock_run.call_args
        assert call_args[1]["system_prompt_file"] == "agents/humanizer.md"


def test_humanize_returns_original_on_failure():
    """On non-zero exit code, return the original content unchanged."""
    from social.writers import _humanize

    with patch("social.writers.run_claude_prompt") as mock_run:
        mock_run.return_value = ("", 1)
        result = _humanize("Original draft", "bluesky")
        assert result == "Original draft"


def test_humanize_returns_original_on_empty_output():
    """On empty output, return the original content unchanged."""
    from social.writers import _humanize

    with patch("social.writers.run_claude_prompt") as mock_run:
        mock_run.return_value = ("", 0)
        result = _humanize("Original draft", "bluesky")
        assert result == "Original draft"
