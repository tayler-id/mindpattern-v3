"""Tests for the knowledge compiler (knowledge/compile.py).

TDD tests: no network, no API keys, no embedding model required.
Mocks embeddings and LLM calls to test logic in isolation.
"""

import json
import sqlite3
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

# We'll import these after the module exists
# from knowledge.compile import (
#     fetch_recent_findings,
#     cluster_findings,
#     match_clusters_to_concepts,
#     write_concept_page,
#     generate_index,
#     compile_knowledge,
# )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fake_embeddings(n: int, dim: int = 384) -> list[list[float]]:
    """Generate n random normalized embeddings for testing."""
    rng = np.random.RandomState(42)
    vecs = rng.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / norms
    return vecs.tolist()


def _make_similar_embeddings(n: int, base_idx: int = 0, dim: int = 384) -> list[list[float]]:
    """Generate n embeddings that are similar to each other (cosine > 0.95)."""
    rng = np.random.RandomState(base_idx)
    base = rng.randn(dim).astype(np.float32)
    base = base / np.linalg.norm(base)
    vecs = []
    for i in range(n):
        noise = rng.randn(dim).astype(np.float32) * 0.005
        v = base + noise
        v = v / np.linalg.norm(v)
        vecs.append(v.tolist())
    return vecs


@pytest.fixture
def findings_db(tmp_path):
    """In-memory SQLite DB with findings table populated."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            agent TEXT,
            title TEXT,
            summary TEXT,
            importance TEXT DEFAULT 'medium',
            category TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            source_name TEXT DEFAULT '',
            created_at TEXT
        )
    """)
    # Insert findings across 3 days, two topic clusters
    today = "2026-04-06"
    yesterday = "2026-04-05"
    two_days_ago = "2026-04-04"

    # Cluster 1: MCP security (3 findings)
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (today, "agents-researcher", "MCP Security Vulnerabilities Found in Chrome Extension",
         "Researchers discovered critical MCP protocol vulnerabilities that allow tool poisoning attacks.",
         "high", "Hacker News"),
    )
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (yesterday, "security-researcher", "MCP Tool Poisoning Attack Vector Published",
         "New attack vector published showing how MCP servers can be compromised via tool injection.",
         "high", "GitHub"),
    )
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (two_days_ago, "news-researcher", "MCP Protocol Security Audit Released",
         "Full security audit of the MCP protocol reveals multiple attack surfaces.",
         "medium", "TechCrunch"),
    )

    # Cluster 2: AI coding tools (3 findings)
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (today, "vibe-coding-researcher", "Claude Code Ships Autonomous Coding Agent",
         "Anthropic releases Claude Code with full autonomous coding capability.",
         "high", "Hacker News"),
    )
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (yesterday, "hn-researcher", "Cursor vs Claude Code Benchmark Results",
         "Community benchmarks show Claude Code outperforming Cursor on complex refactoring tasks.",
         "medium", "Reddit"),
    )
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (two_days_ago, "projects-researcher", "GitHub Copilot Workspace Public Beta",
         "GitHub launches Copilot Workspace with multi-file editing and PR generation.",
         "medium", "VentureBeat"),
    )

    # Outlier finding (won't cluster with either group)
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_name) VALUES (?, ?, ?, ?, ?, ?)",
        (today, "arxiv-researcher", "New Quantum Computing Algorithm Achieves 100x Speedup",
         "Breakthrough in quantum error correction enables practical quantum advantage.",
         "high", "arXiv"),
    )

    db.commit()
    return db


@pytest.fixture
def vault_dir(tmp_path):
    """Temporary vault directory with knowledge/ subdirectory."""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "concepts").mkdir()
    (knowledge_dir / "connections").mkdir()
    return tmp_path


@pytest.fixture
def existing_concept_page(vault_dir):
    """Pre-existing concept page for update tests."""
    concept_path = vault_dir / "knowledge" / "concepts" / "mcp-security.md"
    concept_path.write_text(textwrap.dedent("""\
        ---
        type: concept
        title: MCP Security
        first_seen: 2026-03-15
        last_updated: 2026-04-01
        finding_count: 12
        tags: security, mcp, protocol
        ---

        # MCP Security

        ## Summary

        The Model Context Protocol has multiple known attack surfaces including
        tool poisoning, prompt injection via tool descriptions, and unauthorized
        data exfiltration through MCP server responses.

        ## Key Insights

        - Tool poisoning is the primary attack vector
        - MCP servers can inject hidden instructions in tool descriptions
        - No standardized authentication between client and server

        ## Evidence

        - [[daily/2026-03-15|Initial MCP vulnerability report]]
        - [[daily/2026-03-20|MCP auth bypass demonstrated]]

        ## Related Concepts

        - [[concepts/ai-agent-security]]
        - [[concepts/supply-chain-attacks]]
    """))
    return concept_path


# ---------------------------------------------------------------------------
# Tests: fetch_recent_findings
# ---------------------------------------------------------------------------

class TestFetchRecentFindings:

    def test_returns_findings_within_lookback(self, findings_db):
        from knowledge.compile import fetch_recent_findings
        findings = fetch_recent_findings(findings_db, "2026-04-06", lookback_days=7)
        assert len(findings) == 7  # all 7 findings are within 7 days

    def test_respects_lookback_window(self, findings_db):
        from knowledge.compile import fetch_recent_findings
        findings = fetch_recent_findings(findings_db, "2026-04-06", lookback_days=1)
        # Only today's findings (3 findings on 2026-04-06)
        assert len(findings) == 3
        assert all(f["run_date"] == "2026-04-06" for f in findings)

    def test_returns_dicts_with_required_keys(self, findings_db):
        from knowledge.compile import fetch_recent_findings
        findings = fetch_recent_findings(findings_db, "2026-04-06", lookback_days=7)
        required_keys = {"title", "summary", "importance", "agent", "run_date", "source_name"}
        for f in findings:
            assert required_keys.issubset(f.keys()), f"Missing keys in {f.keys()}"

    def test_empty_db_returns_empty_list(self):
        from knowledge.compile import fetch_recent_findings
        db = sqlite3.connect(":memory:")
        db.execute("""
            CREATE TABLE findings (
                id INTEGER PRIMARY KEY, run_date TEXT, agent TEXT,
                title TEXT, summary TEXT, importance TEXT,
                category TEXT, source_url TEXT, source_name TEXT, created_at TEXT
            )
        """)
        assert fetch_recent_findings(db, "2026-04-06", lookback_days=7) == []


# ---------------------------------------------------------------------------
# Tests: cluster_findings
# ---------------------------------------------------------------------------

class TestClusterFindings:

    @patch("knowledge.compile.embed_texts")
    def test_groups_similar_findings(self, mock_embed):
        from knowledge.compile import cluster_findings

        # 3 similar MCP findings + 3 similar AI coding findings + 1 outlier
        mcp_vecs = _make_similar_embeddings(3, base_idx=0)
        coding_vecs = _make_similar_embeddings(3, base_idx=99)
        outlier_vecs = _make_fake_embeddings(1)

        mock_embed.return_value = mcp_vecs + coding_vecs + outlier_vecs

        findings = [
            {"title": f"MCP finding {i}", "summary": f"MCP summary {i}"} for i in range(3)
        ] + [
            {"title": f"Coding finding {i}", "summary": f"Coding summary {i}"} for i in range(3)
        ] + [
            {"title": "Quantum outlier", "summary": "Quantum stuff"}
        ]

        clusters = cluster_findings(findings)
        assert len(clusters) == 3  # MCP cluster, coding cluster, outlier
        # The two main clusters should have 3 items each
        sizes = sorted([len(c) for c in clusters], reverse=True)
        assert sizes[0] == 3
        assert sizes[1] == 3
        assert sizes[2] == 1

    @patch("knowledge.compile.embed_texts")
    def test_empty_findings_returns_empty(self, mock_embed):
        from knowledge.compile import cluster_findings
        mock_embed.return_value = []
        assert cluster_findings([]) == []

    @patch("knowledge.compile.embed_texts")
    def test_single_finding_returns_one_cluster(self, mock_embed):
        from knowledge.compile import cluster_findings
        mock_embed.return_value = _make_fake_embeddings(1)
        findings = [{"title": "Only finding", "summary": "Only summary"}]
        clusters = cluster_findings(findings)
        assert len(clusters) == 1
        assert len(clusters[0]) == 1


# ---------------------------------------------------------------------------
# Tests: match_clusters_to_concepts
# ---------------------------------------------------------------------------

class TestMatchClustersToConcepts:

    @patch("knowledge.compile.embed_texts")
    def test_matches_cluster_to_existing_concept(self, mock_embed, vault_dir, existing_concept_page):
        from knowledge.compile import match_clusters_to_concepts

        # Make the cluster centroid similar to "MCP Security" embedding
        similar_vecs = _make_similar_embeddings(2, base_idx=42)
        concept_vec = similar_vecs[0]
        cluster_centroid = similar_vecs[1]

        # First call: embed existing concept titles; second call: embed cluster labels
        mock_embed.side_effect = [
            [concept_vec],       # existing concept "MCP Security"
            [cluster_centroid],  # cluster label
        ]

        clusters = [[
            {"title": "MCP Security Vulnerability", "summary": "MCP vuln"},
            {"title": "MCP Attack Vector", "summary": "MCP attack"},
        ]]

        matches = match_clusters_to_concepts(
            clusters, vault_dir / "knowledge" / "concepts"
        )
        assert len(matches) == 1
        assert matches[0]["existing_path"] is not None
        assert "mcp-security" in str(matches[0]["existing_path"])

    @patch("knowledge.compile.embed_texts")
    def test_new_concept_when_no_match(self, mock_embed, vault_dir):
        from knowledge.compile import match_clusters_to_concepts

        # Very different embeddings — no match
        vecs = _make_fake_embeddings(2)
        mock_embed.side_effect = [
            [],       # no existing concepts
            [vecs[0]],  # cluster label
        ]

        clusters = [[
            {"title": "Brand New Topic", "summary": "Something new"},
        ]]

        matches = match_clusters_to_concepts(
            clusters, vault_dir / "knowledge" / "concepts"
        )
        assert len(matches) == 1
        assert matches[0]["existing_path"] is None


# ---------------------------------------------------------------------------
# Tests: write_concept_page
# ---------------------------------------------------------------------------

class TestWriteConceptPage:

    def test_creates_new_concept_file(self, vault_dir):
        from knowledge.compile import write_concept_page

        concept_data = {
            "title": "AI Coding Tools",
            "slug": "ai-coding-tools",
            "summary": "AI-powered coding assistants are transforming software development.",
            "key_insights": [
                "Claude Code leads in autonomous refactoring",
                "Local models catching up via quantization",
            ],
            "evidence": [
                {"date": "2026-04-06", "title": "Claude Code Ships"},
                {"date": "2026-04-05", "title": "Cursor Benchmark"},
            ],
            "related_concepts": ["vibe-coding", "developer-productivity"],
            "tags": ["ai", "coding", "tools"],
            "first_seen": "2026-04-04",
            "finding_count": 3,
        }

        concept_dir = vault_dir / "knowledge" / "concepts"
        write_concept_page(concept_dir, concept_data)

        path = concept_dir / "ai-coding-tools.md"
        assert path.exists()
        content = path.read_text()

        # Check frontmatter
        assert "type: concept" in content
        assert 'title: "AI Coding Tools"' in content
        assert "first_seen: 2026-04-04" in content

        # Check body sections
        assert "## Summary" in content
        assert "AI-powered coding assistants" in content
        assert "## Key Points" in content
        assert "Claude Code leads" in content
        assert "## Evidence" in content
        assert "daily/2026-04-06" in content
        assert "## Related" in content
        assert "concepts/vibe-coding]]" in content

    def test_updates_existing_concept_file(self, vault_dir, existing_concept_page):
        from knowledge.compile import write_concept_page

        concept_data = {
            "title": "MCP Security",
            "slug": "mcp-security",
            "summary": "Updated summary with new findings about MCP vulnerabilities.",
            "key_insights": [
                "Tool poisoning remains primary vector",
                "New auth bypass discovered in Chrome extension",
                "MCP servers lack input validation",
            ],
            "evidence": [
                {"date": "2026-04-06", "title": "MCP Chrome Extension Vuln"},
                {"date": "2026-04-05", "title": "MCP Tool Poisoning Published"},
            ],
            "related_concepts": ["ai-agent-security", "supply-chain-attacks"],
            "tags": ["security", "mcp", "protocol"],
            "first_seen": "2026-03-15",
            "finding_count": 15,
        }

        concept_dir = vault_dir / "knowledge" / "concepts"
        write_concept_page(concept_dir, concept_data)

        content = existing_concept_page.read_text()
        assert "finding_count: 15" in content
        assert "New auth bypass" in content


# ---------------------------------------------------------------------------
# Tests: generate_index
# ---------------------------------------------------------------------------

class TestGenerateIndex:

    def test_generates_index_from_concept_files(self, vault_dir):
        from knowledge.compile import generate_index

        concepts_dir = vault_dir / "knowledge" / "concepts"

        # Create two concept pages
        (concepts_dir / "mcp-security.md").write_text(textwrap.dedent("""\
            ---
            type: concept
            title: MCP Security
            finding_count: 12
            ---
            # MCP Security
            ## Summary
            MCP has security issues.
        """))
        (concepts_dir / "ai-coding-tools.md").write_text(textwrap.dedent("""\
            ---
            type: concept
            title: AI Coding Tools
            finding_count: 8
            ---
            # AI Coding Tools
            ## Summary
            AI coding tools are evolving fast.
        """))

        knowledge_dir = vault_dir / "knowledge"
        generate_index(knowledge_dir)

        index_path = knowledge_dir / "index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "concepts/mcp-security|MCP Security]]" in content
        assert "concepts/ai-coding-tools|AI Coding Tools]]" in content

    def test_empty_concepts_dir(self, vault_dir):
        from knowledge.compile import generate_index

        knowledge_dir = vault_dir / "knowledge"
        generate_index(knowledge_dir)

        index_path = knowledge_dir / "index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "No concepts compiled yet" in content


# ---------------------------------------------------------------------------
# Tests: compile_knowledge (integration)
# ---------------------------------------------------------------------------

class TestCompileKnowledge:

    @patch("knowledge.compile.run_claude_prompt")
    @patch("knowledge.compile.embed_texts")
    def test_end_to_end_creates_concepts(self, mock_embed, mock_claude, findings_db, vault_dir):
        from knowledge.compile import compile_knowledge

        # Set up embeddings: 2 clusters of 3 + 1 outlier
        mcp_vecs = _make_similar_embeddings(3, base_idx=0)
        coding_vecs = _make_similar_embeddings(3, base_idx=99)
        outlier_vecs = _make_fake_embeddings(1)

        # embed_texts is called multiple times:
        # 1. cluster_findings (7 findings)
        # 2. match_clusters_to_concepts: existing concepts (0) + cluster labels
        all_vecs = mcp_vecs + coding_vecs + outlier_vecs
        mock_embed.side_effect = [
            all_vecs,   # cluster_findings
            [],         # existing concept embeddings (none exist)
            _make_fake_embeddings(3),  # cluster label embeddings
        ]

        # Mock Claude synthesis responses
        mock_claude.side_effect = [
            (json.dumps({
                "title": "MCP Security Vulnerabilities",
                "summary": "Critical security issues in the MCP protocol.",
                "key_insights": ["Tool poisoning is the primary vector"],
                "related_concepts": ["ai-agent-security"],
                "tags": ["security", "mcp"],
            }), 0),
            (json.dumps({
                "title": "AI Coding Tools Evolution",
                "summary": "AI coding assistants are rapidly improving.",
                "key_insights": ["Claude Code leads in autonomous tasks"],
                "related_concepts": ["developer-productivity"],
                "tags": ["ai", "coding"],
            }), 0),
            (json.dumps({
                "title": "Quantum Computing Advances",
                "summary": "New quantum algorithms show practical speedups.",
                "key_insights": ["Error correction breakthrough"],
                "related_concepts": [],
                "tags": ["quantum"],
            }), 0),
        ]

        stats = compile_knowledge(
            db=findings_db,
            vault_dir=vault_dir,
            date_str="2026-04-06",
            lookback_days=7,
        )

        assert stats["findings_processed"] == 7
        assert stats["concepts_created"] >= 1
        assert stats["concepts_updated"] == 0

        # Check concept files were created
        concepts_dir = vault_dir / "knowledge" / "concepts"
        concept_files = list(concepts_dir.glob("*.md"))
        assert len(concept_files) >= 1

        # Check index was generated
        index_path = vault_dir / "knowledge" / "index.md"
        assert index_path.exists()

    @patch("knowledge.compile.run_claude_prompt")
    @patch("knowledge.compile.embed_texts")
    def test_updates_existing_concept(self, mock_embed, mock_claude, findings_db, vault_dir, existing_concept_page):
        from knowledge.compile import compile_knowledge

        # All findings cluster into one group that matches existing MCP concept
        similar_vecs = _make_similar_embeddings(7, base_idx=42)
        concept_embed = similar_vecs[0]  # existing concept embedding

        mock_embed.side_effect = [
            similar_vecs,       # cluster_findings (all 7 similar)
            [concept_embed],    # existing concept "MCP Security"
            [similar_vecs[1]],  # cluster label embedding
        ]

        mock_claude.return_value = (json.dumps({
            "title": "MCP Security",
            "summary": "Updated: MCP protocol has expanding attack surface.",
            "key_insights": [
                "Tool poisoning remains critical",
                "Chrome extension adds new vectors",
            ],
            "related_concepts": ["ai-agent-security", "supply-chain-attacks"],
            "tags": ["security", "mcp"],
        }), 0)

        stats = compile_knowledge(
            db=findings_db,
            vault_dir=vault_dir,
            date_str="2026-04-06",
            lookback_days=7,
        )

        assert stats["concepts_updated"] >= 1

    @patch("knowledge.compile.embed_texts")
    def test_no_findings_produces_no_concepts(self, mock_embed, vault_dir):
        from knowledge.compile import compile_knowledge

        db = sqlite3.connect(":memory:")
        db.execute("""
            CREATE TABLE findings (
                id INTEGER PRIMARY KEY, run_date TEXT, agent TEXT,
                title TEXT, summary TEXT, importance TEXT,
                category TEXT, source_url TEXT, source_name TEXT, created_at TEXT
            )
        """)

        stats = compile_knowledge(
            db=db,
            vault_dir=vault_dir,
            date_str="2026-04-06",
            lookback_days=7,
        )

        assert stats["findings_processed"] == 0
        assert stats["concepts_created"] == 0
        assert stats["concepts_updated"] == 0

    @patch("knowledge.compile.run_claude_prompt")
    @patch("knowledge.compile.embed_texts")
    def test_handles_claude_error_gracefully(self, mock_embed, mock_claude, findings_db, vault_dir):
        from knowledge.compile import compile_knowledge

        mock_embed.side_effect = [
            _make_fake_embeddings(7),  # all different = 7 clusters
            [],                        # no existing concepts
            _make_fake_embeddings(7),  # cluster labels
        ]

        # Claude returns non-zero exit code
        mock_claude.return_value = ("", 1)

        stats = compile_knowledge(
            db=findings_db,
            vault_dir=vault_dir,
            date_str="2026-04-06",
            lookback_days=7,
        )

        # Should handle gracefully, not crash
        assert stats["errors"] > 0

    @patch("knowledge.compile.run_claude_prompt")
    @patch("knowledge.compile.embed_texts")
    def test_handles_malformed_claude_json(self, mock_embed, mock_claude, findings_db, vault_dir):
        from knowledge.compile import compile_knowledge

        mock_embed.side_effect = [
            _make_similar_embeddings(7, base_idx=0),
            [],
            _make_fake_embeddings(1),
        ]

        mock_claude.return_value = ("not valid json {{{", 0)

        stats = compile_knowledge(
            db=findings_db,
            vault_dir=vault_dir,
            date_str="2026-04-06",
            lookback_days=7,
        )

        assert stats["errors"] > 0
