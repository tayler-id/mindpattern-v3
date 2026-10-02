"""Tests for identity file loading in agent prompts."""
from pathlib import Path

from orchestrator.agents import (
    AGENT_ALLOWED_TOOLS,
    build_agent_prompt,
    RESEARCH_DISALLOWED_TOOLS,
)


def _build_claude_command(prompt, *, model, max_turns, allowed_tools=None, disallowed_tools=None,
                          system_prompt_file=None):
    """The argv core.model_cli builds for these inputs (the old builder moved there)."""
    from core.config import Route
    from core.model_cli import CallRequest, ToolPolicy, build_argv, disallowed

    route = Route("test", "claude", model, 300, max_turns=max_turns)
    request = CallRequest(task="test", prompt=prompt, system_prompt_file=system_prompt_file,
                          tools=ToolPolicy(allowed=tuple(allowed_tools or ()),
                                           disallowed=disallowed(disallowed_tools)))
    return build_argv(route, request)[0]


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


def test_research_agent_command_grants_web_tools_without_fence():
    """Research agents keep the full Claude Code research surface (no
    --disallowedTools fence) while web tools are pre-approved for headless
    runs, which cannot answer permission prompts."""
    cmd = _build_claude_command(
        "research prompt",
        model="opus",
        max_turns=35,
        allowed_tools=AGENT_ALLOWED_TOOLS,
        disallowed_tools=RESEARCH_DISALLOWED_TOOLS,
    )
    granted = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--allowedTools"]
    assert "WebSearch" in granted
    assert "WebFetch" in granted
    assert "--disallowedTools" not in cmd
