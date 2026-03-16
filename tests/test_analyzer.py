"""Tests for self-optimization analyzer."""
import json
from pathlib import Path

from orchestrator.pipeline import Phase, PHASE_ORDER, SKIPPABLE_PHASES


# ── Pipeline phase tests ──────────────────────────────────────────

def test_analyze_phase_exists():
    assert hasattr(Phase, "ANALYZE")
    assert Phase.ANALYZE.value == "analyze"


def test_analyze_in_phase_order():
    order = [p.value for p in PHASE_ORDER]
    evolve_idx = order.index("evolve")
    analyze_idx = order.index("analyze")
    mirror_idx = order.index("mirror")
    assert evolve_idx < analyze_idx < mirror_idx


def test_analyze_is_skippable():
    assert Phase.ANALYZE in SKIPPABLE_PHASES


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
