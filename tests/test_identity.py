"""Tests for identity file loading in agent prompts."""
from pathlib import Path
from orchestrator.agents import build_agent_prompt


def test_identity_dir_overrides_soul_path(tmp_path):
    """vault soul.md should override verticals SOUL.md"""
    # Static verticals version
    soul = tmp_path / "SOUL.md"
    soul.write_text("# Static Soul")

    # Vault version (should win)
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "soul.md").write_text("# Evolved Soul with learned preferences")
    (vault / "user.md").write_text("# User: Tayler Ramsay\nPrefers fintech and AI agents")

    skill = tmp_path / "agent.md"
    skill.write_text("# Agent skill")

    prompt = build_agent_prompt(
        agent_name="test",
        user_id="ramsay",
        date_str="2026-03-16",
        soul_path=soul,
        agent_skill_path=skill,
        context="",
        identity_dir=vault,
    )

    assert "Evolved Soul" in prompt
    assert "Static Soul" not in prompt
    assert "Tayler Ramsay" in prompt


def test_no_identity_dir_uses_soul_path(tmp_path):
    """Without identity_dir, falls back to soul_path"""
    soul = tmp_path / "SOUL.md"
    soul.write_text("# Fallback Soul")
    skill = tmp_path / "agent.md"
    skill.write_text("# Skill")

    prompt = build_agent_prompt(
        agent_name="test",
        user_id="ramsay",
        date_str="2026-03-16",
        soul_path=soul,
        agent_skill_path=skill,
        context="",
    )

    assert "Fallback Soul" in prompt


def test_skill_tool_blocked_in_run_single_agent():
    """Verify --disallowedTools Skill is in the command"""
    # We can't easily test the full subprocess, but we can verify
    # the function builds the right command by inspecting the code
    import orchestrator.agents as agents
    import inspect
    source = inspect.getsource(agents.run_single_agent)
    assert "disallowedTools" in source
    assert "Skill" in source
