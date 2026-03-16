"""Tests for hooks/session-transcript.py — agent transcript capture hook.

Tests the transcript parsing, log extraction, markdown formatting, and
atomic write functions independently of Claude Code's hook infrastructure.
"""

import json
import tempfile
from pathlib import Path

import pytest

# Import hook functions directly
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from importlib import import_module

# Import the module by path since it has a hyphen
import importlib.util
_hook_spec = importlib.util.spec_from_file_location(
    "session_transcript",
    Path(__file__).parent.parent / "hooks" / "session-transcript.py",
)
hook = importlib.util.module_from_spec(_hook_spec)
_hook_spec.loader.exec_module(hook)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def vault_dir(tmp_path):
    """Temporary vault directory."""
    return tmp_path / "vault"


@pytest.fixture
def sample_transcript(tmp_path):
    """Write a sample JSONL transcript and return its path."""
    lines = [
        {
            "type": "user",
            "timestamp": "2026-03-15T07:00:00Z",
            "message": {
                "content": "Search for the latest AI safety research papers published this week."
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-03-15T07:00:05Z",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "I'll search for recent AI safety papers across multiple sources.",
                    },
                    {
                        "type": "tool_use",
                        "name": "WebSearch",
                        "input": {"query": "AI safety research papers 2026"},
                    },
                ]
            },
        },
        {
            "type": "assistant",
            "timestamp": "2026-03-15T07:01:30Z",
            "message": {
                "content": "Found 3 relevant papers from this week. The most significant is a new alignment technique from Anthropic.",
            },
        },
    ]
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        "\n".join(json.dumps(line) for line in lines),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def empty_transcript(tmp_path):
    """Empty JSONL transcript."""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    return str(path)


@pytest.fixture
def system_message_transcript(tmp_path):
    """Transcript with only system/internal messages (should be filtered)."""
    lines = [
        {
            "type": "user",
            "timestamp": "2026-03-15T07:00:00Z",
            "message": {
                "content": "<system-reminder>This is a system message</system-reminder>"
            },
        },
        {
            "type": "user",
            "timestamp": "2026-03-15T07:00:01Z",
            "message": {
                "content": "<teammate-message from='agent'>Status update</teammate-message>"
            },
        },
    ]
    path = tmp_path / "system.jsonl"
    path.write_text(
        "\n".join(json.dumps(line) for line in lines),
        encoding="utf-8",
    )
    return str(path)


# ══════════════════════════════════════════════════════════════════════════════
# 1. parse_transcript
# ══════════════════════════════════════════════════════════════════════════════


class TestParseTranscript:
    def test_parses_valid_jsonl(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        assert len(messages) == 3

    def test_returns_empty_for_missing_file(self):
        messages = hook.parse_transcript("/nonexistent/path.jsonl")
        assert messages == []

    def test_returns_empty_for_empty_file(self, empty_transcript):
        messages = hook.parse_transcript(empty_transcript)
        assert messages == []

    def test_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"valid": true}\nnot json\n{"also": "valid"}\n')
        messages = hook.parse_transcript(str(path))
        assert len(messages) == 2

    def test_preserves_message_types(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        types = [m["type"] for m in messages]
        assert types == ["user", "assistant", "assistant"]


# ══════════════════════════════════════════════════════════════════════════════
# 2. extract_agent_log
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractAgentLog:
    def test_extracts_user_prompts(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        log = hook.extract_agent_log(messages)
        assert len(log["user_prompts"]) == 1
        assert "AI safety research" in log["user_prompts"][0]

    def test_extracts_reasoning(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        log = hook.extract_agent_log(messages)
        assert len(log["reasoning"]) >= 1
        assert any("alignment" in r for r in log["reasoning"])

    def test_extracts_tool_calls(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        log = hook.extract_agent_log(messages)
        assert len(log["tool_calls"]) == 1
        assert log["tool_calls"][0]["tool"] == "WebSearch"

    def test_calculates_duration(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        log = hook.extract_agent_log(messages)
        assert log["duration"] == "1m 30s"

    def test_filters_system_messages(self, system_message_transcript):
        messages = hook.parse_transcript(system_message_transcript)
        log = hook.extract_agent_log(messages)
        assert len(log["user_prompts"]) == 0

    def test_handles_empty_messages(self):
        log = hook.extract_agent_log([])
        assert log["reasoning"] == []
        assert log["tool_calls"] == []
        assert log["user_prompts"] == []
        assert log["duration"] == ""

    def test_handles_string_content_assistant(self, sample_transcript):
        messages = hook.parse_transcript(sample_transcript)
        log = hook.extract_agent_log(messages)
        # The third message has string content
        assert any("3 relevant papers" in r for r in log["reasoning"])

    def test_handles_list_content_user(self, tmp_path):
        """User message with list content (array of blocks)."""
        lines = [
            {
                "type": "user",
                "timestamp": "2026-03-15T07:00:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Search for papers on alignment"},
                    ]
                },
            },
        ]
        path = tmp_path / "list_user.jsonl"
        path.write_text(json.dumps(lines[0]))
        messages = hook.parse_transcript(str(path))
        log = hook.extract_agent_log(messages)
        assert len(log["user_prompts"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. format_agent_log
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatAgentLog:
    def test_has_yaml_frontmatter(self):
        log_data = {
            "reasoning": ["Decided to search arxiv first"],
            "tool_calls": [{"tool": "WebSearch", "input_preview": '{"q": "..."}'}],
            "user_prompts": ["Search for papers"],
            "duration": "2m 30s",
        }
        md = hook.format_agent_log("news-researcher", "2026-03-15", log_data)
        assert md.startswith("---\n")
        assert "type: agent-log" in md
        assert "agent: news-researcher" in md
        assert "date: 2026-03-15" in md

    def test_contains_daily_link(self):
        log_data = {
            "reasoning": [],
            "tool_calls": [],
            "user_prompts": [],
            "duration": "",
        }
        md = hook.format_agent_log("eic", "2026-03-15", log_data)
        assert "[[daily/2026-03-15]]" in md

    def test_contains_tool_calls_section(self):
        log_data = {
            "reasoning": [],
            "tool_calls": [
                {"tool": "WebSearch", "input_preview": '{"q": "test"}'},
                {"tool": "Read", "input_preview": '{"path": "/foo"}'},
            ],
            "user_prompts": [],
            "duration": "1m 0s",
        }
        md = hook.format_agent_log("researcher", "2026-03-15", log_data)
        assert "## Tool Calls" in md
        assert "**WebSearch**" in md
        assert "**Read**" in md

    def test_contains_output_section(self):
        log_data = {
            "reasoning": ["This is important because it shows a new trend"],
            "tool_calls": [],
            "user_prompts": [],
            "duration": "",
        }
        md = hook.format_agent_log("researcher", "2026-03-15", log_data)
        assert "## Output" in md
        assert "important because" in md

    def test_truncates_long_reasoning(self):
        log_data = {
            "reasoning": ["x" * 2000],
            "tool_calls": [],
            "user_prompts": [],
            "duration": "",
        }
        md = hook.format_agent_log("researcher", "2026-03-15", log_data)
        assert "..." in md
        # Should be truncated to ~1000 chars
        assert "x" * 1001 not in md

    def test_no_tool_calls_section_when_empty(self):
        log_data = {
            "reasoning": ["Some reasoning"],
            "tool_calls": [],
            "user_prompts": [],
            "duration": "",
        }
        md = hook.format_agent_log("researcher", "2026-03-15", log_data)
        assert "## Tool Calls" not in md


# ══════════════════════════════════════════════════════════════════════════════
# 4. atomic_write
# ══════════════════════════════════════════════════════════════════════════════


class TestHookAtomicWrite:
    def test_creates_file_and_parents(self, vault_dir):
        target = vault_dir / "agents" / "news" / "2026-03-15.md"
        hook.atomic_write(target, "# Hello\n")
        assert target.exists()
        assert target.read_text() == "# Hello\n"

    def test_normalizes_line_endings(self, vault_dir):
        target = vault_dir / "test.md"
        hook.atomic_write(target, "line1\r\nline2\rline3\n")
        assert "\r" not in target.read_text()

    def test_overwrites_existing(self, vault_dir):
        target = vault_dir / "test.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old content")
        hook.atomic_write(target, "new content")
        assert target.read_text() == "new content"

    def test_no_tmp_file_left(self, vault_dir):
        target = vault_dir / "test.md"
        hook.atomic_write(target, "content")
        tmp = target.with_suffix(".md.tmp")
        assert not tmp.exists()


# ══════════════════════════════════════════════════════════════════════════════
# 5. _truncate
# ══════════════════════════════════════════════════════════════════════════════


class TestTruncate:
    def test_short_string_unchanged(self):
        assert hook._truncate("hello", 10) == "hello"

    def test_long_string_truncated(self):
        result = hook._truncate("a" * 300, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        assert hook._truncate("a" * 200, 200) == "a" * 200


# ══════════════════════════════════════════════════════════════════════════════
# 6. Multi-turn transcript capture
# ══════════════════════════════════════════════════════════════════════════════


class TestMultiTurnTranscript:
    def test_captures_all_reasoning_blocks(self, tmp_path):
        """Multiple assistant messages each produce a reasoning block."""
        lines = [
            {"type": "user", "timestamp": "2026-03-15T07:00:00Z",
             "message": {"content": "Search for AI papers"}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:05Z",
             "message": {"content": [
                 {"type": "text", "text": "I'll search arxiv first."},
                 {"type": "tool_use", "name": "WebSearch", "input": {"q": "arxiv AI"}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:15Z",
             "message": {"content": [
                 {"type": "text", "text": "Found 3 papers. Now checking HN."},
                 {"type": "tool_use", "name": "WebSearch", "input": {"q": "HN AI"}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:25Z",
             "message": {"content": [
                 {"type": "text", "text": "HN has 2 relevant threads. Let me read them."},
                 {"type": "tool_use", "name": "WebFetch", "input": {"url": "https://..."}},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:01:00Z",
             "message": {"content": '{"findings": [{"title": "Paper 1"}]}'}},
        ]
        path = tmp_path / "multi.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines))
        messages = hook.parse_transcript(str(path))
        log = hook.extract_agent_log(messages)
        assert len(log["reasoning"]) == 4
        assert len(log["tool_calls"]) == 3
        assert "arxiv first" in log["reasoning"][0]
        assert "HN has 2" in log["reasoning"][2]

    def test_captures_tool_result_summaries(self, tmp_path):
        """Tool results from user messages are captured."""
        lines = [
            {"type": "user", "timestamp": "2026-03-15T07:00:00Z",
             "message": {"content": "Search"}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:05Z",
             "message": {"content": [
                 {"type": "text", "text": "Searching..."},
                 {"type": "tool_use", "id": "t1", "name": "WebSearch",
                  "input": {"q": "test"}},
             ]}},
            {"type": "user", "timestamp": "2026-03-15T07:00:10Z",
             "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "t1",
                  "content": "Found: Paper on alignment techniques (arxiv 2026)"},
             ]}},
            {"type": "assistant", "timestamp": "2026-03-15T07:00:15Z",
             "message": {"content": "The alignment paper looks promising."}},
        ]
        path = tmp_path / "results.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines))
        messages = hook.parse_transcript(str(path))
        log = hook.extract_agent_log(messages)
        assert len(log["tool_results"]) >= 1
        assert "alignment" in log["tool_results"][0]
