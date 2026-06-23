"""M0 Task 14 — de-fang research agents (audit C6).

Research agents ingest scraped web content; an injected instruction must
never reach a shell, spawn subagents, or write files. --dry-run must force
the outbound kill switch.
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
    def test_no_shell_or_subagents_in_allowlist(self):
        assert "Bash" not in AGENT_ALLOWED_TOOLS
        assert "Agent" not in AGENT_ALLOWED_TOOLS

    def test_no_write_tools_in_allowlist(self):
        assert "Write" not in AGENT_ALLOWED_TOOLS
        assert "Edit" not in AGENT_ALLOWED_TOOLS

    def test_research_tools_still_present(self):
        for tool in ("WebSearch", "WebFetch", "Read", "Glob", "Grep"):
            assert tool in AGENT_ALLOWED_TOOLS

    def test_dispatch_cmd_denies_dangerous_tools(self):
        """The built claude command must explicitly disallow Bash/Agent —
        allowed-tools alone is not reliably enforced."""
        cmd = _build_claude_command(
            "research prompt",
            model="opus",
            max_turns=35,
            allowed_tools=AGENT_ALLOWED_TOOLS,
            disallowed_tools=RESEARCH_DISALLOWED_TOOLS,
        )
        denied = cmd[cmd.index("--disallowedTools") + 1].split()
        for tool in ("Bash", "Agent", "Write", "Edit", "Skill"):
            assert tool in denied


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
