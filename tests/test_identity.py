"""Tests for identity file loading in agent prompts."""
from pathlib import Path

from orchestrator.agents import (
    _build_claude_command,
    AGENT_ALLOWED_TOOLS,
    build_agent_prompt,
    RESEARCH_DISALLOWED_TOOLS,
)


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


def test_research_agent_command_does_not_add_default_tool_fences():
    """Research agents need the full Claude Code research surface."""
    cmd = _build_claude_command(
        "research prompt",
        model="opus",
        max_turns=35,
        allowed_tools=AGENT_ALLOWED_TOOLS,
        disallowed_tools=RESEARCH_DISALLOWED_TOOLS,
    )
    assert "--allowedTools" not in cmd
    assert "--disallowedTools" not in cmd
