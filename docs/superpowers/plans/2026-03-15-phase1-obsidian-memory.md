# Phase 1: Obsidian Memory + Evolving Identity — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Obsidian-visible memory with evolving identity files, Jinja2 mirror generation, EVOLVE + MIRROR pipeline phases, Agent Reach research tools, and LinkedIn engagement discovery.

**Architecture:** SQLite stays primary for structured data. 4 source-of-truth markdown files (soul, user, voice, decisions) live in the Obsidian vault and are read/written directly by the pipeline. All other vault files are generated mirrors rebuilt from SQLite after each run using Jinja2 templates. Two new pipeline phases (EVOLVE, MIRROR) run after ENGAGEMENT and before SYNC.

**Tech Stack:** Python 3.14, SQLite, Jinja2, fastembed, pytest, Agent Reach (xreach, yt-dlp, feedparser, Jina Reader), Exa search

**Spec:** `docs/superpowers/specs/2026-03-15-obsidian-memory-evolution-design.md`

**Parallel Workstreams:**
```
A (vault/mirror) ← B (evolve + prompt updates)
C (agent reach) ← D (linkedin engagement)
```
A and C can be built in parallel. B starts after A. D starts after C.

---

## Chunk 1: Workstream A — Vault, Templates, Mirror

### Task 1: `memory/vault.py` — Atomic read/write for markdown files

**Files:**
- Create: `memory/vault.py`
- Create: `tests/test_vault.py`

- [ ] **Step 1: Write failing tests for vault read/write**

```python
# tests/test_vault.py
import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def vault_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestAtomicWrite:
    def test_write_creates_file(self, vault_dir):
        from memory.vault import atomic_write
        path = vault_dir / "test.md"
        atomic_write(path, "# Hello\n\nContent here.")
        assert path.exists()
        assert path.read_text() == "# Hello\n\nContent here."

    def test_write_is_utf8_lf(self, vault_dir):
        from memory.vault import atomic_write
        path = vault_dir / "test.md"
        atomic_write(path, "Héllo wörld\nLine 2")
        raw = path.read_bytes()
        assert b"\r\n" not in raw  # no CRLF
        assert raw.decode("utf-8")  # valid UTF-8

    def test_write_overwrites_existing(self, vault_dir):
        from memory.vault import atomic_write
        path = vault_dir / "test.md"
        atomic_write(path, "version 1")
        atomic_write(path, "version 2")
        assert path.read_text() == "version 2"

    def test_write_creates_parent_dirs(self, vault_dir):
        from memory.vault import atomic_write
        path = vault_dir / "sub" / "dir" / "test.md"
        atomic_write(path, "nested")
        assert path.read_text() == "nested"


class TestReadSourceOfTruth:
    def test_read_existing_file(self, vault_dir):
        from memory.vault import atomic_write, read_source_file
        path = vault_dir / "soul.md"
        atomic_write(path, "# Soul\n\n## Values\nBe good.")
        content = read_source_file(path)
        assert "Be good." in content

    def test_read_missing_file_returns_empty(self, vault_dir):
        from memory.vault import read_source_file
        content = read_source_file(vault_dir / "missing.md")
        assert content == ""


class TestSectionUpdate:
    def test_update_existing_section(self, vault_dir):
        from memory.vault import atomic_write, update_section
        path = vault_dir / "soul.md"
        atomic_write(path, "# Soul\n\n## Values\nOld values.\n\n## Preferences\nOld prefs.")
        update_section(path, "Values", "New values.")
        content = path.read_text()
        assert "New values." in content
        assert "Old values." not in content
        assert "Old prefs." in content  # other sections unchanged

    def test_update_missing_section_appends(self, vault_dir):
        from memory.vault import atomic_write, update_section
        path = vault_dir / "soul.md"
        atomic_write(path, "# Soul\n\n## Values\nStuff.")
        update_section(path, "New Section", "New content.")
        content = path.read_text()
        assert "## New Section" in content
        assert "New content." in content
        assert "Stuff." in content

    def test_update_case_insensitive_match(self, vault_dir):
        from memory.vault import atomic_write, update_section
        path = vault_dir / "soul.md"
        atomic_write(path, "# Soul\n\n## Learned Preferences\nOld.")
        update_section(path, "learned_preferences", "Updated.")
        content = path.read_text()
        assert "Updated." in content

    def test_update_enforces_max_length(self, vault_dir):
        from memory.vault import atomic_write, update_section
        path = vault_dir / "soul.md"
        atomic_write(path, "# Soul\n\n## Values\nOld.")
        long_content = "x" * 600
        with pytest.raises(ValueError, match="exceeds max"):
            update_section(path, "Values", long_content)


class TestAppendEntry:
    def test_append_adds_dated_entry(self, vault_dir):
        from memory.vault import atomic_write, append_entry
        path = vault_dir / "decisions.md"
        atomic_write(path, "# Decisions\n")
        append_entry(path, "## 2026-03-15\nTopic selected: AI security (8.2)")
        content = path.read_text()
        assert "## 2026-03-15" in content
        assert "AI security" in content

    def test_append_preserves_existing(self, vault_dir):
        from memory.vault import atomic_write, append_entry
        path = vault_dir / "decisions.md"
        atomic_write(path, "# Decisions\n\n## 2026-03-14\nOld entry.")
        append_entry(path, "## 2026-03-15\nNew entry.")
        content = path.read_text()
        assert "Old entry." in content
        assert "New entry." in content


class TestGetRecentEntries:
    def test_get_last_n_entries(self, vault_dir):
        from memory.vault import atomic_write, get_recent_entries
        path = vault_dir / "decisions.md"
        entries = "# Decisions\n\n## 2026-03-13\nDay 1.\n\n## 2026-03-14\nDay 2.\n\n## 2026-03-15\nDay 3."
        atomic_write(path, entries)
        recent = get_recent_entries(path, n=2)
        assert len(recent) == 2
        assert "Day 3." in recent[0]
        assert "Day 2." in recent[1]


class TestArchiveOldEntries:
    def test_archive_entries_older_than_days(self, vault_dir):
        from memory.vault import atomic_write, archive_old_entries
        path = vault_dir / "decisions.md"
        archive_path = vault_dir / "decisions-archive.md"
        old_date = "2025-01-01"
        recent_date = "2026-03-15"
        content = f"# Decisions\n\n## {old_date}\nOld.\n\n## {recent_date}\nRecent."
        atomic_write(path, content)
        archive_old_entries(path, archive_path, max_age_days=90)
        main = path.read_text()
        archive = archive_path.read_text()
        assert old_date not in main
        assert recent_date in main
        assert old_date in archive
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_vault.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memory.vault'`

- [ ] **Step 3: Implement `memory/vault.py`**

```python
# memory/vault.py
"""Atomic read/write for Obsidian vault markdown files.

Source-of-truth files (soul.md, user.md, voice.md, decisions.md) are read
directly by pipeline agents and updated by the EVOLVE phase. All writes
use atomic rename to prevent corruption when Obsidian has files open.
"""

import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Max characters for a single section update (safety guardrail)
MAX_SECTION_LENGTH = 500


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (write tmp, then rename).

    Creates parent directories if needed. Always UTF-8, LF line endings.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize to LF
    content = content.replace("\r\n", "\n")

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp", prefix=".vault_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_source_file(path: Path) -> str:
    """Read a source-of-truth markdown file. Returns '' if missing."""
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _parse_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) tuples by ## boundaries.

    Returns list of (heading_text, section_body) where heading_text is
    the text after '## ' and body is everything until the next '## ' or EOF.
    The content before the first ## is returned with heading_text = ''.
    """
    parts = re.split(r"\n(?=## )", content)
    sections = []
    for part in parts:
        match = re.match(r"^## (.+)\n(.*)", part, re.DOTALL)
        if match:
            sections.append((match.group(1).strip(), match.group(2)))
        else:
            sections.append(("", part))
    return sections


def _normalize_heading(heading: str) -> str:
    """Normalize heading for case-insensitive matching.

    'Learned Preferences' and 'learned_preferences' both match.
    """
    return heading.lower().replace("_", " ").strip()


def update_section(path: Path, section_name: str, new_content: str) -> None:
    """Update a specific ## section in a markdown file.

    If section exists, replaces its body. If not, appends new section.
    Raises ValueError if new_content exceeds MAX_SECTION_LENGTH.
    """
    if len(new_content) > MAX_SECTION_LENGTH:
        raise ValueError(
            f"Section content ({len(new_content)} chars) exceeds max "
            f"({MAX_SECTION_LENGTH} chars)"
        )

    content = read_source_file(path)
    sections = _parse_sections(content)
    target = _normalize_heading(section_name)

    # Try to find and replace existing section
    found = False
    for i, (heading, body) in enumerate(sections):
        if _normalize_heading(heading) == target:
            sections[i] = (heading, new_content.strip() + "\n")
            found = True
            break

    if not found:
        # Convert underscores to title case for new heading
        display_name = section_name.replace("_", " ").title()
        sections.append((display_name, new_content.strip() + "\n"))

    # Rebuild file
    parts = []
    for heading, body in sections:
        if heading:
            parts.append(f"## {heading}\n{body}")
        else:
            parts.append(body)

    atomic_write(path, "\n".join(parts))


def append_entry(path: Path, entry: str) -> None:
    """Append a dated entry to an append-only file (e.g. decisions.md)."""
    content = read_source_file(path)
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n" + entry.strip() + "\n"
    atomic_write(path, content)


def get_recent_entries(path: Path, n: int = 7) -> list[str]:
    """Get the last N ## entries from an append-only file.

    Returns list of entry bodies, most recent first.
    """
    content = read_source_file(path)
    if not content:
        return []

    sections = _parse_sections(content)
    # Filter to only dated sections (those with ## headings)
    dated = [(h, b) for h, b in sections if h]
    # Return last N, reversed (most recent first)
    return [f"## {h}\n{b}" for h, b in dated[-n:][::-1]]


def archive_old_entries(
    path: Path, archive_path: Path, max_age_days: int = 90
) -> None:
    """Move entries older than max_age_days to archive file."""
    content = read_source_file(path)
    if not content:
        return

    cutoff = datetime.now() - timedelta(days=max_age_days)
    sections = _parse_sections(content)

    keep = []
    archive = []
    for heading, body in sections:
        if not heading:
            keep.append(("", body))
            continue
        # Try to parse date from heading (## YYYY-MM-DD)
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", heading)
        if date_match:
            entry_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            if entry_date < cutoff:
                archive.append((heading, body))
                continue
        keep.append((heading, body))

    if not archive:
        return

    # Write archived entries
    existing_archive = read_source_file(archive_path)
    archive_content = existing_archive
    for heading, body in archive:
        archive_content += f"\n## {heading}\n{body}"
    atomic_write(archive_path, archive_content)

    # Rewrite main file without archived entries
    parts = []
    for heading, body in keep:
        if heading:
            parts.append(f"## {heading}\n{body}")
        else:
            parts.append(body)
    atomic_write(path, "\n".join(parts))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_vault.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add memory/vault.py tests/test_vault.py
git commit -m "feat: add memory/vault.py — atomic read/write for Obsidian markdown files"
```

---

### Task 2: Seed the 4 source-of-truth files

**Files:**
- Create: `data/ramsay/mindpattern/soul.md`
- Create: `data/ramsay/mindpattern/user.md`
- Create: `data/ramsay/mindpattern/voice.md` (copy from `agents/voice-guide.md`)
- Create: `data/ramsay/mindpattern/decisions.md`
- Create: `data/ramsay/mindpattern/daily/_index.md`
- Create: `data/ramsay/mindpattern/topics/_index.md`
- Create: `data/ramsay/mindpattern/sources/_index.md`
- Create: `data/ramsay/mindpattern/social/_index.md`
- Create: `data/ramsay/mindpattern/people/_index.md`

- [ ] **Step 1: Create soul.md**

Seed from v2 SOUL.md + current pipeline behavior. File must have YAML frontmatter with `type: identity`, `date`, `tags: [soul, identity]`. Sections: `## Core Values`, `## Personality`, `## Learned Preferences`, `## Self Assessment`, `## Evolution Log`. Read `/Users/taylerramsay/Projects/daily-research-agent-v2/SOUL.md` for initial content, adapt for v3.

- [ ] **Step 2: Create user.md**

Seed from `agents/voice-guide.md` bio section + known user preferences. YAML frontmatter: `type: identity`, `date`, `tags: [user, profile]`. Sections: `## Background`, `## Current Stack`, `## Interests`, `## Communication Preferences`, `## Observed Patterns`, `## Kill Switches`.

- [ ] **Step 3: Create voice.md**

Copy `agents/voice-guide.md` contents. Add YAML frontmatter: `type: identity`, `date`, `tags: [voice, persona]`. Keep all existing sections.

- [ ] **Step 4: Create decisions.md**

Empty starter. YAML frontmatter: `type: decisions`, `date`, `tags: [decisions, editorial]`. Body: `# Editorial Decisions\n\nAppend-only log of editorial decisions made by the pipeline.\n`

- [ ] **Step 5: Create _index.md for each subfolder**

Each `_index.md` has YAML frontmatter `type: index`, links to all files in its folder (initially empty links — MIRROR phase will populate), and a Dataview query block. Create for: `daily/`, `topics/`, `sources/`, `social/`, `people/`.

- [ ] **Step 6: Commit**

```bash
git add data/ramsay/mindpattern/
git commit -m "feat: seed Obsidian vault with source-of-truth files and folder indexes"
```

---

### Task 3: Jinja2 templates for mirror files

**Files:**
- Create: `memory/templates/daily.md.j2`
- Create: `memory/templates/topic.md.j2`
- Create: `memory/templates/source.md.j2`
- Create: `memory/templates/posts.md.j2`
- Create: `memory/templates/corrections.md.j2`
- Create: `memory/templates/engagement-log.md.j2`
- Create: `memory/templates/engaged-authors.md.j2`
- Create: `memory/templates/index.md.j2`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write failing tests for template rendering**

```python
# tests/test_templates.py
import pytest
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "memory" / "templates"


@pytest.fixture
def env():
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


class TestDailyTemplate:
    def test_renders_with_agents_and_findings(self, env):
        tmpl = env.get_template("daily.md.j2")
        result = tmpl.render(
            date="2026-03-15",
            agents_run=3,
            findings_count=25,
            posts=["bluesky", "linkedin"],
            agents=[
                {
                    "name": "ai-frontiers-researcher",
                    "focus": "Claude Code adoption",
                    "findings": [
                        {"title": "Claude Code writes 4% of GitHub", "importance": "HIGH"},
                    ],
                    "decision": "Prioritized broad appeal stat",
                    "sources": ["Anthropic blog"],
                },
            ],
            social={"topic": "AI security", "expeditor": "PASS", "posts": [{"platform": "bluesky", "url": "https://bsky.app/..."}]},
            engagement={"candidates_found": 5, "replies_drafted": 2},
            evolution={"soul": "no changes", "user": "added pattern"},
        )
        assert "---" in result  # has frontmatter
        assert "type: daily" in result
        assert "ai-frontiers-researcher" in result
        assert "[[" in result  # has wiki-links

    def test_renders_with_empty_data(self, env):
        tmpl = env.get_template("daily.md.j2")
        result = tmpl.render(
            date="2026-03-15", agents_run=0, findings_count=0,
            posts=[], agents=[], social={}, engagement={}, evolution={},
        )
        assert "type: daily" in result


class TestTopicTemplate:
    def test_renders_with_findings_and_links(self, env):
        tmpl = env.get_template("topic.md.j2")
        result = tmpl.render(
            name="AI Security",
            slug="ai-security",
            date="2026-03-15",
            first_seen="2026-02-01",
            finding_count=42,
            tags=["topic", "security", "ai"],
            findings=[
                {"title": "McKinsey breach", "date": "2026-03-15", "importance": "HIGH"},
            ],
            sources=[{"name": "CrowdStrike", "slug": "crowdstrike"}],
            related_topics=[{"name": "Agent Tooling", "slug": "agent-tooling"}],
            posts=[{"date": "2026-03-15", "platform": "bluesky"}],
        )
        assert "type: topic" in result
        assert "[[sources/crowdstrike]]" in result or "[[sources/crowdstrike|" in result
        assert "[[topics/agent-tooling]]" in result or "[[topics/agent-tooling|" in result


class TestSourceTemplate:
    def test_renders_with_url_and_topics(self, env):
        tmpl = env.get_template("source.md.j2")
        result = tmpl.render(
            name="CrowdStrike",
            slug="crowdstrike",
            date="2026-03-15",
            url="https://crowdstrike.com",
            finding_count=15,
            eic_selection_rate=0.4,
            tags=["source"],
            topics=[{"name": "AI Security", "slug": "ai-security"}],
            recent_findings=[{"title": "25% vuln rate", "date": "2026-03-15"}],
        )
        assert "type: source" in result
        assert "crowdstrike.com" in result
        assert "[[topics/ai-security" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_templates.py -v`
Expected: FAIL — template files not found

- [ ] **Step 3: Create all Jinja2 templates**

Create each `.md.j2` template in `memory/templates/`. Each template outputs valid Obsidian markdown with YAML frontmatter, wiki-links, and proper formatting. Templates use `{{ variable }}` for values and `{% for %}` loops for lists.

Key requirements:
- Every template starts with `---\n` YAML frontmatter block
- Every template includes at least one `[[wiki-link]]`
- Quote YAML values containing colons
- Use kebab-case for link targets
- Daily template links to `[[topics/{slug}]]` and `[[sources/{slug}]]`
- Topic template links to `[[daily/{date}]]`, `[[sources/{slug}]]`, `[[topics/{slug}]]`
- Source template links to `[[topics/{slug}]]`, `[[daily/{date}]]`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_templates.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add memory/templates/ tests/test_templates.py
git commit -m "feat: add Jinja2 templates for Obsidian mirror files"
```

---

### Task 4: `memory/mirror.py` — MIRROR phase (SQLite → markdown)

**Files:**
- Create: `memory/mirror.py`
- Create: `tests/test_mirror.py`

- [ ] **Step 1: Write failing tests for mirror generation**

Test that `generate_mirrors()` queries SQLite and produces markdown files in the vault directory. Use in-memory SQLite with test data. Verify:
- `daily/2026-03-15.md` is created with correct frontmatter
- `topics/*.md` files are created for each topic cluster
- `sources/*.md` files are created for each source
- `social/posts.md`, `corrections.md`, `engagement-log.md` are created
- `people/engaged-authors.md` is created
- All files contain at least one `[[wiki-link]]`
- `_index.md` files in each subfolder are updated with links to all files
- decisions.md archival runs (moves entries older than 90 days)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_mirror.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memory.mirror'`

- [ ] **Step 3: Implement `memory/mirror.py`**

The `generate_mirrors()` function:
1. Accepts `db` (sqlite3.Connection), `vault_dir` (Path), `date_str` (str)
2. Loads Jinja2 templates from `memory/templates/`
3. Queries SQLite for findings, sources, topics, social posts, corrections, engagements
4. Groups findings into topic clusters (by agent or by semantic similarity tag)
5. Renders each template with query results
6. Writes each file atomically via `vault.atomic_write()`
7. Updates `_index.md` in each subfolder with links to all generated files
8. Runs `vault.archive_old_entries()` on decisions.md

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_mirror.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add memory/mirror.py tests/test_mirror.py
git commit -m "feat: add memory/mirror.py — generate Obsidian files from SQLite"
```

---

### Task 5: Wire MIRROR phase into pipeline

**Files:**
- Modify: `orchestrator/pipeline.py` — add Phase.EVOLVE, Phase.MIRROR to enum + PHASE_ORDER + SKIPPABLE_PHASES
- Modify: `orchestrator/runner.py` — add `_phase_evolve()` and `_phase_mirror()` handler methods

- [ ] **Step 1: Add phases to pipeline.py**

Add `EVOLVE = "evolve"` and `MIRROR = "mirror"` to `Phase` enum. Insert between ENGAGEMENT and SYNC in `PHASE_ORDER`. Add both to `SKIPPABLE_PHASES`.

- [ ] **Step 2: Add `_phase_mirror()` to runner.py**

Wire `Phase.MIRROR: self._phase_mirror` in the phase handlers dict. Implementation calls `memory.mirror.generate_mirrors(self.db, vault_dir, self.date_str)` where `vault_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern"`.

- [ ] **Step 3: Add stub `_phase_evolve()` to runner.py**

Wire `Phase.EVOLVE: self._phase_evolve`. Stub implementation: `logger.info("EVOLVE phase: stub (implemented in Workstream B)")`. Returns empty dict.

- [ ] **Step 4: Run existing tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v`
Expected: All existing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/pipeline.py orchestrator/runner.py
git commit -m "feat: wire EVOLVE + MIRROR phases into pipeline state machine"
```

---

## Chunk 2: Workstream B — Identity Evolution + Prompt Updates

### Task 6: `memory/identity_evolve.py` — EVOLVE phase

**Files:**
- Create: `memory/identity_evolve.py`
- Create: `tests/test_identity_evolve.py`

- [ ] **Step 1: Write failing tests for evolve logic**

Test `apply_evolution_diff()` — takes a JSON diff dict, validates schema, applies to vault files:
- Valid diff updates a section in soul.md
- Valid diff appends to decisions.md
- Malformed JSON raises no exception, returns error dict
- Unknown keys in diff are rejected
- Content exceeding 500 chars is rejected
- `action: "none"` makes no changes

Test `build_evolve_prompt()` — builds the LLM prompt from current files + pipeline results:
- Includes current soul.md content
- Includes last 7 decisions entries
- Includes today's pipeline results
- Output is a string prompt

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_identity_evolve.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `memory/identity_evolve.py`**

Two public functions:
- `build_evolve_prompt(vault_dir, pipeline_results)` → str (the prompt for the Sonnet call)
- `apply_evolution_diff(vault_dir, diff_json)` → dict (result with changes applied or errors)

The runner's `_phase_evolve()` will:
1. Call `build_evolve_prompt()` to get the LLM prompt
2. Call `run_claude_prompt()` with the prompt
3. Parse JSON from the LLM output
4. Call `apply_evolution_diff()` with the parsed JSON

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_identity_evolve.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add memory/identity_evolve.py tests/test_identity_evolve.py
git commit -m "feat: add memory/identity_evolve.py — LLM-driven identity file evolution"
```

---

### Task 7: Wire EVOLVE phase into runner.py

**Files:**
- Modify: `orchestrator/runner.py` — replace stub `_phase_evolve()` with real implementation

- [ ] **Step 1: Implement `_phase_evolve()` in runner.py**

Replace the stub with:
1. Build prompt via `identity_evolve.build_evolve_prompt()`
2. Call `run_claude_prompt()` with task_type="evolve"
3. Parse JSON from output (with try/except — malformed = skip)
4. Call `identity_evolve.apply_evolution_diff()`
5. Log what changed

- [ ] **Step 2: Run existing tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: wire real EVOLVE phase — LLM updates identity files each run"
```

---

### Task 8: Update agent prompts to read from vault

**Files:**
- Modify: `social/writers.py` — change voice guide path
- Modify: `social/critics.py` — change voice guide path
- Modify: `agents/eic.md` — add soul.md + user.md reading instructions
- Modify: `agents/bluesky-writer.md` — reference voice.md
- Modify: `agents/linkedin-writer.md` — reference voice.md
- Remove: `agents/voice-guide.md` (after voice.md is confirmed working)

- [ ] **Step 1: Update `_VOICE_GUIDE_PATH` in `social/writers.py`**

Change from `PROJECT_ROOT / "agents" / "voice-guide.md"` to `PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"`.

- [ ] **Step 2: Update voice guide path in `social/critics.py`**

Change `voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"` to `PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"` in `review_draft()` and `expedite()`.

- [ ] **Step 3: Update EIC prompt to read soul.md + user.md**

In `agents/eic.md`, add instructions to read `data/ramsay/mindpattern/soul.md` and `data/ramsay/mindpattern/user.md` at the beginning of the process, before loading findings.

- [ ] **Step 4: Update writer agent files**

In `agents/bluesky-writer.md` and `agents/linkedin-writer.md`, add reference to `data/ramsay/mindpattern/voice.md` as the voice guide source.

- [ ] **Step 5: Verify voice.md exists and matches old voice-guide.md**

Confirm `data/ramsay/mindpattern/voice.md` has the same content as `agents/voice-guide.md`. Then delete `agents/voice-guide.md`.

- [ ] **Step 6: Run existing tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add social/writers.py social/critics.py agents/eic.md agents/bluesky-writer.md agents/linkedin-writer.md
git rm agents/voice-guide.md
git commit -m "feat: switch all agents to read voice.md from Obsidian vault"
```

---

## Chunk 3: Workstream C — Agent Reach

### Task 9: Install Agent Reach

**Files:**
- No code files — system installation

- [ ] **Step 1: Install Agent Reach**

Run: `pip install https://github.com/Panniantong/agent-reach/archive/main.zip`
Then: `agent-reach install --env=auto`

- [ ] **Step 2: Verify installation**

Run: `agent-reach doctor`
Expected: Shows available channels (Web, Twitter/X, YouTube, RSS, GitHub at minimum)

- [ ] **Step 3: Test key tools**

Run each to verify they work:
- `curl -s https://r.jina.ai/https://anthropic.com | head -20` (Jina Reader)
- `yt-dlp --dump-json --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))"` (yt-dlp)
- `python3 -c "import feedparser; print(feedparser.parse('https://blog.anthropic.com/rss').entries[0].title)"` (feedparser)

- [ ] **Step 4: Commit (add agent-reach to requirements if applicable)**

```bash
git commit -m "chore: install Agent Reach for expanded research capabilities"
```

---

### Task 10: Update research agent prompts with Agent Reach tools

**Files:**
- Modify: All 13 files in `verticals/ai-tech/agents/*.md`

- [ ] **Step 1: Add Agent Reach tool instructions to each research agent**

Append a new `## Available Research Tools` section to each agent .md file with instructions for using:
- `curl https://r.jina.ai/URL` — read any web page as clean markdown
- `xreach tweet URL --json` — read a tweet
- `xreach search "query" --json` — search Twitter/X
- `yt-dlp --dump-json --skip-download URL` — get YouTube video info + subtitles
- `python3 -c "import feedparser; ..."` — parse RSS feeds

Include examples and when to use each tool.

- [ ] **Step 2: Test one agent manually**

Run a single research agent with the updated prompt to verify it can use Agent Reach tools.

- [ ] **Step 3: Commit**

```bash
git add verticals/ai-tech/agents/
git commit -m "feat: add Agent Reach tool instructions to all research agents"
```

---

## Chunk 4: Workstream D — LinkedIn Engagement

### Task 11: Add `search_via_exa()` to engagement pipeline

**Files:**
- Modify: `social/engagement.py`
- Create: `tests/test_engagement_linkedin.py`

- [ ] **Step 1: Write failing tests for Exa search helper**

```python
# tests/test_engagement_linkedin.py
from unittest.mock import patch, MagicMock
import pytest


class TestSearchViaExa:
    @patch("subprocess.run")
    def test_returns_normalized_results(self, mock_run):
        from social.engagement import search_via_exa
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"url": "https://linkedin.com/posts/abc", "title": "AI post", "text": "Great discussion about AI agents"}]',
        )
        results = search_via_exa("AI agents", max_results=5)
        assert len(results) >= 1
        assert "url" in results[0]
        assert "text" in results[0]
        assert results[0]["platform"] == "linkedin"

    @patch("subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        from social.engagement import search_via_exa
        results = search_via_exa("AI agents")
        assert results == []


class TestLinkedInEngagement:
    @patch("social.engagement.search_via_exa")
    def test_linkedin_candidates_found(self, mock_search):
        mock_search.return_value = [
            {
                "url": "https://linkedin.com/posts/abc",
                "title": "AI agents discussion",
                "text": "Really interesting findings on agent security...",
                "platform": "linkedin",
                "author_handle": "john-smith",
                "followers_count": 500,
                "like_count": 10,
            }
        ]
        # Test that _find_candidates includes LinkedIn results
        # when "linkedin" is in engagement platforms config
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_engagement_linkedin.py -v`
Expected: FAIL — `search_via_exa` not defined

- [ ] **Step 3: Implement `search_via_exa()` in engagement.py**

Add function that:
1. Calls Exa CLI via subprocess: `agent-reach search "query" --site linkedin.com --json`
2. Parses JSON output
3. For each result, calls Jina Reader to get full content: `curl -s https://r.jina.ai/{url}`
4. Normalizes to the same dict format as `BlueskyClient.search()` returns
5. Returns list of normalized post dicts

- [ ] **Step 4: Wire LinkedIn into `_find_candidates()`**

In `_find_candidates()`, check if "linkedin" is in `self._platform_clients` or engagement config platforms. If so, call `search_via_exa()` instead of `client.search()` and skip the connection filter (no LinkedIn relationship API).

- [ ] **Step 5: Handle LinkedIn in `_post_engagement()` — draft-only mode**

When platform is "linkedin", instead of calling `client.reply()`:
1. Save the drafted reply to `data/social-drafts/engagement-linkedin.json`
2. Send the draft via iMessage for manual posting
3. Log as `status="drafted"` not `status="posted"`

- [ ] **Step 6: Update social-config.json**

Change `"engagement": {"platforms": ["bluesky"]}` to `"engagement": {"platforms": ["bluesky", "linkedin"]}`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_engagement_linkedin.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add social/engagement.py tests/test_engagement_linkedin.py social-config.json
git commit -m "feat: add LinkedIn engagement discovery via Exa search + Jina Reader"
```

---

## Chunk 5: Integration + Jinja2 dependency + E2E validation

### Task 12: Add Jinja2 dependency

**Files:**
- Modify: `requirements.txt` (or create if not exists)

- [ ] **Step 1: Install Jinja2**

Run: `pip install jinja2`

- [ ] **Step 2: Add to requirements.txt**

Add `jinja2>=3.1` to the project's requirements file.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add jinja2 dependency for Obsidian template rendering"
```

---

### Task 13: Export new functions from `memory/__init__.py`

**Files:**
- Modify: `memory/__init__.py`

- [ ] **Step 1: Add exports for vault, mirror, identity_evolve**

Add imports for the new public functions so the pipeline can call `memory.generate_mirrors()`, etc.

- [ ] **Step 2: Run existing tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add memory/__init__.py
git commit -m "feat: export vault, mirror, identity_evolve from memory module"
```

---

### Task 14: Full E2E validation

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v`
Expected: All PASS including new tests

- [ ] **Step 2: Run social pipeline E2E**

Run the real social pipeline (same command as today's successful test). Verify:
- EVOLVE phase runs (may log "no changes" on first run — that's fine)
- MIRROR phase generates files in `data/ramsay/mindpattern/`
- Daily log is created
- Obsidian can open the vault and show files + graph

- [ ] **Step 3: Verify Obsidian vault**

Open Obsidian, point at `data/ramsay/mindpattern/`. Check:
- soul.md, user.md, voice.md, decisions.md visible
- Daily log visible with today's date
- Graph view shows connected nodes
- No orphan files (every file has at least one link)

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "feat: Phase 1 complete — Obsidian memory, evolving identity, Agent Reach, LinkedIn engagement"
```

---

## Summary

| Task | Workstream | Files | Est. Steps |
|------|-----------|-------|-----------|
| 1. vault.py | A | 2 new | 5 |
| 2. Seed files | A | 9 new | 6 |
| 3. Templates | A | 9 new | 5 |
| 4. mirror.py | A | 2 new | 5 |
| 5. Pipeline wiring | A | 2 modified | 5 |
| 6. identity_evolve.py | B | 2 new | 5 |
| 7. Wire EVOLVE | B | 1 modified | 3 |
| 8. Agent prompts | B | 7 modified, 1 removed | 7 |
| 9. Install Agent Reach | C | 0 | 4 |
| 10. Research prompts | C | 13 modified | 3 |
| 11. LinkedIn engagement | D | 2 modified, 1 new | 8 |
| 12. Jinja2 dep | — | 1 modified | 3 |
| 13. Module exports | — | 1 modified | 3 |
| 14. E2E validation | — | 0 | 4 |

**Parallel execution:** Tasks 1-5 (Workstream A) and Tasks 9-10 (Workstream C) can run simultaneously. Tasks 6-8 (Workstream B) start after A completes. Task 11 (Workstream D) starts after C completes. Tasks 12-14 run last.
