"""Tests for harness/knowledge_sections.py — pure algorithm tests.

Uses temporary directories with synthetic knowledge files.
No network, no API keys, no embeddings required.
"""

import textwrap
from pathlib import Path

import pytest

from harness.knowledge_sections import (
    CheckResult,
    CodeRef,
    Section,
    build_suffix_index,
    find_sections,
    flatten_sections,
    has_require_code_mention,
    levenshtein_distance,
    parse_sections,
    resolve_ref,
    scan_code_refs,
    strip_wiki_links_for_length,
    _scan_with_pathlib,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def knowledge_dir(tmp_path):
    """Create a temp knowledge directory with sample files."""
    kdir = tmp_path / "knowledge"
    kdir.mkdir()

    (kdir / "orchestrator-runner.md").write_text(textwrap.dedent("""\
        ## Key Functions

        The run_single_agent function dispatches work.

        ### run_single_agent

        Runs one agent in a subprocess.

        ## Error Handling

        Errors are caught and logged. See [[orchestrator/agents]].

        ## Dependencies

        Depends on [[orchestrator/agents]] and [[memory/vault]].
    """))

    (kdir / "orchestrator-agents.md").write_text(textwrap.dedent("""\
        ## Dispatch

        Agent dispatch logic. See [[orchestrator/runner]].

        ## Configuration

        Agent config from harness/config.json.
    """))

    (kdir / "memory-vault.md").write_text(textwrap.dedent("""\
        ## Atomic Write

        All writes use atomic write strategy.

        ## Section Operations

        Section split and update.
    """))

    (kdir / "INDEX.md").write_text(textwrap.dedent("""\
        # Knowledge Index

        - [[orchestrator/runner]] — Main pipeline
        - [[orchestrator/agents]] — Agent dispatch
        - [[memory/vault]] — Vault operations
    """))

    return kdir


@pytest.fixture
def slug_to_path(knowledge_dir):
    """Build slug→path mapping for the test knowledge dir."""
    return {
        "orchestrator/runner": str(knowledge_dir / "orchestrator-runner.md"),
        "orchestrator/agents": str(knowledge_dir / "orchestrator-agents.md"),
        "memory/vault": str(knowledge_dir / "memory-vault.md"),
    }


@pytest.fixture
def suffix_index(slug_to_path):
    return build_suffix_index(slug_to_path)


@pytest.fixture
def parsed_sections(knowledge_dir):
    """Parse all test files into sections."""
    sections = {}
    slugs = {
        "orchestrator-runner.md": "orchestrator/runner",
        "orchestrator-agents.md": "orchestrator/agents",
        "memory-vault.md": "memory/vault",
    }
    for fname, slug in slugs.items():
        path = knowledge_dir / fname
        text = path.read_text()
        sections[slug] = parse_sections(text, slug)
    return sections


@pytest.fixture
def section_index(parsed_sections):
    """Build flat section_id → Section lookup."""
    idx = {}
    for slug, tree in parsed_sections.items():
        for s in flatten_sections(tree):
            idx[s.id] = s
    return idx


# ══════════════════════════════════════════════════════════════════════
# 1. Section Tree Parser
# ══════════════════════════════════════════════════════════════════════

class TestParseSections:
    def test_basic_sections(self):
        text = "## Alpha\n\nFirst section.\n\n## Beta\n\nSecond section.\n"
        sections = parse_sections(text, "test/file")
        assert len(sections) == 2
        assert sections[0].heading == "Alpha"
        assert sections[1].heading == "Beta"

    def test_nested_headings(self):
        text = "## Parent\n\nIntro.\n\n### Child\n\nChild content.\n"
        sections = parse_sections(text, "test/file")
        assert len(sections) == 1
        assert sections[0].heading == "Parent"
        assert len(sections[0].children) == 1
        assert sections[0].children[0].heading == "Child"

    def test_hierarchical_ids(self):
        text = "## Key Functions\n\nOverview.\n\n### run_single_agent\n\nRuns agent.\n"
        sections = parse_sections(text, "orchestrator/runner")
        assert sections[0].id == "orchestrator/runner#Key Functions"
        assert sections[0].children[0].id == "orchestrator/runner#Key Functions#run_single_agent"

    def test_first_paragraph_extraction(self):
        text = "## Section\n\nThis is the first paragraph.\n\nThis is the second.\n"
        sections = parse_sections(text, "test/file")
        assert sections[0].first_paragraph == "This is the first paragraph."

    def test_first_paragraph_truncation(self):
        long_para = "A" * 300
        text = f"## Section\n\n{long_para}\n"
        sections = parse_sections(text, "test/file")
        assert sections[0].first_paragraph.endswith("...")
        assert len(sections[0].first_paragraph) < 300

    def test_empty_section(self):
        text = "## Empty\n\n## Next\n\nContent here.\n"
        sections = parse_sections(text, "test/file")
        assert sections[0].heading == "Empty"
        assert sections[0].first_paragraph == ""

    def test_line_numbers(self):
        text = "## First\n\nLine 2 content.\n\n## Second\n\nLine 6 content.\n"
        sections = parse_sections(text, "test/file")
        assert sections[0].start_line == 1
        assert sections[1].start_line == 5

    def test_skip_code_block_headings(self):
        text = "## Real\n\nContent.\n\n```\n## Not A Heading\n```\n\n## Also Real\n\nMore.\n"
        sections = parse_sections(text, "test/file")
        assert len(sections) == 2
        assert sections[0].heading == "Real"
        assert sections[1].heading == "Also Real"

    def test_skip_frontmatter(self):
        text = "---\nrequire-code-mention: true\n---\n## Section\n\nContent.\n"
        sections = parse_sections(text, "test/file")
        assert len(sections) == 1
        assert sections[0].heading == "Section"

    def test_deeply_nested(self):
        text = "## L2\n\nA.\n\n### L3\n\nB.\n\n#### L4\n\nC.\n"
        sections = parse_sections(text, "test/file")
        assert len(sections) == 1
        child = sections[0].children[0]
        assert child.heading == "L3"
        grandchild = child.children[0]
        assert grandchild.heading == "L4"
        assert grandchild.id == "test/file#L2#L3#L4"

    def test_nested_end_line_not_less_than_start(self):
        """Nested sections must have end_line >= start_line."""
        text = (
            "## Parent\n"       # line 1
            "\n"                 # line 2
            "Parent intro.\n"   # line 3
            "\n"                 # line 4
            "### Child A\n"     # line 5
            "\n"                 # line 6
            "Child A body.\n"   # line 7
            "\n"                 # line 8
            "### Child B\n"     # line 9
            "\n"                 # line 10
            "Child B body.\n"   # line 11 (trailing \n adds line 12)
        )
        total_lines = len(text.split("\n"))  # 12 due to trailing newline
        sections = parse_sections(text, "test/file")
        parent = sections[0]
        assert parent.start_line == 1
        assert parent.end_line == total_lines  # encompasses all children
        # Children must have correct, non-inverted line ranges
        child_a = parent.children[0]
        child_b = parent.children[1]
        assert child_a.start_line == 5
        assert child_a.end_line >= child_a.start_line, (
            f"Child A end_line ({child_a.end_line}) < start_line ({child_a.start_line})"
        )
        assert child_a.end_line == 8  # ends before Child B starts
        assert child_b.start_line == 9
        assert child_b.end_line >= child_b.start_line, (
            f"Child B end_line ({child_b.end_line}) < start_line ({child_b.start_line})"
        )
        assert child_b.end_line == total_lines

    def test_real_knowledge_file(self, knowledge_dir):
        text = (knowledge_dir / "orchestrator-runner.md").read_text()
        sections = parse_sections(text, "orchestrator/runner")
        headings = [s.heading for s in sections]
        assert "Key Functions" in headings
        assert "Error Handling" in headings
        assert "Dependencies" in headings
        # Check nested
        key_fn = [s for s in sections if s.heading == "Key Functions"][0]
        assert any(c.heading == "run_single_agent" for c in key_fn.children)


# ══════════════════════════════════════════════════════════════════════
# 2. Suffix Index
# ══════════════════════════════════════════════════════════════════════

class TestSuffixIndex:
    def test_build_suffix_index(self, suffix_index):
        # Full slug should resolve
        assert "orchestrator/runner" in suffix_index
        # Short suffix should resolve
        assert "runner" in suffix_index

    def test_ambiguous_suffix(self, slug_to_path):
        # Add a second file with 'runner' suffix
        extended = dict(slug_to_path)
        extended["social/runner"] = "/fake/social-runner.md"
        idx = build_suffix_index(extended)
        # 'runner' now maps to 2 entries
        assert len(idx["runner"]) == 2

    def test_case_insensitive(self, suffix_index):
        assert "orchestrator/runner" in suffix_index
        # Index keys are already lowercased
        assert "ORCHESTRATOR/RUNNER".lower() in suffix_index

    def test_single_segment_slug(self):
        idx = build_suffix_index({"INDEX": "/fake/INDEX.md"})
        assert "index" in idx
        assert len(idx["index"]) == 1


# ══════════════════════════════════════════════════════════════════════
# 3. Ref Resolution
# ══════════════════════════════════════════════════════════════════════

class TestResolveRef:
    def test_exact_match(self, suffix_index):
        slug, sid, ambig = resolve_ref("orchestrator/runner", suffix_index)
        assert slug == "orchestrator/runner"
        assert not ambig

    def test_section_fragment(self, suffix_index, section_index):
        slug, sid, ambig = resolve_ref("orchestrator/runner#Error Handling", suffix_index, section_index)
        assert slug == "orchestrator/runner"
        assert sid == "orchestrator/runner#Error Handling"
        assert not ambig

    def test_suffix_expansion(self, suffix_index):
        slug, sid, ambig = resolve_ref("runner", suffix_index)
        assert slug == "orchestrator/runner"
        assert not ambig

    def test_ambiguous_detection(self, slug_to_path):
        extended = dict(slug_to_path)
        extended["social/runner"] = "/fake/social-runner.md"
        idx = build_suffix_index(extended)
        slug, sid, ambig = resolve_ref("runner", idx)
        assert ambig

    def test_broken_ref(self, suffix_index):
        slug, sid, ambig = resolve_ref("nonexistent/file", suffix_index)
        assert slug is None
        assert sid is None

    def test_broken_section_fragment(self, suffix_index, section_index):
        slug, sid, ambig = resolve_ref("orchestrator/runner#Nonexistent Section", suffix_index, section_index)
        assert slug == "orchestrator/runner"
        assert sid is None  # file found, section not


# ══════════════════════════════════════════════════════════════════════
# 4. Fuzzy Search (5-tier)
# ══════════════════════════════════════════════════════════════════════

class TestFindSections:
    @pytest.fixture
    def all_section_ids(self, section_index):
        return list(section_index.keys())

    def test_tier1_exact_match(self, all_section_ids):
        results = find_sections("orchestrator/runner#Key Functions", all_section_ids)
        assert len(results) > 0
        sid, tier, score = results[0]
        assert tier == 1
        assert score == 1.0

    def test_tier2_stem_expansion(self, all_section_ids):
        results = find_sections("runner", all_section_ids)
        assert any(tier == 2 for _, tier, _ in results)

    def test_tier3_tail_match(self, all_section_ids):
        results = find_sections("Dispatch", all_section_ids)
        assert any(tier == 3 for _, tier, _ in results)

    def test_tier4_subsequence(self, all_section_ids):
        results = find_sections("runner#run_single_agent", all_section_ids)
        assert any(tier <= 4 for _, tier, _ in results)

    def test_tier5_levenshtein(self, all_section_ids):
        # Slightly misspelled
        results = find_sections("Dispatc", all_section_ids)
        assert any(tier == 5 for _, tier, _ in results)

    def test_no_match_beyond_threshold(self, all_section_ids):
        results = find_sections("zzzzzzzzzzzzzzzzzzz", all_section_ids)
        assert len(results) == 0

    def test_tier_ordering(self, all_section_ids):
        results = find_sections("Key Functions", all_section_ids)
        tiers = [tier for _, tier, _ in results]
        assert tiers == sorted(tiers)

    def test_empty_query(self, all_section_ids):
        results = find_sections("", all_section_ids)
        assert len(results) == 0


# ══════════════════════════════════════════════════════════════════════
# 5. Levenshtein Distance
# ══════════════════════════════════════════════════════════════════════

class TestLevenshtein:
    def test_identical_strings(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "xyz") == 3

    def test_single_insertion(self):
        assert levenshtein_distance("cat", "cats") == 1

    def test_single_deletion(self):
        assert levenshtein_distance("cats", "cat") == 1

    def test_single_substitution(self):
        assert levenshtein_distance("cat", "car") == 1

    def test_known_distance(self):
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_symmetric(self):
        assert levenshtein_distance("abc", "xyz") == levenshtein_distance("xyz", "abc")


# ══════════════════════════════════════════════════════════════════════
# 6. Validation Helpers
# ══════════════════════════════════════════════════════════════════════

class TestCheckResult:
    def test_to_dict(self):
        r = CheckResult(passed=True, failures=[], warnings=["warn1"])
        d = r.to_dict()
        assert d["pass"] is True
        assert d["failures"] == []
        assert d["warnings"] == ["warn1"]

    def test_failed_result(self):
        r = CheckResult(passed=False, failures=["broken link"])
        assert not r.passed
        assert r.to_dict()["pass"] is False


# ══════════════════════════════════════════════════════════════════════
# 7. Code Scanner
# ══════════════════════════════════════════════════════════════════════

class TestCodeScanner:
    def test_finds_know_comments(self, tmp_path):
        py_file = tmp_path / "example.py"
        py_file.write_text(
            "# normal comment\n"
            "def foo():\n"
            "    # @know: [[orchestrator/runner#Key Functions]]\n"
            "    pass\n"
        )
        refs = _scan_with_pathlib(str(tmp_path), [])
        assert len(refs) == 1
        assert refs[0].target == "orchestrator/runner#Key Functions"
        assert refs[0].source_line == 3

    def test_ignores_non_python_files(self, tmp_path):
        js_file = tmp_path / "example.js"
        js_file.write_text("// @know: [[orchestrator/runner]]\n")
        refs = _scan_with_pathlib(str(tmp_path), [])
        assert len(refs) == 0

    def test_excludes_directories(self, tmp_path):
        excluded = tmp_path / "__pycache__"
        excluded.mkdir()
        py_file = excluded / "cached.py"
        py_file.write_text("# @know: [[orchestrator/runner]]\n")
        refs = _scan_with_pathlib(str(tmp_path), ["__pycache__"])
        assert len(refs) == 0

    def test_multiple_refs_in_file(self, tmp_path):
        py_file = tmp_path / "multi.py"
        py_file.write_text(
            "# @know: [[orchestrator/runner]]\n"
            "# @know: [[memory/vault]]\n"
        )
        refs = _scan_with_pathlib(str(tmp_path), [])
        assert len(refs) == 2
        targets = {r.target for r in refs}
        assert targets == {"orchestrator/runner", "memory/vault"}


# ══════════════════════════════════════════════════════════════════════
# 8. Frontmatter Helpers
# ══════════════════════════════════════════════════════════════════════

class TestFrontmatter:
    def test_has_require_code_mention(self):
        text = "---\nrequire-code-mention: true\ntitle: Test\n---\n## Section\n"
        assert has_require_code_mention(text) is True

    def test_no_frontmatter(self):
        text = "## Section\n\nContent.\n"
        assert has_require_code_mention(text) is False

    def test_frontmatter_without_flag(self):
        text = "---\ntitle: Test\n---\n## Section\n"
        assert has_require_code_mention(text) is False

    def test_strip_wiki_links(self):
        text = "Uses [[orchestrator/runner]] and [[memory/vault]]"
        stripped = strip_wiki_links_for_length(text)
        assert "[[" not in stripped
        assert "]]" not in stripped


# ══════════════════════════════════════════════════════════════════════
# 9. Flatten Sections
# ══════════════════════════════════════════════════════════════════════

class TestFlattenSections:
    def test_flatten(self):
        text = "## A\n\nContent.\n\n### B\n\nNested.\n\n## C\n\nMore.\n"
        sections = parse_sections(text, "test/file")
        flat = flatten_sections(sections)
        ids = [s.id for s in flat]
        assert "test/file#A" in ids
        assert "test/file#A#B" in ids
        assert "test/file#C" in ids
        assert len(flat) == 3
