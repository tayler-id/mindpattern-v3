"""Tests for memory/mirror.py — SQLite-to-Obsidian mirror generation.

Uses a temporary in-memory SQLite database and a temp vault directory.
Follows the same fixture pattern as test_memory.py.
"""

import sqlite3
from pathlib import Path

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Create a fresh in-memory database with full schema initialization."""
    from memory.db import _init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def vault(tmp_path):
    """Return a temporary vault directory."""
    return tmp_path / "vault"


@pytest.fixture
def seeded_db(db):
    """Database pre-loaded with representative test data across all tables."""
    # ── Findings ──────────────────────────────────────────────────────────
    db.execute(
        """INSERT INTO findings
           (run_date, agent, title, summary, importance, category, source_url, source_name)
           VALUES ('2026-03-15', 'security-researcher', 'CVE-2026-1234 in OpenSSL',
                   'Critical vulnerability found in OpenSSL 4.0', 'high', 'security',
                   'https://cve.mitre.org/cve/2026-1234', 'MITRE')"""
    )
    db.execute(
        """INSERT INTO findings
           (run_date, agent, title, summary, importance, category, source_url, source_name)
           VALUES ('2026-03-15', 'security-researcher', 'New Auth Bypass in Kubernetes',
                   'Authentication bypass via ServiceAccount tokens', 'high', 'security',
                   'https://kubernetes.io/blog/auth-bypass', 'Kubernetes Blog')"""
    )
    db.execute(
        """INSERT INTO findings
           (run_date, agent, title, summary, importance, category, source_url, source_name)
           VALUES ('2026-03-15', 'ai-researcher', 'Claude 5 Benchmarks Released',
                   'Anthropic releases Claude 5 with improved reasoning', 'medium', 'ai',
                   'https://anthropic.com/blog/claude-5', 'Anthropic Blog')"""
    )
    db.execute(
        """INSERT INTO findings
           (run_date, agent, title, summary, importance, category, source_url, source_name)
           VALUES ('2026-03-14', 'ai-researcher', 'GPT-5 API Update',
                   'OpenAI ships GPT-5 turbo API with function calling v3', 'medium', 'ai',
                   'https://openai.com/blog/gpt-5', 'OpenAI Blog')"""
    )

    # ── Social Posts ──────────────────────────────────────────────────────
    db.execute(
        """INSERT INTO social_posts
           (date, platform, content, post_type, anchor_text, gate2_action, posted)
           VALUES ('2026-03-15', 'twitter',
                   'Critical OpenSSL vulnerability CVE-2026-1234 affects all 4.x deployments. Patch now.',
                   'single', 'CVE-2026-1234', 'approved', 1)"""
    )
    db.execute(
        """INSERT INTO social_posts
           (date, platform, content, post_type, anchor_text, gate2_action, posted)
           VALUES ('2026-03-15', 'linkedin',
                   'Claude 5 just dropped with impressive reasoning benchmarks. Heres what matters for builders.',
                   'single', 'Claude 5', 'approved', 1)"""
    )

    # ── Editorial Corrections ─────────────────────────────────────────────
    db.execute(
        """INSERT INTO editorial_corrections
           (platform, original_text, approved_text, reason, created_at)
           VALUES ('twitter',
                   'OpenSSL is broken lol patch ur stuff',
                   'Critical OpenSSL vulnerability CVE-2026-1234 affects all 4.x deployments. Patch now.',
                   'Tone was too casual for security advisory',
                   '2026-03-15 10:00:00')"""
    )

    # ── Engagements ───────────────────────────────────────────────────────
    db.execute(
        """INSERT INTO engagements
           (user_id, platform, engagement_type, target_author, target_author_id,
            target_content, our_reply, status, created_at)
           VALUES ('ramsay', 'twitter', 'reply', '@swyx', 'swyx123',
                   'Interesting thread about AI agent architectures and how they scale',
                   'Great breakdown! We have been exploring similar multi-agent patterns.',
                   'posted', '2026-03-15 12:00:00')"""
    )
    db.execute(
        """INSERT INTO engagements
           (user_id, platform, engagement_type, target_author, target_author_id,
            target_content, our_reply, status, created_at)
           VALUES ('ramsay', 'twitter', 'follow', '@karpathy', 'karpathy456',
                   NULL, NULL, 'completed', '2026-03-15 14:00:00')"""
    )

    db.commit()
    return db


# ══════════════════════════════════════════════════════════════════════════════
# 1. generate_mirrors() creates expected files
# ══════════════════════════════════════════════════════════════════════════════


class TestGenerateMirrors:
    def test_creates_daily_file(self, seeded_db, vault):
        """generate_mirrors() creates daily/2026-03-15.md."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        daily_path = vault / "daily" / "2026-03-15.md"
        assert daily_path.exists(), f"Expected {daily_path} to exist"
        content = daily_path.read_text(encoding="utf-8")
        # Frontmatter
        assert "type: daily" in content
        assert "date: 2026-03-15" in content
        # Agent section
        assert "security-researcher" in content
        assert "ai-researcher" in content
        # Finding titles
        assert "CVE-2026-1234 in OpenSSL" in content

    def test_creates_topic_files(self, seeded_db, vault):
        """generate_mirrors() creates topic files based on agent names."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        topics_dir = vault / "topics"
        assert topics_dir.exists()
        topic_files = list(topics_dir.glob("*.md"))
        # Filter out _index.md
        topic_files = [f for f in topic_files if f.name != "_index.md"]
        assert len(topic_files) >= 1, "Expected at least one topic file"

        # security-researcher -> topic "security"
        security_path = topics_dir / "security.md"
        assert security_path.exists(), "Expected security.md topic file"
        content = security_path.read_text(encoding="utf-8")
        assert "type: topic" in content
        assert "CVE-2026-1234 in OpenSSL" in content

    def test_creates_source_files(self, seeded_db, vault):
        """generate_mirrors() creates source files from finding URLs."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        sources_dir = vault / "sources"
        assert sources_dir.exists()
        source_files = list(sources_dir.glob("*.md"))
        source_files = [f for f in source_files if f.name != "_index.md"]
        assert len(source_files) >= 1, "Expected at least one source file"

        # Check that at least one known source domain file was created
        source_names = {f.stem for f in source_files}
        # cve.mitre.org -> cve-mitre-org (or similar slug)
        assert any("mitre" in name for name in source_names) or \
               any("anthropic" in name for name in source_names), \
               f"Expected known source domain in {source_names}"

    def test_creates_posts_file(self, seeded_db, vault):
        """generate_mirrors() creates social/posts.md."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        posts_path = vault / "social" / "posts.md"
        assert posts_path.exists()
        content = posts_path.read_text(encoding="utf-8")
        assert "type: social" in content
        assert "twitter" in content
        assert "linkedin" in content
        assert "CVE-2026-1234" in content

    def test_creates_corrections_file(self, seeded_db, vault):
        """generate_mirrors() creates social/corrections.md."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        corrections_path = vault / "social" / "corrections.md"
        assert corrections_path.exists()
        content = corrections_path.read_text(encoding="utf-8")
        assert "Editorial Corrections" in content
        assert "Tone was too casual" in content

    def test_creates_engagement_log(self, seeded_db, vault):
        """generate_mirrors() creates social/engagement-log.md."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        log_path = vault / "social" / "engagement-log.md"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "Engagement Activity" in content
        assert "@swyx" in content

    def test_creates_engaged_authors_file(self, seeded_db, vault):
        """generate_mirrors() creates people/engaged-authors.md."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        authors_path = vault / "people" / "engaged-authors.md"
        assert authors_path.exists()
        content = authors_path.read_text(encoding="utf-8")
        assert "Engaged Authors" in content
        assert "@swyx" in content or "swyx" in content

    def test_creates_index_files(self, seeded_db, vault):
        """generate_mirrors() creates _index.md in each subfolder."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        for subfolder in ["daily", "topics", "sources", "social", "people"]:
            index_path = vault / subfolder / "_index.md"
            assert index_path.exists(), f"Expected _index.md in {subfolder}/"
            content = index_path.read_text(encoding="utf-8")
            assert "type: index" in content


# ══════════════════════════════════════════════════════════════════════════════
# 2. File content correctness
# ══════════════════════════════════════════════════════════════════════════════


class TestContentCorrectness:
    def test_daily_has_wiki_links_to_topics(self, seeded_db, vault):
        """Daily file wiki-links to topic files."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        content = (vault / "daily" / "2026-03-15.md").read_text(encoding="utf-8")
        assert "[[topics/" in content

    def test_daily_has_wiki_links_to_sources(self, seeded_db, vault):
        """Daily file wiki-links to source files."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        content = (vault / "daily" / "2026-03-15.md").read_text(encoding="utf-8")
        assert "[[sources/" in content

    def test_topic_has_wiki_links_to_daily(self, seeded_db, vault):
        """Topic file wiki-links back to daily log."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        content = (vault / "topics" / "security.md").read_text(encoding="utf-8")
        assert "[[daily/2026-03-15]]" in content

    def test_source_has_finding_history(self, seeded_db, vault):
        """Source file includes finding history."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        sources_dir = vault / "sources"
        source_files = [f for f in sources_dir.glob("*.md") if f.name != "_index.md"]
        assert len(source_files) > 0
        # At least one source file should have finding content
        found_finding = False
        for sf in source_files:
            content = sf.read_text(encoding="utf-8")
            if "Finding History" in content and "[[daily/" in content:
                found_finding = True
                break
        assert found_finding, "Expected at least one source to have findings with daily links"

    def test_frontmatter_has_lf_only(self, seeded_db, vault):
        """All generated files use LF line endings only (no CRLF)."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        for md_file in vault.rglob("*.md"):
            raw = md_file.read_bytes()
            assert b"\r\n" not in raw, f"CRLF found in {md_file}"
            assert b"\r" not in raw, f"CR found in {md_file}"

    def test_posts_includes_gate_outcome(self, seeded_db, vault):
        """Posts file includes gate outcome data."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        content = (vault / "social" / "posts.md").read_text(encoding="utf-8")
        assert "approved" in content.lower() or "Gate" in content


# ══════════════════════════════════════════════════════════════════════════════
# 3. Index file correctness
# ══════════════════════════════════════════════════════════════════════════════


class TestIndexFiles:
    def test_topics_index_links_to_topic_files(self, seeded_db, vault):
        """topics/_index.md contains links to all topic files."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        index_content = (vault / "topics" / "_index.md").read_text(encoding="utf-8")
        assert "[[topics/" in index_content
        assert "security" in index_content.lower()

    def test_sources_index_links_to_source_files(self, seeded_db, vault):
        """sources/_index.md contains links to all source files."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        index_content = (vault / "sources" / "_index.md").read_text(encoding="utf-8")
        assert "[[sources/" in index_content

    def test_daily_index_links_to_daily_files(self, seeded_db, vault):
        """daily/_index.md contains links to daily log files."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")

        index_content = (vault / "daily" / "_index.md").read_text(encoding="utf-8")
        assert "[[daily/" in index_content
        assert "2026-03-15" in index_content


# ══════════════════════════════════════════════════════════════════════════════
# 4. Archival
# ══════════════════════════════════════════════════════════════════════════════


class TestArchival:
    def test_decisions_archival_runs(self, seeded_db, vault):
        """generate_mirrors() runs archive_old_entries() on decisions.md."""
        from memory.mirror import generate_mirrors
        from memory.vault import append_entry, read_source_file

        decisions_path = vault / "decisions.md"

        # Write an entry dated 100 days ago (should be archived)
        old_entry = "## 2025-12-01\n\nOld decision that should be archived.\n"
        recent_entry = "## 2026-03-10\n\nRecent decision that should stay.\n"
        from memory.vault import atomic_write
        atomic_write(decisions_path, old_entry + "\n" + recent_entry)

        generate_mirrors(seeded_db, vault, "2026-03-15")

        # After archival, decisions.md should only have the recent entry
        remaining = read_source_file(decisions_path)
        assert "2026-03-10" in remaining
        assert "2025-12-01" not in remaining

        # Archive file should have the old entry
        archive_path = vault / "decisions-archive.md"
        assert archive_path.exists()
        archive_content = read_source_file(archive_path)
        assert "2025-12-01" in archive_content


# ══════════════════════════════════════════════════════════════════════════════
# 5. Edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_database(self, db, vault):
        """generate_mirrors() handles empty database gracefully."""
        from memory.mirror import generate_mirrors

        # Should not raise
        generate_mirrors(db, vault, "2026-03-15")

        # Daily file should still be created (even if empty)
        daily_path = vault / "daily" / "2026-03-15.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        assert "type: daily" in content
        assert "No findings this run" in content or "findings_count: 0" in content

    def test_findings_without_urls(self, db, vault):
        """Findings with NULL source_url are handled."""
        from memory.mirror import generate_mirrors

        db.execute(
            """INSERT INTO findings
               (run_date, agent, title, summary, importance, category)
               VALUES ('2026-03-15', 'test-agent', 'No URL Finding',
                       'A finding with no source URL', 'medium', 'general')"""
        )
        db.commit()

        # Should not raise
        generate_mirrors(db, vault, "2026-03-15")

        daily_path = vault / "daily" / "2026-03-15.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        assert "No URL Finding" in content

    def test_idempotent_runs(self, seeded_db, vault):
        """Running generate_mirrors() twice produces the same output."""
        from memory.mirror import generate_mirrors

        generate_mirrors(seeded_db, vault, "2026-03-15")
        first_content = (vault / "daily" / "2026-03-15.md").read_text(encoding="utf-8")

        generate_mirrors(seeded_db, vault, "2026-03-15")
        second_content = (vault / "daily" / "2026-03-15.md").read_text(encoding="utf-8")

        assert first_content == second_content

    def test_special_characters_in_titles(self, db, vault):
        """Titles with special characters don't break file generation."""
        from memory.mirror import generate_mirrors

        db.execute(
            """INSERT INTO findings
               (run_date, agent, title, summary, importance, category,
                source_url, source_name)
               VALUES ('2026-03-15', 'test-agent',
                       'What''s Next: "AI" & <ML> in 2026?',
                       'Summary with special chars & "quotes"', 'medium', 'ai',
                       'https://example.com/article', 'Example')"""
        )
        db.commit()

        # Should not raise
        generate_mirrors(db, vault, "2026-03-15")

        daily_path = vault / "daily" / "2026-03-15.md"
        assert daily_path.exists()


# ══════════════════════════════════════════════════════════════════════════════
# 6. Slug generation
# ══════════════════════════════════════════════════════════════════════════════


class TestSlugGeneration:
    def test_slugify_basic(self):
        """_slugify() converts strings to filesystem-safe slugs."""
        from memory.mirror import _slugify

        assert _slugify("Hello World") == "hello-world"
        assert _slugify("security-researcher") == "security-researcher"
        assert _slugify("cve.mitre.org") == "cve-mitre-org"

    def test_slugify_special_chars(self):
        """_slugify() strips special characters."""
        from memory.mirror import _slugify

        assert _slugify("What's Next?") == "whats-next"
        assert _slugify("AI & ML") == "ai-ml"
        assert _slugify("https://example.com") == "https-example-com"

    def test_topic_from_agent(self):
        """_topic_from_agent() extracts topic name from agent name."""
        from memory.mirror import _topic_from_agent

        assert _topic_from_agent("security-researcher") == "security"
        assert _topic_from_agent("ai-researcher") == "ai"
        assert _topic_from_agent("news") == "news"
        assert _topic_from_agent("general-news-researcher") == "general-news"

    def test_domain_from_url(self):
        """_domain_from_url() extracts domain from URL."""
        from memory.mirror import _domain_from_url

        assert _domain_from_url("https://cve.mitre.org/cve/2026-1234") == "cve.mitre.org"
        assert _domain_from_url("https://anthropic.com/blog/claude-5") == "anthropic.com"
        assert _domain_from_url("") is None
        assert _domain_from_url(None) is None
