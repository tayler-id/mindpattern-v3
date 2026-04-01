"""Tests for orchestrator/agents.py _parse_findings().

Ticket: 2026-04-01-007
Root cause: greedy regex r'{[\\s\\S]*"findings"[\\s\\S]*}' matches from
first { to last } in the entire output, producing invalid JSON when the
agent output contains text before/after the JSON block or multiple JSON
objects.
"""

import json
import time

import pytest

from orchestrator.agents import _parse_findings


class TestParseFindingsWithTextBeforeJson:
    """Agent output has prose before and after the JSON block."""

    def test_extracts_findings_despite_surrounding_text(self):
        output = (
            'Here are my findings:\n'
            '{"findings": [{"title": "Test Finding", "summary": "A summary", '
            '"importance": "high", "category": "AI", "source_url": "https://example.com", '
            '"source_name": "Example", "date_found": "2026-03-31"}]}\n'
            'Done. Timing: {"elapsed_ms": 320}\n'
            'Agent complete.'
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 1
        assert result[0]["title"] == "Test Finding"


class TestParseFindingsWithMultipleJsonBlocks:
    """Agent output contains a metadata JSON block followed by the findings block."""

    def test_selects_findings_block_not_metadata(self):
        # Metadata block includes "sources" array — so the greedy array
        # fallback r'\[[\s\S]*\]' would also match the wrong span.
        metadata_block = json.dumps({
            "agent": "test-agent",
            "model": "opus",
            "sources": ["rss", "twitter", "reddit"],
            "timestamp": "2026-03-31T12:00:00Z",
        })
        findings_block = json.dumps({
            "findings": [
                {
                    "title": "Real Finding",
                    "summary": "The actual result",
                    "importance": "high",
                    "category": "AI",
                    "source_url": "https://example.com/real",
                    "source_name": "Example",
                    "date_found": "2026-03-31",
                },
                {
                    "title": "Second Finding",
                    "summary": "Another result",
                    "importance": "medium",
                    "category": "ML",
                    "source_url": "https://example.com/second",
                    "source_name": "Other",
                    "date_found": "2026-03-31",
                },
            ]
        })
        # Trailing JSON block (status) ensures greedy regex overshoots
        status_block = json.dumps({"status": "complete", "elapsed_ms": 4200})
        output = (
            f"Metadata: {metadata_block}\n"
            f"Results:\n{findings_block}\n"
            f"Status: {status_block}\n"
            f"End of output."
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 2
        assert result[0]["title"] == "Real Finding"
        assert result[1]["title"] == "Second Finding"


class TestParseFindingsWithNestedBracesInValues:
    """Finding values contain literal { } characters (e.g. code snippets)."""

    def test_handles_braces_inside_string_values(self):
        findings_obj = {
            "findings": [
                {
                    "title": "Code Pattern {x: 1}",
                    "summary": "The function uses {key: value} syntax for config objects.",
                    "importance": "medium",
                    "category": "Dev Tools",
                    "source_url": "https://example.com/code",
                    "source_name": "GitHub",
                    "date_found": "2026-03-31",
                },
            ]
        }
        output = (
            "Thinking about this...\n"
            + json.dumps(findings_obj)
            + "\nAll done."
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 1
        assert "{x: 1}" in result[0]["title"]
        assert "{key: value}" in result[0]["summary"]


class TestParseFindingsLargeOutputPerformance:
    """_parse_findings must handle 100K+ char outputs in under 1 second."""

    def test_parses_large_output_within_time_limit(self):
        # Build a realistic large output: lots of prose, then JSON
        filler = "This is a long line of agent reasoning output. " * 220  # ~10.3K per block
        blocks = [filler] * 10  # ~103K of filler text
        findings_obj = {
            "findings": [
                {
                    "title": f"Finding {i}",
                    "summary": f"Summary for finding {i} with details.",
                    "importance": "medium",
                    "category": "AI",
                    "source_url": f"https://example.com/{i}",
                    "source_name": "Source",
                    "date_found": "2026-03-31",
                }
                for i in range(20)
            ]
        }
        output = "\n".join(blocks) + "\n" + json.dumps(findings_obj) + "\nEnd."

        assert len(output) > 100_000, f"Output only {len(output)} chars, need >100K"

        start = time.monotonic()
        result = _parse_findings(output, "test-agent")
        elapsed = time.monotonic() - start

        assert len(result) == 20
        assert elapsed < 1.0, f"Parsing took {elapsed:.2f}s, must be < 1s"
