"""Tests for memory/vault.py — atomic read/write for Obsidian markdown files.

Uses a temporary directory so tests never touch the real vault at data/ramsay/mindpattern/.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def vault_dir():
    """Create a fresh temporary directory that acts as a vault root."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ══════════════════════════════════════════════════════════════════════════════
# 1. atomic_write
# ══════════════════════════════════════════════════════════════════════════════


class TestAtomicWrite:
    def test_creates_file(self, vault_dir):
        """atomic_write creates a new file with the given content."""
        from memory.vault import atomic_write

        target = vault_dir / "hello.md"
        atomic_write(target, "# Hello\n\nWorld\n")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# Hello\n\nWorld\n"

    def test_utf8_lf_encoding(self, vault_dir):
        """atomic_write produces UTF-8 with LF line endings only (no CR)."""
        from memory.vault import atomic_write

        target = vault_dir / "encoding.md"
        content = "Line one\nLine two\nUnicode: \u00e9\u00e0\u00fc\u2603\n"
        atomic_write(target, content)

        raw = target.read_bytes()
        assert b"\r" not in raw  # no CR bytes
        assert "\u00e9\u00e0\u00fc\u2603".encode("utf-8") in raw

    def test_overwrites_existing(self, vault_dir):
        """atomic_write replaces existing file content."""
        from memory.vault import atomic_write

        target = vault_dir / "overwrite.md"
        atomic_write(target, "old content")
        atomic_write(target, "new content")

        assert target.read_text(encoding="utf-8") == "new content"

    def test_creates_parent_dirs(self, vault_dir):
        """atomic_write creates parent directories that don't exist yet."""
        from memory.vault import atomic_write

        target = vault_dir / "deeply" / "nested" / "dir" / "file.md"
        atomic_write(target, "deep content")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "deep content"

    def test_no_partial_writes(self, vault_dir):
        """atomic_write does not leave a .tmp file behind on success."""
        from memory.vault import atomic_write

        target = vault_dir / "clean.md"
        atomic_write(target, "content")

        tmp_files = list(vault_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. read_source_file
# ══════════════════════════════════════════════════════════════════════════════


class TestReadSourceFile:
    def test_reads_existing(self, vault_dir):
        """read_source_file returns content of an existing file."""
        from memory.vault import read_source_file

        target = vault_dir / "existing.md"
        target.write_text("# Existing\n\nContent here.\n", encoding="utf-8")

        result = read_source_file(target)
        assert result == "# Existing\n\nContent here.\n"

    def test_returns_empty_for_missing(self, vault_dir):
        """read_source_file returns '' for a file that does not exist."""
        from memory.vault import read_source_file

        result = read_source_file(vault_dir / "nonexistent.md")
        assert result == ""


# ══════════════════════════════════════════════════════════════════════════════
# 3. update_section
# ══════════════════════════════════════════════════════════════════════════════


class TestUpdateSection:
    def test_update_existing_section(self, vault_dir):
        """update_section replaces the body of an existing ## section."""
        from memory.vault import atomic_write, update_section

        target = vault_dir / "sections.md"
        atomic_write(target, (
            "# Title\n\n"
            "## Alpha\n\n"
            "Old alpha content.\n\n"
            "## Beta\n\n"
            "Beta content.\n"
        ))

        update_section(target, "Alpha", "New alpha content.")

        text = target.read_text(encoding="utf-8")
        assert "New alpha content." in text
        assert "Old alpha content." not in text
        # Beta should be untouched
        assert "Beta content." in text

    def test_append_missing_section(self, vault_dir):
        """update_section appends a new section when the heading is not found."""
        from memory.vault import atomic_write, update_section

        target = vault_dir / "sections.md"
        atomic_write(target, "# Title\n\n## Existing\n\nBody.\n")

        update_section(target, "New Section", "Brand new content.")

        text = target.read_text(encoding="utf-8")
        assert "## New Section" in text
        assert "Brand new content." in text
        # Existing section preserved
        assert "## Existing" in text
        assert "Body." in text

    def test_case_insensitive_match(self, vault_dir):
        """update_section matches heading case-insensitively."""
        from memory.vault import atomic_write, update_section

        target = vault_dir / "case.md"
        atomic_write(target, "# Doc\n\n## Current Status\n\nOld status.\n")

        update_section(target, "current status", "Updated status.")

        text = target.read_text(encoding="utf-8")
        assert "Updated status." in text
        assert "Old status." not in text

    def test_underscore_space_normalization(self, vault_dir):
        """update_section normalizes underscores to spaces for matching."""
        from memory.vault import atomic_write, update_section

        target = vault_dir / "underscore.md"
        atomic_write(target, "# Doc\n\n## Recent Decisions\n\nOld decisions.\n")

        update_section(target, "recent_decisions", "New decisions.")

        text = target.read_text(encoding="utf-8")
        assert "New decisions." in text
        assert "Old decisions." not in text

    def test_max_length_enforcement(self, vault_dir):
        """update_section raises ValueError if content exceeds MAX_SECTION_LENGTH."""
        from memory.vault import MAX_SECTION_LENGTH, atomic_write, update_section

        target = vault_dir / "long.md"
        atomic_write(target, "# Doc\n\n## Section\n\nBody.\n")

        with pytest.raises(ValueError, match=str(MAX_SECTION_LENGTH)):
            update_section(target, "Section", "x" * (MAX_SECTION_LENGTH + 1))

    def test_exactly_max_length_is_ok(self, vault_dir):
        """update_section accepts content that is exactly MAX_SECTION_LENGTH."""
        from memory.vault import MAX_SECTION_LENGTH, atomic_write, update_section

        target = vault_dir / "exact.md"
        atomic_write(target, "# Doc\n\n## Section\n\nBody.\n")

        # Should not raise
        update_section(target, "Section", "x" * MAX_SECTION_LENGTH)

        text = target.read_text(encoding="utf-8")
        assert "x" * MAX_SECTION_LENGTH in text

    def test_creates_file_if_missing(self, vault_dir):
        """update_section creates the file if it doesn't exist."""
        from memory.vault import update_section

        target = vault_dir / "newfile.md"
        update_section(target, "First Section", "Content here.")

        text = target.read_text(encoding="utf-8")
        assert "## First Section" in text
        assert "Content here." in text


# ══════════════════════════════════════════════════════════════════════════════
# 4. append_entry
# ══════════════════════════════════════════════════════════════════════════════


class TestAppendEntry:
    def test_adds_dated_entry(self, vault_dir):
        """append_entry adds a dated ## heading entry."""
        from memory.vault import append_entry

        target = vault_dir / "decisions.md"
        append_entry(target, "Decided to use atomic writes for all vault ops.")

        text = target.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        assert f"## {today}" in text
        assert "Decided to use atomic writes" in text

    def test_preserves_existing(self, vault_dir):
        """append_entry preserves existing entries when appending."""
        from memory.vault import append_entry, atomic_write

        target = vault_dir / "decisions.md"
        atomic_write(target, "## 2026-03-10\n\nOld decision.\n")

        append_entry(target, "New decision.")

        text = target.read_text(encoding="utf-8")
        assert "Old decision." in text
        assert "New decision." in text

    def test_creates_file_if_missing(self, vault_dir):
        """append_entry creates the file if it doesn't exist."""
        from memory.vault import append_entry

        target = vault_dir / "new_log.md"
        append_entry(target, "First entry.")

        assert target.exists()
        text = target.read_text(encoding="utf-8")
        assert "First entry." in text


# ══════════════════════════════════════════════════════════════════════════════
# 5. get_recent_entries
# ══════════════════════════════════════════════════════════════════════════════


class TestGetRecentEntries:
    def test_returns_last_n_in_reverse_order(self, vault_dir):
        """get_recent_entries returns the last N entries, most recent first."""
        from memory.vault import atomic_write, get_recent_entries

        target = vault_dir / "entries.md"
        atomic_write(target, (
            "## 2026-03-01\n\nFirst entry.\n\n"
            "## 2026-03-05\n\nSecond entry.\n\n"
            "## 2026-03-10\n\nThird entry.\n\n"
            "## 2026-03-14\n\nFourth entry.\n"
        ))

        entries = get_recent_entries(target, n=2)
        assert len(entries) == 2
        assert "Fourth entry." in entries[0]
        assert "Third entry." in entries[1]

    def test_returns_all_when_fewer_than_n(self, vault_dir):
        """get_recent_entries returns all entries when fewer than N exist."""
        from memory.vault import atomic_write, get_recent_entries

        target = vault_dir / "few.md"
        atomic_write(target, "## 2026-03-01\n\nOnly entry.\n")

        entries = get_recent_entries(target, n=10)
        assert len(entries) == 1
        assert "Only entry." in entries[0]

    def test_returns_empty_for_missing_file(self, vault_dir):
        """get_recent_entries returns [] for a nonexistent file."""
        from memory.vault import get_recent_entries

        entries = get_recent_entries(vault_dir / "nope.md")
        assert entries == []

    def test_default_n_is_7(self, vault_dir):
        """get_recent_entries defaults to n=7."""
        from memory.vault import atomic_write, get_recent_entries

        target = vault_dir / "many.md"
        parts = []
        for i in range(10):
            day = f"2026-03-{i+1:02d}"
            parts.append(f"## {day}\n\nEntry {i+1}.\n")
        atomic_write(target, "\n".join(parts))

        entries = get_recent_entries(target)
        assert len(entries) == 7


# ══════════════════════════════════════════════════════════════════════════════
# 6. archive_old_entries
# ══════════════════════════════════════════════════════════════════════════════


class TestArchiveOldEntries:
    def test_moves_old_entries_to_archive(self, vault_dir):
        """archive_old_entries moves entries older than max_age_days to archive."""
        from memory.vault import atomic_write, archive_old_entries

        target = vault_dir / "decisions.md"
        archive = vault_dir / "archive" / "decisions.md"

        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        atomic_write(target, (
            f"## {old_date}\n\nOld decision.\n\n"
            f"## {recent_date}\n\nRecent decision.\n"
        ))

        archive_old_entries(target, archive, max_age_days=90)

        # Recent entry stays in original file
        source_text = target.read_text(encoding="utf-8")
        assert "Recent decision." in source_text
        assert "Old decision." not in source_text

        # Old entry moved to archive
        archive_text = archive.read_text(encoding="utf-8")
        assert "Old decision." in archive_text
        assert old_date in archive_text

    def test_keeps_recent_entries(self, vault_dir):
        """archive_old_entries leaves recent entries untouched."""
        from memory.vault import atomic_write, archive_old_entries

        target = vault_dir / "decisions.md"
        archive = vault_dir / "archive.md"

        recent_date = datetime.now().strftime("%Y-%m-%d")
        atomic_write(target, f"## {recent_date}\n\nFresh decision.\n")

        archive_old_entries(target, archive, max_age_days=90)

        source_text = target.read_text(encoding="utf-8")
        assert "Fresh decision." in source_text
        # Archive should not exist (nothing was archived)
        assert not archive.exists()

    def test_appends_to_existing_archive(self, vault_dir):
        """archive_old_entries appends to an existing archive file."""
        from memory.vault import atomic_write, archive_old_entries

        target = vault_dir / "decisions.md"
        archive = vault_dir / "archive.md"

        old_date_1 = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        old_date_2 = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        recent_date = datetime.now().strftime("%Y-%m-%d")

        # Pre-existing archive content
        atomic_write(archive, f"## {old_date_1}\n\nPreviously archived.\n")

        atomic_write(target, (
            f"## {old_date_2}\n\nMoving this.\n\n"
            f"## {recent_date}\n\nKeeping this.\n"
        ))

        archive_old_entries(target, archive, max_age_days=90)

        archive_text = archive.read_text(encoding="utf-8")
        assert "Previously archived." in archive_text
        assert "Moving this." in archive_text
