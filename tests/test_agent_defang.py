"""Research-agent tool policy and dry-run kill-switch tests.

Daily newsletter research agents intentionally run without default Claude tool
allow/deny fences. Source breadth depends on shell-backed tools, Agent Reach,
and subagents. Harness research keeps its own narrower guard because harness
agents run with repo-write access.
"""

import re
from pathlib import Path

from orchestrator.agents import (
    _build_claude_command,
    AGENT_ALLOWED_TOOLS,
    RESEARCH_DISALLOWED_TOOLS,
)

PROJECT_ROOT = Path(__file__).parent.parent


class TestResearchAgentTools:
    def test_research_agents_have_unfenced_tool_policy(self):
        assert AGENT_ALLOWED_TOOLS is None
        assert RESEARCH_DISALLOWED_TOOLS is None

    def test_research_cmd_omits_tool_fences_by_default(self):
        cmd = _build_claude_command(
            "research prompt",
            model="opus",
            max_turns=35,
            allowed_tools=AGENT_ALLOWED_TOOLS,
            disallowed_tools=RESEARCH_DISALLOWED_TOOLS,
        )
        assert "--allowedTools" not in cmd
        assert "--disallowedTools" not in cmd

    def test_dispatch_cmd_preserves_explicit_tool_fences(self):
        cmd = _build_claude_command(
            "prompt",
            model="sonnet",
            max_turns=10,
            allowed_tools=["Read", "Glob"],
            disallowed_tools="Agent,Write",
        )
        assert cmd.count("--allowedTools") == 2
        assert cmd[cmd.index("--allowedTools") + 1] == "Read"
        assert cmd[cmd.index("--allowedTools", cmd.index("--allowedTools") + 1) + 1] == "Glob"
        assert cmd[cmd.index("--disallowedTools") + 1] == "Agent,Write"


class TestHarnessResearchAgent:
    def test_webfetch_removed_from_harness_research(self):
        """The harness research agent holds repo write access — it must not
        also fetch arbitrary pages (lethal trifecta)."""
        run_sh = (PROJECT_ROOT / "harness" / "run.sh").read_text()
        # Find the research stage's tool flags
        research_block = run_sh.split("Stage 2: Research")[-1].split("Stage 3")[0]
        allowed = re.search(r'--allowedTools\s+"([^"]+)"', research_block).group(1)
        disallowed = re.search(r'--disallowedTools\s+"([^"]+)"', research_block).group(1)
        assert "WebFetch" not in allowed.split()
        assert "WebFetch" in disallowed.split()


class TestDryRunKillSwitch:
    def test_dry_run_sets_outbound_kill_switch(self):
        """run.py --dry-run must force MP_DISABLE_OUTBOUND=1."""
        source = (PROJECT_ROOT / "run.py").read_text()
        assert 'os.environ["MP_DISABLE_OUTBOUND"] = "1"' in source
        # The assignment must be gated on args.dry_run
        gate = re.search(
            r"if args\.dry_run:\s*\n\s*os\.environ\[\"MP_DISABLE_OUTBOUND\"\] = \"1\"",
            source,
        )
        assert gate, "--dry-run does not force the kill switch"

    def test_dry_run_sets_claude_skip_switch(self):
        """run.py --dry-run must force MP_DRY_RUN=1 so Claude calls are skipped."""
        source = (PROJECT_ROOT / "run.py").read_text()
        assert 'os.environ["MP_DRY_RUN"] = "1"' in source
        gate = re.search(
            r"if args\.dry_run:\s*\n"
            r"\s*os\.environ\[\"MP_DISABLE_OUTBOUND\"\] = \"1\"\s*\n"
            r"\s*os\.environ\[\"MP_DRY_RUN\"\] = \"1\"",
            source,
        )
        assert gate, "--dry-run does not force the Claude dry-run switch"

    def test_kill_switch_blocks_send(self, monkeypatch):
        """End check: with the switch set, outbound_allowed() is False."""
        from core import receipts

        monkeypatch.setenv("MP_DISABLE_OUTBOUND", "1")
        assert receipts.outbound_allowed() is False
