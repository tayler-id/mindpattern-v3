"""Tests for memory/identity_evolve.py — LLM-driven identity file evolution.

Uses a temporary directory so tests never touch the real vault at data/ramsay/mindpattern/.
"""

import json
import tempfile
from pathlib import Path

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


MINIMAL_SOUL = """\
# Soul

## Core Values

Signal over noise.

## Personality

Concise but thorough.
"""

MINIMAL_USER = """\
# User Profile

## Background

Senior engineer.

## Interests

AI agents, developer tools.
"""

MINIMAL_VOICE = """\
# Voice Guide

## Brand Voice

A builder sharing what caught their attention.

## Banned Words

delve, tapestry
"""

MINIMAL_DECISIONS = """\
## 2026-03-10

Decided to use atomic writes.

## 2026-03-12

Switched to parallel agent execution.

## 2026-03-14

Added voice fingerprint checks.
"""


@pytest.fixture
def vault_dir():
    """Create a fresh temporary directory seeded with minimal identity files."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "soul.md").write_text(MINIMAL_SOUL, encoding="utf-8")
        (root / "user.md").write_text(MINIMAL_USER, encoding="utf-8")
        (root / "voice.md").write_text(MINIMAL_VOICE, encoding="utf-8")
        (root / "decisions.md").write_text(MINIMAL_DECISIONS, encoding="utf-8")
        yield root


SAMPLE_PIPELINE_RESULTS = {
    "topic": "Claude 4 launch announcement",
    "gate1_outcome": "approved",
    "gate2_outcome": "approved",
    "corrections": ["Removed hedge phrase 'it should be noted'"],
    "expeditor_feedback": "Voice was slightly too formal in first draft.",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. build_evolve_prompt
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildEvolvePrompt:
    def test_returns_string(self, vault_dir):
        """build_evolve_prompt returns a non-empty string."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_includes_soul_content(self, vault_dir):
        """Prompt contains the current soul.md content."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "Signal over noise" in prompt

    def test_includes_user_content(self, vault_dir):
        """Prompt contains the current user.md content."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "Senior engineer" in prompt

    def test_includes_voice_content(self, vault_dir):
        """Prompt contains the current voice.md content."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "A builder sharing what caught their attention" in prompt

    def test_includes_recent_decisions(self, vault_dir):
        """Prompt contains recent entries from decisions.md."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "Added voice fingerprint checks" in prompt

    def test_includes_pipeline_results(self, vault_dir):
        """Prompt includes the pipeline results (topic, gate outcomes, etc.)."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "Claude 4 launch announcement" in prompt
        assert "approved" in prompt
        assert "Removed hedge phrase" in prompt

    def test_instructs_json_output(self, vault_dir):
        """Prompt instructs the LLM to output JSON."""
        from memory.identity_evolve import build_evolve_prompt

        prompt = build_evolve_prompt(vault_dir, SAMPLE_PIPELINE_RESULTS)
        assert "JSON" in prompt or "json" in prompt

    def test_handles_missing_files_gracefully(self):
        """build_evolve_prompt works even if some vault files are missing."""
        from memory.identity_evolve import build_evolve_prompt

        with tempfile.TemporaryDirectory() as d:
            empty_vault = Path(d)
            # Only create soul.md
            (empty_vault / "soul.md").write_text("# Soul\n", encoding="utf-8")

            prompt = build_evolve_prompt(empty_vault, SAMPLE_PIPELINE_RESULTS)
            assert isinstance(prompt, str)
            assert len(prompt) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. apply_evolution_diff
# ══════════════════════════════════════════════════════════════════════════════


class TestApplyEvolutionDiff:
    def test_update_modifies_section(self, vault_dir):
        """action='update' calls vault.update_section and modifies the file."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {
                "action": "update",
                "section": "Core Values",
                "content": "Updated values here.",
            }
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["changes_made"]) == 1
        assert len(result["errors"]) == 0
        text = (vault_dir / "soul.md").read_text(encoding="utf-8")
        assert "Updated values here." in text

    def test_append_adds_to_decisions(self, vault_dir):
        """action='append' appends a new dated entry to decisions.md."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "decisions": {
                "action": "append",
                "content": "New editorial decision recorded.",
            }
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["changes_made"]) == 1
        assert len(result["errors"]) == 0
        text = (vault_dir / "decisions.md").read_text(encoding="utf-8")
        assert "New editorial decision recorded." in text

    def test_action_none_makes_no_changes(self, vault_dir):
        """action='none' skips the file — no writes, no errors."""
        from memory.identity_evolve import apply_evolution_diff

        original_soul = (vault_dir / "soul.md").read_text(encoding="utf-8")

        diff = {
            "soul": {"action": "none"}
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["changes_made"]) == 0
        assert len(result["errors"]) == 0
        assert (vault_dir / "soul.md").read_text(encoding="utf-8") == original_soul

    def test_rejects_unknown_keys(self, vault_dir):
        """Unknown keys in the diff are rejected with an error."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {"action": "none"},
            "evil_file": {"action": "update", "section": "Hack", "content": "pwned"},
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1
        assert any("evil_file" in e for e in result["errors"])

    def test_oversized_content_rejected(self, vault_dir):
        """Content exceeding 500 chars is rejected with an error, not an exception."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {
                "action": "update",
                "section": "Core Values",
                "content": "x" * 501,
            }
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1
        assert any("500" in e or "too long" in e.lower() or "exceed" in e.lower()
                    for e in result["errors"])
        assert len(result["changes_made"]) == 0

    def test_malformed_input_returns_errors_not_exceptions(self, vault_dir):
        """Malformed diff input (missing action) returns errors, does not raise."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {"section": "Core Values", "content": "No action key."}
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1
        assert "changes_made" in result

    def test_append_only_for_decisions(self, vault_dir):
        """action='append' is only valid for decisions, rejected for other files."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {"action": "append", "content": "Should not work."}
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1

    def test_update_requires_section(self, vault_dir):
        """action='update' without a section key is an error."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {"action": "update", "content": "Missing section."}
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1

    def test_multiple_files_updated(self, vault_dir):
        """Multiple files can be updated in a single diff."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {
                "action": "update",
                "section": "Personality",
                "content": "Updated personality.",
            },
            "user": {
                "action": "update",
                "section": "Interests",
                "content": "Updated interests.",
            },
            "voice": {"action": "none"},
            "decisions": {
                "action": "append",
                "content": "Updated soul and user.",
            },
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["changes_made"]) == 3
        assert len(result["errors"]) == 0

    def test_invalid_action_value(self, vault_dir):
        """An unrecognized action value is reported as an error."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": {"action": "delete", "section": "Core Values"}
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1

    def test_non_dict_value_rejected(self, vault_dir):
        """A non-dict value in the diff is reported as an error."""
        from memory.identity_evolve import apply_evolution_diff

        diff = {
            "soul": "just a string"
        }

        result = apply_evolution_diff(vault_dir, diff)

        assert len(result["errors"]) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. parse_llm_output
# ══════════════════════════════════════════════════════════════════════════════


class TestParseLlmOutput:
    def test_parses_clean_json(self):
        """Parses clean JSON with no surrounding text."""
        from memory.identity_evolve import parse_llm_output

        raw = json.dumps({"soul": {"action": "none"}})
        result = parse_llm_output(raw)

        assert result == {"soul": {"action": "none"}}

    def test_extracts_from_markdown_code_fence(self):
        """Extracts JSON from markdown ```json ... ``` code fences."""
        from memory.identity_evolve import parse_llm_output

        raw = (
            "Here is my analysis:\n\n"
            "```json\n"
            '{"soul": {"action": "none"}, "user": {"action": "none"}}\n'
            "```\n\n"
            "That's my recommendation."
        )
        result = parse_llm_output(raw)

        assert result is not None
        assert result["soul"]["action"] == "none"
        assert result["user"]["action"] == "none"

    def test_extracts_from_bare_code_fence(self):
        """Extracts JSON from bare ``` ... ``` code fences (no json tag)."""
        from memory.identity_evolve import parse_llm_output

        raw = (
            "Some text\n"
            "```\n"
            '{"voice": {"action": "update", "section": "Brand Voice", "content": "New voice."}}\n'
            "```\n"
        )
        result = parse_llm_output(raw)

        assert result is not None
        assert result["voice"]["action"] == "update"

    def test_returns_none_for_garbage(self):
        """Returns None when input has no parseable JSON."""
        from memory.identity_evolve import parse_llm_output

        result = parse_llm_output("This is just random text with no JSON at all.")
        assert result is None

    def test_returns_none_for_empty_string(self):
        """Returns None for empty input."""
        from memory.identity_evolve import parse_llm_output

        result = parse_llm_output("")
        assert result is None

    def test_extracts_json_with_surrounding_text(self):
        """Extracts JSON even when embedded in prose (no code fence)."""
        from memory.identity_evolve import parse_llm_output

        raw = (
            "After reviewing, here is the diff:\n"
            '{"decisions": {"action": "append", "content": "Noted."}}\n'
            "Let me know if you want changes."
        )
        result = parse_llm_output(raw)

        assert result is not None
        assert result["decisions"]["action"] == "append"

    def test_handles_multiline_json(self):
        """Handles pretty-printed multiline JSON inside a code fence."""
        from memory.identity_evolve import parse_llm_output

        inner = json.dumps(
            {
                "soul": {"action": "update", "section": "Personality", "content": "New."},
                "user": {"action": "none"},
                "voice": {"action": "none"},
                "decisions": {"action": "append", "content": "Updated personality."},
            },
            indent=2,
        )
        raw = f"```json\n{inner}\n```"
        result = parse_llm_output(raw)

        assert result is not None
        assert result["soul"]["action"] == "update"
        assert result["decisions"]["content"] == "Updated personality."
