"""Tests for the session capture hook (hooks/session-capture.py).

No network, no API keys. Tests transcript parsing, extraction, and page writing.
"""

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TRANSCRIPT = [
    {
        "type": "user",
        "timestamp": "2026-04-06T14:00:00Z",
        "message": {
            "content": "Build the knowledge compiler for the second brain"
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-06T14:00:30Z",
        "message": {
            "content": [
                {
                    "type": "thinking",
                    "thinking": "I need to create knowledge/compile.py that reads findings from SQLite and clusters them.",
                },
                {
                    "type": "text",
                    "text": "I'll start by creating the test file first, then build the implementation.",
                },
                {
                    "type": "tool_use",
                    "name": "Write",
                    "input": {"file_path": "/project/tests/test_compile.py"},
                },
            ]
        },
    },
    {
        "type": "user",
        "timestamp": "2026-04-06T14:01:00Z",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": "File created successfully",
                }
            ]
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-06T14:02:00Z",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "Now let me create the compiler module. I decided to use greedy single-linkage clustering (same pattern as preflight/trends.py) because it's fast and proven in this codebase.",
                },
                {
                    "type": "tool_use",
                    "name": "Write",
                    "input": {"file_path": "/project/knowledge/compile.py"},
                },
            ]
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-06T14:05:00Z",
        "message": {
            "content": "All 18 tests passing. The knowledge compiler is ready.",
        },
    },
]


@pytest.fixture
def transcript_file(tmp_path):
    """Write sample transcript to a JSONL file."""
    path = tmp_path / "transcript.jsonl"
    with open(path, "w") as f:
        for msg in SAMPLE_TRANSCRIPT:
            f.write(json.dumps(msg) + "\n")
    return path


@pytest.fixture
def knowledge_dir(tmp_path):
    """Temporary knowledge directory with sessions/ subdirectory."""
    sessions_dir = tmp_path / "knowledge" / "sessions"
    sessions_dir.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: parse_transcript
# ---------------------------------------------------------------------------

class TestParseTranscript:

    def test_parses_jsonl_file(self, transcript_file):
        from hooks.session_capture import parse_transcript
        messages = parse_transcript(str(transcript_file))
        assert len(messages) == 5

    def test_missing_file_returns_empty(self, tmp_path):
        from hooks.session_capture import parse_transcript
        assert parse_transcript(str(tmp_path / "nope.jsonl")) == []

    def test_handles_malformed_lines(self, tmp_path):
        from hooks.session_capture import parse_transcript
        path = tmp_path / "bad.jsonl"
        path.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
        messages = parse_transcript(str(path))
        assert len(messages) == 2


# ---------------------------------------------------------------------------
# Tests: extract_session_data
# ---------------------------------------------------------------------------

class TestExtractSessionData:

    def test_extracts_user_messages(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        assert len(data["user_messages"]) >= 1
        assert "knowledge compiler" in data["user_messages"][0].lower()

    def test_extracts_decisions(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        # Should find "decided" in assistant text
        assert len(data["decisions"]) >= 1
        assert any("clustering" in d.lower() for d in data["decisions"])

    def test_extracts_files_modified(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        assert "test_compile.py" in str(data["files_touched"])
        assert "compile.py" in str(data["files_touched"])

    def test_computes_duration(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        assert data["duration"] == "5m 0s"

    def test_extracts_tool_counts(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        assert data["tool_counts"]["Write"] == 2

    def test_handles_empty_transcript(self):
        from hooks.session_capture import extract_session_data
        data = extract_session_data([])
        assert data["user_messages"] == []
        assert data["decisions"] == []
        assert data["files_touched"] == []
        assert data["duration"] == ""


# ---------------------------------------------------------------------------
# Tests: format_session_page
# ---------------------------------------------------------------------------

class TestFormatSessionPage:

    def test_generates_valid_markdown(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data, format_session_page
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        assert "type: session" in markdown
        assert "## What Was Done" in markdown
        assert "## Decisions" in markdown
        assert "## Files Touched" in markdown

    def test_includes_frontmatter(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data, format_session_page
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        assert "date: 2026-04-06" in markdown
        assert "duration:" in markdown

    def test_slug_in_title(self, transcript_file):
        from hooks.session_capture import parse_transcript, extract_session_data, format_session_page
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        # Title should be derived from user's first message
        assert "# Session" in markdown


# ---------------------------------------------------------------------------
# Tests: write_session_file
# ---------------------------------------------------------------------------

class TestWriteSessionFile:

    def test_writes_to_sessions_dir(self, knowledge_dir, transcript_file):
        from hooks.session_capture import (
            parse_transcript, extract_session_data,
            format_session_page, write_session_file,
        )
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        sessions_dir = knowledge_dir / "knowledge" / "sessions"
        path = write_session_file(sessions_dir, markdown, "2026-04-06", "knowledge-compiler")

        assert path.exists()
        assert "2026-04-06" in path.name
        assert "knowledge-compiler" in path.name
        content = path.read_text()
        assert "type: session" in content

    def test_creates_sessions_dir_if_missing(self, tmp_path, transcript_file):
        from hooks.session_capture import (
            parse_transcript, extract_session_data,
            format_session_page, write_session_file,
        )
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        sessions_dir = tmp_path / "knowledge" / "sessions"
        # Dir doesn't exist yet
        assert not sessions_dir.exists()

        path = write_session_file(sessions_dir, markdown, "2026-04-06", "test")
        assert path.exists()
        assert sessions_dir.exists()

    def test_no_overwrite_existing(self, knowledge_dir, transcript_file):
        from hooks.session_capture import (
            parse_transcript, extract_session_data,
            format_session_page, write_session_file,
        )
        messages = parse_transcript(str(transcript_file))
        data = extract_session_data(messages)
        markdown = format_session_page(data, "2026-04-06")

        sessions_dir = knowledge_dir / "knowledge" / "sessions"
        path1 = write_session_file(sessions_dir, markdown, "2026-04-06", "test")
        path2 = write_session_file(sessions_dir, markdown, "2026-04-06", "test")
        # Should create a second file with unique name, not overwrite
        assert path1.exists()
        assert path2.exists()
        assert path1 != path2


# ---------------------------------------------------------------------------
# Tests: infer_session_title
# ---------------------------------------------------------------------------

class TestInferSessionTitle:

    def test_infers_from_first_user_message(self):
        from hooks.session_capture import infer_session_title
        messages = ["Build the knowledge compiler for the second brain"]
        assert "knowledge" in infer_session_title(messages).lower()

    def test_handles_empty_messages(self):
        from hooks.session_capture import infer_session_title
        title = infer_session_title([])
        assert title  # Should return some default

    def test_truncates_long_titles(self):
        from hooks.session_capture import infer_session_title
        messages = ["A" * 500]
        title = infer_session_title(messages)
        assert len(title) <= 80
