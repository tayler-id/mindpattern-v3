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


# --- Cross-agent dedup tests (ticket 2026-04-01-R015) ---

from unittest.mock import patch
import numpy as np
from orchestrator.agents import AgentResult, dedup_cross_agent_findings


def _make_finding(title, summary, importance="medium", source_url=None, agent=None):
    """Helper to build a finding dict."""
    f = {
        "title": title,
        "summary": summary,
        "importance": importance,
        "category": "AI",
        "source_name": "Test",
        "date_found": "2026-04-01",
    }
    if source_url:
        f["source_url"] = source_url
    return f


def _mock_embed_texts(texts):
    """Return deterministic embeddings where similar titles produce similar vectors.

    Findings with the same first word get nearly identical vectors (sim > 0.95).
    Different first words get orthogonal vectors (sim ~ 0).
    """
    dim = 384
    vectors = []
    seed_map = {}
    for text in texts:
        key = text.split()[0].lower() if text else "empty"
        if key not in seed_map:
            rng = np.random.RandomState(hash(key) % 2**31)
            vec = rng.randn(dim).astype(np.float32)
            vec /= np.linalg.norm(vec)
            seed_map[key] = vec
        base = seed_map[key]
        # Add tiny noise so pairs aren't exactly 1.0
        rng = np.random.RandomState(hash(text) % 2**31)
        noise = rng.randn(dim).astype(np.float32) * 0.01
        vec = base + noise
        vec /= np.linalg.norm(vec)
        vectors.append(vec.tolist())
    return vectors


class TestCrossAgentDedupRemovesDuplicates:
    """Near-duplicate findings across agents should be consolidated."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_removes_duplicates(self, mock_embed):
        results = [
            AgentResult(
                agent_name="agent-a",
                findings=[
                    _make_finding("DuplicateStory breaks new ground", "Short summary."),
                    _make_finding("UniqueA is interesting", "Only agent A found this."),
                ],
            ),
            AgentResult(
                agent_name="agent-b",
                findings=[
                    _make_finding(
                        "DuplicateStory covered from different angle",
                        "A much longer and more detailed summary with specifics.",
                        importance="high",
                        source_url="https://example.com/dup",
                    ),
                    _make_finding("UniqueB is noteworthy", "Only agent B found this."),
                ],
            ),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]
        titles = [f["title"] for f in all_findings]

        # One of the DuplicateStory findings should be removed
        dup_count = sum(1 for t in titles if t.startswith("DuplicateStory"))
        assert dup_count == 1, f"Expected 1 DuplicateStory finding, got {dup_count}: {titles}"
        assert summary["removed"] >= 1


class TestCrossAgentDedupKeepsHigherQuality:
    """When deduplicating, the higher-quality finding is kept."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_keeps_higher_quality(self, mock_embed):
        low_quality = _make_finding("SameStory from agent A", "Short.")
        high_quality = _make_finding(
            "SameStory from agent B with more detail",
            "This is a much longer and more detailed summary that provides real value.",
            importance="high",
            source_url="https://example.com/story",
        )

        results = [
            AgentResult(agent_name="agent-a", findings=[low_quality]),
            AgentResult(agent_name="agent-b", findings=[high_quality]),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]

        assert len(all_findings) == 1
        # The kept finding should be the high-quality one (longer summary, has URL)
        kept = all_findings[0]
        assert kept["importance"] == "high"
        assert "source_url" in kept
        assert "much longer" in kept["summary"]


class TestCrossAgentDedupPreservesUniqueFindings:
    """Findings below the similarity threshold should not be removed."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_preserves_unique_findings(self, mock_embed):
        results = [
            AgentResult(
                agent_name="agent-a",
                findings=[
                    _make_finding("AlphaProject launches v2", "Alpha released version 2."),
                    _make_finding("BetaCompany raises funding", "Beta got series B."),
                ],
            ),
            AgentResult(
                agent_name="agent-b",
                findings=[
                    _make_finding("GammaFramework hits 1.0", "Gamma reached stable."),
                    _make_finding("DeltaResearch publishes paper", "Delta published on arXiv."),
                ],
            ),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]

        assert len(all_findings) == 4
        assert summary["removed"] == 0


class TestCrossAgentDedupEmptyInput:
    """Empty input returns empty output with zero-count summary."""

    def test_cross_agent_dedup_empty_input(self):
        deduped, summary = dedup_cross_agent_findings([])
        assert deduped == []
        assert summary["removed"] == 0
        assert summary["total"] == 0
