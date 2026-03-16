"""Atomic read/write for Obsidian vault markdown files.

All writes go through atomic_write() — write to a .tmp sibling, then os.rename
so Obsidian never sees a half-written file. Every file is UTF-8 with LF line
endings only.

The vault root is data/ramsay/mindpattern/ but all functions accept explicit
paths so tests can use a temporary directory.
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

MAX_SECTION_LENGTH = 500


# ── Core I/O ────────────────────────────────────────────────────────────────


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically.

    Creates parent directories as needed. Normalises line endings to LF and
    encodes as UTF-8. Writes to a .tmp sibling first, then renames so readers
    (including Obsidian) never see partial content.

    Args:
        path: Destination file path.
        content: String content to write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise any stray CR-LF or lone CR to LF
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        os.rename(tmp, path)
    except BaseException:
        # Clean up the temp file if the rename fails
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def read_source_file(path: Path) -> str:
    """Read a markdown file and return its content.

    Args:
        path: File path to read.

    Returns:
        File content as a string, or '' if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# ── Section-level operations ────────────────────────────────────────────────


def _normalise_heading(name: str) -> str:
    """Lower-case and replace underscores with spaces for comparison."""
    return name.strip().lower().replace("_", " ")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, body) pairs on ``## `` boundaries.

    The first element may have heading == '' if there is content before the
    first ``## `` heading.
    """
    # Split on lines that start with "## "
    pattern = re.compile(r"^(## .+)$", re.MULTILINE)
    parts = pattern.split(text)

    sections: list[tuple[str, str]] = []
    i = 0
    while i < len(parts):
        if parts[i].startswith("## "):
            heading = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            sections.append((heading, body))
            i += 2
        else:
            # Preamble before any ## heading
            sections.append(("", parts[i]))
            i += 1

    return sections


def update_section(path: Path, section_name: str, new_content: str) -> None:
    """Update a ``## ``-delimited section in a markdown file.

    Matching is case-insensitive and normalises underscores to spaces.
    If the section exists its body is replaced; otherwise a new section is
    appended at the end of the file.

    Args:
        path: File path (created if missing).
        section_name: Section heading text (without the ``## `` prefix).
        new_content: New body for the section.

    Raises:
        ValueError: If *new_content* exceeds MAX_SECTION_LENGTH (500) chars.
    """
    if len(new_content) > MAX_SECTION_LENGTH:
        raise ValueError(
            f"Section content is {len(new_content)} chars, max is {MAX_SECTION_LENGTH} (500)"
        )

    path = Path(path)
    existing = read_source_file(path)
    target_norm = _normalise_heading(section_name)

    sections = _split_sections(existing)

    found = False
    for idx, (heading, _body) in enumerate(sections):
        if heading.startswith("## "):
            heading_text = heading[3:]  # strip "## "
            if _normalise_heading(heading_text) == target_norm:
                sections[idx] = (heading, f"\n\n{new_content}\n")
                found = True
                break

    if not found:
        # Append new section
        display_name = section_name.replace("_", " ")
        # Capitalise first letter of each word for a clean heading
        display_name = display_name.title() if display_name.islower() else display_name
        sections.append((f"## {display_name}", f"\n\n{new_content}\n"))

    # Reassemble
    result = "".join(h + b for h, b in sections)
    atomic_write(path, result)


# ── Append-only log ─────────────────────────────────────────────────────────


def append_entry(path: Path, entry: str) -> None:
    """Append a dated entry to an append-only log file (e.g. decisions.md).

    Each entry gets a ``## YYYY-MM-DD`` heading with today's date.

    Args:
        path: File path (created if missing).
        entry: Entry text to append.
    """
    path = Path(path)
    existing = read_source_file(path)
    today = datetime.now().strftime("%Y-%m-%d")

    new_section = f"## {today}\n\n{entry}\n"

    if existing:
        combined = existing.rstrip("\n") + "\n\n" + new_section
    else:
        combined = new_section

    atomic_write(path, combined)


# ── Entry retrieval ──────────────────────────────────────────────────────────


def get_recent_entries(path: Path, n: int = 7) -> list[str]:
    """Return the last *n* ``## ``-headed entries, most recent first.

    Args:
        path: File path to read.
        n: Number of entries to return (default 7).

    Returns:
        List of entry bodies (including the ``## `` heading line), most recent
        first. Empty list if the file is missing or has no entries.
    """
    path = Path(path)
    text = read_source_file(path)
    if not text:
        return []

    sections = _split_sections(text)
    # Keep only real ## entries (skip preamble)
    entries = [(h, b) for h, b in sections if h.startswith("## ")]

    # Take last n, reverse so most recent is first
    last_n = entries[-n:] if n < len(entries) else entries
    last_n.reverse()

    return [(h + b).strip() for h, b in last_n]


# ── Archival ─────────────────────────────────────────────────────────────────


def archive_old_entries(
    path: Path,
    archive_path: Path,
    max_age_days: int = 90,
) -> None:
    """Move entries older than *max_age_days* from *path* to *archive_path*.

    Entries must have ``## YYYY-MM-DD`` headings. Recent entries stay in the
    source file. Archived entries are appended to the archive file.

    Args:
        path: Source file with dated entries.
        archive_path: Destination archive file (created/appended).
        max_age_days: Entries older than this many days are archived.
    """
    path = Path(path)
    archive_path = Path(archive_path)

    text = read_source_file(path)
    if not text:
        return

    cutoff = datetime.now() - timedelta(days=max_age_days)
    sections = _split_sections(text)
    date_re = re.compile(r"^## (\d{4}-\d{2}-\d{2})")

    keep: list[tuple[str, str]] = []
    archive: list[tuple[str, str]] = []

    for heading, body in sections:
        m = date_re.match(heading)
        if m:
            entry_date = datetime.strptime(m.group(1), "%Y-%m-%d")
            if entry_date < cutoff:
                archive.append((heading, body))
            else:
                keep.append((heading, body))
        else:
            # Preamble or non-dated section stays in the source
            keep.append((heading, body))

    if not archive:
        return  # nothing to archive

    # Write archived entries to archive file
    archive_text = "".join(h + b for h, b in archive).strip() + "\n"
    existing_archive = read_source_file(archive_path)
    if existing_archive:
        combined_archive = existing_archive.rstrip("\n") + "\n\n" + archive_text
    else:
        combined_archive = archive_text
    atomic_write(archive_path, combined_archive)

    # Rewrite source with only the kept entries
    kept_text = "".join(h + b for h, b in keep).strip() + "\n"
    atomic_write(path, kept_text)
