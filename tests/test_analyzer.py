"""Tests for self-optimization analyzer."""
import json
from pathlib import Path

from orchestrator.pipeline import Phase, PHASE_ORDER, SKIPPABLE_PHASES


# ── Pipeline phase tests ──────────────────────────────────────────

def test_phase_semantics():
    assert hasattr(Phase, "EVOLVE")
    assert hasattr(Phase, "IDENTITY")
    assert not hasattr(Phase, "ANALYZE")


def test_evolve_identity_in_phase_order():
    order = [p.value for p in PHASE_ORDER]
    evolve_idx = order.index("evolve")
    identity_idx = order.index("identity")
    mirror_idx = order.index("mirror")
    assert evolve_idx < identity_idx < mirror_idx


def test_evolve_and_identity_are_skippable():
    assert Phase.EVOLVE in SKIPPABLE_PHASES
    assert Phase.IDENTITY in SKIPPABLE_PHASES


# ── Analyzer function tests ─────────────────────────────────────

from orchestrator.analyzer import (
    build_analyzer_prompt,
    parse_analyzer_output,
    apply_analyzer_changes,
)


def test_build_analyzer_prompt_includes_traces(tmp_path):
    # Create mock trace dir with one agent
    trace_dir = tmp_path / "agents"
    hn = trace_dir / "hn-researcher"
    hn.mkdir(parents=True)
    (hn / "2026-03-16.md").write_text("# hn-researcher trace\n## Reasoning\nUsed WebSearch first.")

    # Create mock skill file
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    skill_file = skill_dir / "hn-researcher.md"
    skill_file.write_text("# HN Researcher\n## Phase 2 Exploration Preferences\n- Primary: Exa")

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[skill_file],
        date_str="2026-03-16",
        metrics={"findings_per_agent": {"hn-researcher": 12}},
        regression_data=[],
    )

    assert "hn-researcher trace" in prompt
    assert "Used WebSearch first" in prompt
    assert "Phase 2 Exploration Preferences" in prompt
    assert "Primary: Exa" in prompt


def test_build_analyzer_prompt_skips_agents_without_trace(tmp_path):
    trace_dir = tmp_path / "agents"
    trace_dir.mkdir(parents=True)
    # No trace files at all

    skill_file = tmp_path / "agent.md"
    skill_file.write_text("# Agent")

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[skill_file],
        date_str="2026-03-16",
        metrics={},
        regression_data=[],
    )

    assert "No trace logs found" in prompt or "TRACE LOG" not in prompt


def test_build_analyzer_prompt_includes_regression_data(tmp_path):
    trace_dir = tmp_path / "agents"
    trace_dir.mkdir(parents=True)

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[],
        date_str="2026-03-16",
        metrics={},
        regression_data=[{
            "file": "agents/hn-researcher.md",
            "quality_before": 0.85,
            "quality_after": 0.60,
            "regression_pct": 0.294,
        }],
    )

    assert "REGRESSION" in prompt
    assert "hn-researcher" in prompt
    assert "0.85" in prompt


def test_parse_analyzer_output_valid():
    raw = json.dumps({
        "changes": [{"file": "agents/x.md", "reason": "test", "diff": {"section": "S", "action": "replace", "content": "new"}}],
        "reversions": [],
        "no_changes": [],
    })
    result = parse_analyzer_output(raw)
    assert len(result["changes"]) == 1
    assert result["changes"][0]["file"] == "agents/x.md"


def test_parse_analyzer_output_with_fences():
    raw = '```json\n{"changes": [], "reversions": [], "no_changes": ["a.md"]}\n```'
    result = parse_analyzer_output(raw)
    assert result is not None
    assert result["no_changes"] == ["a.md"]


def test_parse_analyzer_output_invalid():
    result = parse_analyzer_output("not json at all")
    assert result is None


def test_apply_analyzer_changes_replace(tmp_path):
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Focus\nOld focus\n\n## Notes\nKeep this\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Focus", "action": "replace", "content": "New focus content"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    updated = skill.read_text()
    assert "New focus content" in updated
    assert "Old focus" not in updated
    assert "Keep this" in updated  # Other sections preserved
    assert result["applied"] == 1


def test_apply_analyzer_changes_append(tmp_path):
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Notes\nExisting note\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Notes", "action": "append", "content": "\nNew note from analyzer"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    updated = skill.read_text()
    assert "Existing note" in updated
    assert "New note from analyzer" in updated


def test_apply_analyzer_changes_rejects_missing_trace(tmp_path):
    """Changes for files with no trace should be rejected."""
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Focus\nOld\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Focus", "action": "replace", "content": "New"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path, traced_files=set())
    assert result["applied"] == 0
    assert result["skipped"] == 1


# ── Bug fix tests: section duplication ───────────────────────────

from orchestrator.analyzer import (
    _find_and_replace_section,
    _append_to_section,
    _dedup_sections,
    _normalize_path,
    _section_already_contains,
)


def test_find_and_replace_removes_duplicate_sections():
    """When a file has multiple sections with the same heading,
    replace should keep only the first (with new body) and drop the rest."""
    content = (
        "# Title\n\n"
        "## Focus\nOld focus 1\n\n"
        "## Notes\nSome notes\n\n"
        "## Focus\nOld focus 2\n\n"
        "## Focus\nOld focus 3\n"
    )
    result = _find_and_replace_section(content, "Focus", "New focus content")
    assert result.count("## Focus") == 1
    assert "New focus content" in result
    assert "Old focus 1" not in result
    assert "Old focus 2" not in result
    assert "Old focus 3" not in result
    assert "Some notes" in result  # Other sections preserved


def test_find_and_replace_single_section_still_works():
    """Normal case: single section gets replaced."""
    content = "# Title\n\n## Focus\nOld\n\n## Notes\nKeep\n"
    result = _find_and_replace_section(content, "Focus", "New")
    assert result.count("## Focus") == 1
    assert "New" in result
    assert "Old" not in result
    assert "Keep" in result


def test_find_and_replace_creates_section_if_missing():
    """If the section doesn't exist, it should be appended."""
    content = "# Title\n\n## Notes\nSome notes\n"
    result = _find_and_replace_section(content, "Focus", "Brand new")
    assert "## Focus" in result
    assert "Brand new" in result
    assert "Some notes" in result


def test_append_skips_duplicate_content():
    """If >80% of lines to append already exist, skip the append."""
    content = "# Title\n\n## Notes\n- Line A\n- Line B\n- Line C\n- Line D\n- Line E\n"
    # Try appending content that's 100% already there
    new_content = "- Line A\n- Line B\n- Line C\n- Line D\n- Line E"
    result = _append_to_section(content, "Notes", new_content)
    # Count occurrences of "Line A" — should still be 1, not 2
    assert result.count("- Line A") == 1


def test_append_allows_genuinely_new_content():
    """If the content is mostly new, the append should proceed."""
    content = "# Title\n\n## Notes\n- Existing line\n"
    new_content = "- Brand new line 1\n- Brand new line 2\n- Brand new line 3"
    result = _append_to_section(content, "Notes", new_content)
    assert "Brand new line 1" in result
    assert "Brand new line 2" in result
    assert "Brand new line 3" in result


def test_append_skips_when_most_lines_match():
    """80% threshold: 4 of 5 lines match -> skip."""
    content = "# Title\n\n## Notes\n- A\n- B\n- C\n- D\n"
    # 4 of 5 lines already exist = 80% -> should skip
    new_content = "- A\n- B\n- C\n- D\n- E"
    result = _append_to_section(content, "Notes", new_content)
    # "- E" should NOT appear because 80% threshold was met
    assert result.count("- E") == 0


def test_append_allows_when_below_threshold():
    """Below 80% threshold: should append."""
    content = "# Title\n\n## Notes\n- A\n- B\n"
    # 2 of 5 lines match = 40% -> should append
    new_content = "- A\n- B\n- X\n- Y\n- Z"
    result = _append_to_section(content, "Notes", new_content)
    assert "- X" in result
    assert "- Y" in result
    assert "- Z" in result


def test_section_already_contains_helper():
    """Direct test of the fuzzy match helper."""
    section = ["## Notes", "- A", "- B", "- C", "- D", ""]

    # 100% match
    assert _section_already_contains(section, "- A\n- B\n- C\n- D") is True
    # 75% match (below 80% threshold)
    assert _section_already_contains(section, "- A\n- B\n- C\n- NEW") is False
    # 0% match
    assert _section_already_contains(section, "- X\n- Y\n- Z") is False
    # Empty new content -> considered already present
    assert _section_already_contains(section, "") is True
    assert _section_already_contains(section, "   \n  \n") is True


def test_dedup_sections_removes_duplicates():
    """_dedup_sections should keep first occurrence, drop subsequent."""
    content = (
        "# Title\n\n"
        "## Focus\nFirst focus\n\n"
        "## Notes\nSome notes\n\n"
        "## Focus\nDuplicate focus\n\n"
        "## Focus\nTriple focus\n"
    )
    result = _dedup_sections(content)
    assert result.count("## Focus") == 1
    assert "First focus" in result
    assert "Duplicate focus" not in result
    assert "Triple focus" not in result
    assert "Some notes" in result


def test_dedup_sections_preserves_unique():
    """No duplicates -> no changes."""
    content = "# Title\n\n## A\nBody A\n\n## B\nBody B\n\n## C\nBody C\n"
    result = _dedup_sections(content)
    assert result == content


def test_dedup_sections_case_insensitive():
    """Headings should be matched case-insensitively."""
    content = "# Title\n\n## Focus\nFirst\n\n## focus\nDup\n\n## FOCUS\nTrip\n"
    result = _dedup_sections(content)
    assert result.count("First") == 1
    assert "Dup" not in result
    assert "Trip" not in result


# ── Bug fix tests: path resolution ───────────────────────────────

def test_normalize_path_existing_file(tmp_path):
    """If the path already exists, return it unchanged."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "eic.md").write_text("# EIC")
    result = _normalize_path("agents/eic.md", tmp_path)
    assert result == "agents/eic.md"


def test_normalize_path_prepends_verticals(tmp_path):
    """ai-tech/agents/x.md should resolve to verticals/ai-tech/agents/x.md."""
    (tmp_path / "verticals" / "ai-tech" / "agents").mkdir(parents=True)
    (tmp_path / "verticals" / "ai-tech" / "agents" / "rss-researcher.md").write_text("# RSS")

    result = _normalize_path("ai-tech/agents/rss-researcher.md", tmp_path)
    assert result == "verticals/ai-tech/agents/rss-researcher.md"


def test_normalize_path_prefix_brute_force(tmp_path):
    """If no vertical match, try other prefixes."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "eic.md").write_text("# EIC")

    # LLM might produce just "eic.md" without agents/ prefix
    result = _normalize_path("eic.md", tmp_path)
    assert result == "agents/eic.md"


def test_normalize_path_returns_original_if_not_found(tmp_path):
    """If nothing resolves, return the original path."""
    result = _normalize_path("nonexistent/file.md", tmp_path)
    assert result == "nonexistent/file.md"


def test_apply_changes_with_path_normalization(tmp_path):
    """End-to-end: apply_analyzer_changes should normalize paths."""
    (tmp_path / "verticals" / "ai-tech" / "agents").mkdir(parents=True)
    skill = tmp_path / "verticals" / "ai-tech" / "agents" / "hn-researcher.md"
    skill.write_text("# HN Researcher\n\n## Focus\nOld focus\n")

    changes = {
        "changes": [{
            "file": "ai-tech/agents/hn-researcher.md",  # Missing verticals/ prefix
            "reason": "test path normalization",
            "diff": {"section": "Focus", "action": "replace", "content": "New focus"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    assert result["applied"] == 1
    assert result["errors"] == []
    updated = skill.read_text()
    assert "New focus" in updated
    assert "Old focus" not in updated


def test_apply_changes_dedup_runs_after_modification(tmp_path):
    """After replace/append, final dedup should clean up any stray duplicates."""
    skill = tmp_path / "agent.md"
    # File already has duplicate sections from prior buggy runs
    skill.write_text(
        "# Agent\n\n"
        "## Focus\nFocus v1\n\n"
        "## Notes\nNotes\n\n"
        "## Focus\nFocus v2 (dup)\n\n"
        "## Focus\nFocus v3 (dup)\n"
    )

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test dedup",
            "diff": {"section": "Focus", "action": "replace", "content": "Clean focus"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    assert result["applied"] == 1
    updated = skill.read_text()
    # _find_and_replace_section removes dups, then _dedup_sections double-checks
    assert updated.count("## Focus") == 1
    assert "Clean focus" in updated
    assert "Focus v1" not in updated
    assert "Focus v2" not in updated
    assert "Focus v3" not in updated
