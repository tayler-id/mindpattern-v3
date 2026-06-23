"""Tests for orchestrator/agents.py.

Covers:
- _parse_findings() (ticket 2026-04-01-007)
- run_single_agent() dispatch and error handling
- run_claude_prompt() dispatch and stdin mode
- dispatch_research_agents() parallel execution
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from core.claude_cli import ClaudeProcessResult
from orchestrator.agents import (
    _build_claude_command,
    _parse_findings,
    AGENT_ALLOWED_TOOLS,
    build_agent_prompt,
    run_single_agent,
    run_agent_with_files,
    run_claude_prompt,
    dispatch_research_agents,
    AgentResult,
    RESEARCH_DISALLOWED_TOOLS,
)


class TestParseFindingsWithTextBeforeJson:
    """Agent output has prose before and after the JSON block."""

    def test_extracts_findings_despite_surrounding_text(self):
        output = (
            'Here are my findings:\n'
            '{"findings": [{"title": "Test Finding", "summary": "A summary", '
            '"importance": "high", "category": "AI", "source_url": "https://example.com", '
            '"source_name": "Example", "date_found": "2026-03-31"}]}\n'
            'Done. Timing: {"elapsed_ms": 320}\n'
            'Agent complete.'
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 1
        assert result[0]["title"] == "Test Finding"


class TestParseFindingsWithMultipleJsonBlocks:
    """Agent output contains a metadata JSON block followed by the findings block."""

    def test_selects_findings_block_not_metadata(self):
        # Metadata block includes "sources" array — so the greedy array
        # fallback r'\[[\s\S]*\]' would also match the wrong span.
        metadata_block = json.dumps({
            "agent": "test-agent",
            "model": "opus",
            "sources": ["rss", "twitter", "reddit"],
            "timestamp": "2026-03-31T12:00:00Z",
        })
        findings_block = json.dumps({
            "findings": [
                {
                    "title": "Real Finding",
                    "summary": "The actual result",
                    "importance": "high",
                    "category": "AI",
                    "source_url": "https://example.com/real",
                    "source_name": "Example",
                    "date_found": "2026-03-31",
                },
                {
                    "title": "Second Finding",
                    "summary": "Another result",
                    "importance": "medium",
                    "category": "ML",
                    "source_url": "https://example.com/second",
                    "source_name": "Other",
                    "date_found": "2026-03-31",
                },
            ]
        })
        # Trailing JSON block (status) ensures greedy regex overshoots
        status_block = json.dumps({"status": "complete", "elapsed_ms": 4200})
        output = (
            f"Metadata: {metadata_block}\n"
            f"Results:\n{findings_block}\n"
            f"Status: {status_block}\n"
            f"End of output."
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 2
        assert result[0]["title"] == "Real Finding"
        assert result[1]["title"] == "Second Finding"


class TestParseFindingsWithNestedBracesInValues:
    """Finding values contain literal { } characters (e.g. code snippets)."""

    def test_handles_braces_inside_string_values(self):
        findings_obj = {
            "findings": [
                {
                    "title": "Code Pattern {x: 1}",
                    "summary": "The function uses {key: value} syntax for config objects.",
                    "importance": "medium",
                    "category": "Dev Tools",
                    "source_url": "https://example.com/code",
                    "source_name": "GitHub",
                    "date_found": "2026-03-31",
                },
            ]
        }
        output = (
            "Thinking about this...\n"
            + json.dumps(findings_obj)
            + "\nAll done."
        )
        result = _parse_findings(output, "test-agent")
        assert len(result) == 1
        assert "{x: 1}" in result[0]["title"]
        assert "{key: value}" in result[0]["summary"]


class TestParseFindingsLargeOutputPerformance:
    """_parse_findings must handle 100K+ char outputs in under 1 second."""

    def test_parses_large_output_within_time_limit(self):
        # Build a realistic large output: lots of prose, then JSON
        filler = "This is a long line of agent reasoning output. " * 220  # ~10.3K per block
        blocks = [filler] * 10  # ~103K of filler text
        findings_obj = {
            "findings": [
                {
                    "title": f"Finding {i}",
                    "summary": f"Summary for finding {i} with details.",
                    "importance": "medium",
                    "category": "AI",
                    "source_url": f"https://example.com/{i}",
                    "source_name": "Source",
                    "date_found": "2026-03-31",
                }
                for i in range(20)
            ]
        }
        output = "\n".join(blocks) + "\n" + json.dumps(findings_obj) + "\nEnd."

        assert len(output) > 100_000, f"Output only {len(output)} chars, need >100K"

        start = time.monotonic()
        result = _parse_findings(output, "test-agent")
        elapsed = time.monotonic() - start

        assert len(result) == 20
        assert elapsed < 1.0, f"Parsing took {elapsed:.2f}s, must be < 1s"


# --- Cross-agent dedup tests (ticket 2026-04-01-R015) ---

from unittest.mock import patch
import numpy as np
from orchestrator.agents import AgentResult, dedup_cross_agent_findings


def _make_finding(title, summary, importance="medium", source_url=None, agent=None):
    """Helper to build a finding dict."""
    f = {
        "title": title,
        "summary": summary,
        "importance": importance,
        "category": "AI",
        "source_name": "Test",
        "date_found": "2026-04-01",
    }
    if source_url:
        f["source_url"] = source_url
    return f


def _mock_embed_texts(texts):
    """Return deterministic embeddings where similar titles produce similar vectors.

    Findings with the same first word get nearly identical vectors (sim > 0.95).
    Different first words get orthogonal vectors (sim ~ 0).
    """
    dim = 384
    vectors = []
    seed_map = {}
    for text in texts:
        key = text.split()[0].lower() if text else "empty"
        if key not in seed_map:
            rng = np.random.RandomState(hash(key) % 2**31)
            vec = rng.randn(dim).astype(np.float32)
            vec /= np.linalg.norm(vec)
            seed_map[key] = vec
        base = seed_map[key]
        # Add tiny noise so pairs aren't exactly 1.0
        rng = np.random.RandomState(hash(text) % 2**31)
        noise = rng.randn(dim).astype(np.float32) * 0.01
        vec = base + noise
        vec /= np.linalg.norm(vec)
        vectors.append(vec.tolist())
    return vectors


class TestCrossAgentDedupRemovesDuplicates:
    """Near-duplicate findings across agents should be consolidated."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_removes_duplicates(self, mock_embed):
        results = [
            AgentResult(
                agent_name="agent-a",
                findings=[
                    _make_finding("DuplicateStory breaks new ground", "Short summary."),
                    _make_finding("UniqueA is interesting", "Only agent A found this."),
                ],
            ),
            AgentResult(
                agent_name="agent-b",
                findings=[
                    _make_finding(
                        "DuplicateStory covered from different angle",
                        "A much longer and more detailed summary with specifics.",
                        importance="high",
                        source_url="https://example.com/dup",
                    ),
                    _make_finding("UniqueB is noteworthy", "Only agent B found this."),
                ],
            ),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]
        titles = [f["title"] for f in all_findings]

        # One of the DuplicateStory findings should be removed
        dup_count = sum(1 for t in titles if t.startswith("DuplicateStory"))
        assert dup_count == 1, f"Expected 1 DuplicateStory finding, got {dup_count}: {titles}"
        assert summary["removed"] >= 1


class TestCrossAgentDedupKeepsHigherQuality:
    """When deduplicating, the higher-quality finding is kept."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_keeps_higher_quality(self, mock_embed):
        low_quality = _make_finding("SameStory from agent A", "Short.")
        high_quality = _make_finding(
            "SameStory from agent B with more detail",
            "This is a much longer and more detailed summary that provides real value.",
            importance="high",
            source_url="https://example.com/story",
        )

        results = [
            AgentResult(agent_name="agent-a", findings=[low_quality]),
            AgentResult(agent_name="agent-b", findings=[high_quality]),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]

        assert len(all_findings) == 1
        # The kept finding should be the high-quality one (longer summary, has URL)
        kept = all_findings[0]
        assert kept["importance"] == "high"
        assert "source_url" in kept
        assert "much longer" in kept["summary"]


class TestCrossAgentDedupPreservesUniqueFindings:
    """Findings below the similarity threshold should not be removed."""

    @patch("orchestrator.agents.embed_texts", side_effect=_mock_embed_texts)
    def test_cross_agent_dedup_preserves_unique_findings(self, mock_embed):
        results = [
            AgentResult(
                agent_name="agent-a",
                findings=[
                    _make_finding("AlphaProject launches v2", "Alpha released version 2."),
                    _make_finding("BetaCompany raises funding", "Beta got series B."),
                ],
            ),
            AgentResult(
                agent_name="agent-b",
                findings=[
                    _make_finding("GammaFramework hits 1.0", "Gamma reached stable."),
                    _make_finding("DeltaResearch publishes paper", "Delta published on arXiv."),
                ],
            ),
        ]

        deduped, summary = dedup_cross_agent_findings(results)
        all_findings = [f for r in deduped for f in r.findings]

        assert len(all_findings) == 4
        assert summary["removed"] == 0


class TestCrossAgentDedupEmptyInput:
    """Empty input returns empty output with zero-count summary."""

    def test_cross_agent_dedup_empty_input(self):
        deduped, summary = dedup_cross_agent_findings([])
        assert deduped == []
        assert summary["removed"] == 0
        assert summary["total"] == 0


# ═══════════════════════════════════════════════════════════════════════
# run_single_agent tests
# ═══════════════════════════════════════════════════════════════════════

VALID_FINDINGS_JSON = json.dumps({
    "findings": [
        {
            "title": "Test Finding",
            "summary": "A summary",
            "importance": "high",
            "category": "AI",
            "source_url": "https://example.com",
            "source_name": "Example",
            "date_found": "2026-03-31",
        }
    ]
})


class TestBuildClaudeCommand:
    """Shared Claude command builder preserves each caller's CLI contract."""

    def test_builds_base_command_with_system_prompt_and_tools(self):
        cmd = _build_claude_command(
            "test prompt",
            model="sonnet",
            max_turns=10,
            system_prompt_file="agents/eic.md",
            allowed_tools=["Read", "Write"],
            disallowed_tools="Agent",
        )

        assert cmd == [
            "claude", "-p", "test prompt",
            "--model", "sonnet",
            "--max-turns", "10",
            "--output-format", "text",
            "--append-system-prompt-file", "agents/eic.md",
            "--allowedTools", "Read",
            "--allowedTools", "Write",
            "--disallowedTools", "Agent",
        ]

    def test_research_policy_flags_are_explicit(self):
        cmd = _build_claude_command(
            "research prompt",
            model="opus",
            max_turns=35,
            allowed_tools=AGENT_ALLOWED_TOOLS,
            disallowed_tools=RESEARCH_DISALLOWED_TOOLS,
        )

        assert cmd[0:2] == ["claude", "-p"]
        assert "WebSearch" in cmd
        denied = cmd[cmd.index("--disallowedTools") + 1].split()
        for tool in ("Bash", "Agent", "Write", "Edit", "Skill"):
            assert tool in denied


def _process_result(
    stdout="",
    stderr="",
    returncode=0,
    timed_out=False,
    error=None,
):
    """Create a shared Claude process result for agent tests."""
    return ClaudeProcessResult(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        timed_out=timed_out,
        error=error,
    )


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunSingleAgentSuccess:
    """run_single_agent returns parsed findings on a successful Claude call."""

    def test_run_single_agent_success(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300

        mock_run_process.return_value = _process_result(
            stdout=VALID_FINDINGS_JSON, returncode=0
        )

        result = run_single_agent("test-agent", "test prompt")

        assert isinstance(result, AgentResult)
        assert result.agent_name == "test-agent"
        assert result.exit_code == 0
        assert result.error is None
        assert result.killed_by_timeout is False
        assert len(result.findings) == 1
        assert result.findings[0]["title"] == "Test Finding"
        assert result.duration_ms >= 0

        # Verify the shared process runner was called with the claude CLI.
        mock_run_process.assert_called_once()
        cmd = mock_run_process.call_args.args[0]
        assert cmd[0] == "claude"
        assert "-p" in cmd


class TestRunSingleAgentSharedProcessRunner:
    """run_single_agent delegates Claude process execution to core.claude_cli."""

    @patch("orchestrator.agents.router")
    @patch("orchestrator.agents.run_claude_process")
    def test_run_single_agent_uses_shared_process_runner(
        self, mock_run_process, mock_router, monkeypatch
    ):
        monkeypatch.setenv("PATH", "")
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300
        mock_run_process.return_value = ClaudeProcessResult(
            stdout=VALID_FINDINGS_JSON,
            stderr="",
            returncode=0,
        )

        result = run_single_agent("test-agent", "test prompt")

        assert result.classification == "success"
        assert len(result.findings) == 1
        mock_run_process.assert_called_once()


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunSingleAgentTimeout:
    """run_single_agent handles shared-runner timeouts."""

    def test_run_single_agent_timeout(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 60

        mock_run_process.return_value = _process_result(
            returncode=1,
            timed_out=True,
            error="Timed out after 60s",
        )

        result = run_single_agent("slow-agent", "long prompt")

        assert result.agent_name == "slow-agent"
        assert result.killed_by_timeout is True
        assert result.error is not None
        assert "Timed out" in result.error
        assert result.findings == []


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunSingleAgentInvalidJson:
    """run_single_agent handles unparseable output gracefully."""

    def test_run_single_agent_invalid_json(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300

        mock_run_process.return_value = _process_result(
            stdout="This is not JSON at all, just rambling text.", returncode=0
        )

        result = run_single_agent("confused-agent", "test prompt")

        assert result.agent_name == "confused-agent"
        assert result.exit_code == 0
        assert result.findings == []
        assert result.error is None  # No error — just no findings parsed


# ═══════════════════════════════════════════════════════════════════════
# run_claude_prompt tests
# ═══════════════════════════════════════════════════════════════════════

@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunClaudePromptSuccess:
    """run_claude_prompt returns stdout and exit code on success."""

    def test_run_claude_prompt_success(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300

        mock_run_process.return_value = ClaudeProcessResult(
            stdout="Newsletter content here",
            stderr="",
            returncode=0,
        )

        output, exit_code = run_claude_prompt("Write a newsletter", "synthesis_pass1")

        assert output == "Newsletter content here"
        assert exit_code == 0

        mock_run_process.assert_called_once()
        cmd = mock_run_process.call_args.args[0]
        assert "claude" in cmd
        # Prompt passed as -p argument for small prompts
        assert "Write a newsletter" in cmd
        # input should be None for small prompts
        assert mock_run_process.call_args.kwargs["input_text"] is None


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunClaudePromptLargePromptUsesStdin:
    """run_claude_prompt pipes large prompts via stdin."""

    def test_run_claude_prompt_large_prompt_uses_stdin(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "opus"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 600

        mock_run_process.return_value = ClaudeProcessResult(
            stdout="Output from large prompt",
            stderr="",
            returncode=0,
        )

        large_prompt = "x" * 150_000  # >100K chars
        output, exit_code = run_claude_prompt(large_prompt, "synthesis_pass2")

        assert output == "Output from large prompt"
        assert exit_code == 0

        # Verify stdin was used
        call_kwargs = mock_run_process.call_args.kwargs
        assert call_kwargs["input_text"] == large_prompt

        # Verify -p argument is "-" (stdin marker)
        cmd = mock_run_process.call_args.args[0]
        p_idx = cmd.index("-p")
        assert cmd[p_idx + 1] == "-"


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunClaudePromptFailure:
    """run_claude_prompt returns empty string and exit code 1 on failure."""

    def test_run_claude_prompt_failure(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300

        mock_run_process.return_value = ClaudeProcessResult(
            stdout="",
            stderr="",
            returncode=1,
            timed_out=True,
            error="Timed out after 300s",
        )

        output, exit_code = run_claude_prompt("test prompt", "synthesis_pass1")

        assert output == ""
        assert exit_code == 1

    def test_run_claude_prompt_startup_error_returns_failure(self, mock_run_process, mock_router):
        mock_router.get_model.return_value = "sonnet"
        mock_router.get_max_turns.return_value = 10
        mock_router.get_timeout.return_value = 300

        mock_run_process.return_value = ClaudeProcessResult(
            stdout="",
            stderr="",
            returncode=1,
            error="missing claude",
        )
        output, exit_code = run_claude_prompt("test prompt", "synthesis_pass1")

        assert output == ""
        assert exit_code == 1


class TestDryRunClaudeDispatch:
    """MP_DRY_RUN skips real Claude process execution at dispatch boundaries."""

    def test_run_claude_prompt_dry_run_skips_process_runner(self, monkeypatch):
        monkeypatch.setenv("MP_DRY_RUN", "1")

        with patch("orchestrator.agents.run_claude_process") as mock_run_process:
            output, exit_code = run_claude_prompt("Write a newsletter", "synthesis_pass2")

        assert exit_code == 0
        assert "Dry-Run Report" in output
        mock_run_process.assert_not_called()

    def test_run_single_agent_dry_run_skips_process_runner(self, monkeypatch):
        monkeypatch.setenv("MP_DRY_RUN", "1")

        with patch("orchestrator.agents.run_claude_process") as mock_run_process:
            result = run_single_agent("news-researcher", "find news")

        assert result.classification == "success"
        assert result.findings
        assert result.findings[0]["source_name"] == "Dry Run"
        mock_run_process.assert_not_called()

    def test_run_agent_with_files_dry_run_skips_process_runner(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MP_DRY_RUN", "1")
        output_file = tmp_path / "eic-topic.json"

        with patch("orchestrator.agents.run_claude_process") as mock_run_process:
            result = run_agent_with_files(
                system_prompt_file="agents/eic.md",
                prompt="select a topic",
                output_file=str(output_file),
                task_type="eic",
            )

        assert result == {"dry_run": True, "task_type": "eic"}
        assert json.loads(output_file.read_text()) == result
        mock_run_process.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# dispatch_research_agents tests
# ═══════════════════════════════════════════════════════════════════════

@patch("orchestrator.agents.run_single_agent")
@patch("orchestrator.agents.get_agent_skill_path")
@patch("orchestrator.agents.get_agent_list")
class TestDispatchResearchAgentsParallel:
    """dispatch_research_agents runs agents concurrently and collects results."""

    def test_dispatch_research_agents_parallel(
        self, mock_get_agent_list, mock_get_skill_path, mock_run_single_agent,
        tmp_path,
    ):
        # Setup: 3 agents with skill files that exist
        agent_names = ["agent-a", "agent-b", "agent-c"]
        mock_get_agent_list.return_value = (agent_names, tmp_path)

        # Create fake skill files so exists() passes
        for name in agent_names:
            (tmp_path / f"{name}.md").write_text(f"Skill for {name}")

        mock_get_skill_path.side_effect = lambda name, uid, vertical="ai-tech": tmp_path / f"{name}.md"

        # Each agent returns a valid result
        def fake_run(agent_name, prompt, **kwargs):
            return AgentResult(
                agent_name=agent_name,
                findings=[{"title": f"Finding from {agent_name}"}],
                duration_ms=100,
            )

        mock_run_single_agent.side_effect = fake_run

        with patch("orchestrator.agents.PROJECT_ROOT", tmp_path):
            # Create required paths
            (tmp_path / "verticals" / "ai-tech").mkdir(parents=True)
            (tmp_path / "verticals" / "ai-tech" / "SOUL.md").write_text("soul")
            (tmp_path / "data" / "ramsay" / "mindpattern").mkdir(parents=True)

            context_fn = lambda agent_name, date_str: f"Context for {agent_name}"

            results = dispatch_research_agents(
                user_id="ramsay",
                date_str="2026-03-31",
                context_fn=context_fn,
                max_workers=3,
            )

        assert len(results) == 3
        agent_result_names = {r.agent_name for r in results}
        assert agent_result_names == {"agent-a", "agent-b", "agent-c"}
        total_findings = sum(len(r.findings) for r in results)
        assert total_findings == 3
        assert mock_run_single_agent.call_count == 3


@patch("orchestrator.agents.run_single_agent")
@patch("orchestrator.agents.get_agent_skill_path")
@patch("orchestrator.agents.get_agent_list")
class TestDispatchResearchAgentsPartialFailure:
    """dispatch_research_agents handles some agents failing while others succeed."""

    def test_dispatch_research_agents_partial_failure(
        self, mock_get_agent_list, mock_get_skill_path, mock_run_single_agent,
        tmp_path,
    ):
        agent_names = ["good-agent", "bad-agent"]
        mock_get_agent_list.return_value = (agent_names, tmp_path)

        for name in agent_names:
            (tmp_path / f"{name}.md").write_text(f"Skill for {name}")

        mock_get_skill_path.side_effect = lambda name, uid, vertical="ai-tech": tmp_path / f"{name}.md"

        def fake_run(agent_name, prompt, **kwargs):
            if agent_name == "bad-agent":
                raise RuntimeError("Agent crashed")
            return AgentResult(
                agent_name=agent_name,
                findings=[{"title": "Good finding"}],
                duration_ms=50,
            )

        mock_run_single_agent.side_effect = fake_run

        with patch("orchestrator.agents.PROJECT_ROOT", tmp_path):
            (tmp_path / "verticals" / "ai-tech").mkdir(parents=True)
            (tmp_path / "verticals" / "ai-tech" / "SOUL.md").write_text("soul")
            (tmp_path / "data" / "ramsay" / "mindpattern").mkdir(parents=True)

            context_fn = lambda agent_name, date_str: f"Context for {agent_name}"

            results = dispatch_research_agents(
                user_id="ramsay",
                date_str="2026-03-31",
                context_fn=context_fn,
                max_workers=2,
            )

        assert len(results) == 2

        good = [r for r in results if r.agent_name == "good-agent"]
        bad = [r for r in results if r.agent_name == "bad-agent"]

        assert len(good) == 1
        assert len(good[0].findings) == 1
        assert good[0].error is None

        assert len(bad) == 1
        assert bad[0].error is not None
        assert "crashed" in bad[0].error.lower()


class TestBuildAgentPromptToolBoundary:
    """Research prompts must match the tool boundary enforced by run_single_agent."""

    def test_preflight_exploration_uses_only_allowed_direct_tools(self, tmp_path):
        soul_path = tmp_path / "SOUL.md"
        soul_path.write_text("Soul")
        skill_path = tmp_path / "agent.md"
        skill_path.write_text("Skill")

        prompt = build_agent_prompt(
            agent_name="test-agent",
            user_id="ramsay",
            date_str="2026-06-23",
            soul_path=soul_path,
            agent_skill_path=skill_path,
            context="Recent Findings: none",
            preflight_items=[
                {
                    "source": "rss",
                    "source_name": "Example",
                    "title": "Example release",
                    "url": "https://example.com/release",
                    "content_preview": "A recent item.",
                }
            ],
        )

        assert "## Phase 2: Explore Beyond Preflight" in prompt
        for tool in ("WebSearch", "WebFetch", "Read", "Glob", "Grep"):
            assert tool in prompt

        banned_prompt_fragments = (
            "mcporter call",
            "curl -s",
            "xreach search",
            "yt-dlp",
            "Subagent Delegation",
            "Agent tool",
            "Spawn subagents",
        )
        for fragment in banned_prompt_fragments:
            assert fragment not in prompt

        assert "Do not use shell commands" in prompt
        assert "Do not spawn subagents" in prompt


# ═══════════════════════════════════════════════════════════════════════
# Transient-error classification + retry (529/429/5xx) — spec-research-reliability
# ═══════════════════════════════════════════════════════════════════════

import random as _random

from orchestrator.agents import classify_agent_failure, _retry_delay

# The real claude CLI message that broke 2026-06-23 (148 chars, on stdout, exit 1).
OVERLOAD_MSG = (
    "API Error: 529 Overloaded. This is a server-side issue, usually temporary — "
    "try again in a moment. If it persists, check https://status.claude.com.\n"
)


class TestClassifyAgentFailure:
    """classify_agent_failure inspects stdout/stderr, not just the exit code."""

    def test_overloaded_529(self):
        assert classify_agent_failure(1, OVERLOAD_MSG, "") == "overloaded"

    def test_rate_limit_429(self):
        assert classify_agent_failure(1, "API Error: 429 rate limit exceeded", "") == "rate_limit"

    def test_server_error_5xx(self):
        assert classify_agent_failure(1, "API Error: 500 Internal server error", "") == "server_error"

    def test_parse_error_on_clean_exit(self):
        # Clean exit, output just didn't parse — NOT transient, must not retry.
        assert classify_agent_failure(0, "rambling non-json text", "") == "parse_error"

    def test_other_on_nonzero_with_no_signature(self):
        assert classify_agent_failure(1, "some unexpected failure", "") == "other"


class TestRetryDelayFullJitter:
    """_retry_delay returns a value in [0, min(cap, base*2**attempt)]."""

    def test_within_full_jitter_bounds(self):
        rng = _random.Random(0)
        for attempt in range(5):
            cap = min(60.0, 2.0 * (2 ** attempt))
            for _ in range(50):
                d = _retry_delay(attempt, 2.0, 60.0, rng)
                assert 0.0 <= d <= cap

    def test_cap_is_enforced(self):
        rng = _random.Random(1)
        # base*2**10 would be 2048s; cap pins it to max_delay.
        for _ in range(50):
            assert 0.0 <= _retry_delay(10, 2.0, 60.0, rng) <= 60.0


@patch("orchestrator.agents.router")
@patch("orchestrator.agents.run_claude_process")
class TestRunSingleAgentRetry:
    """run_single_agent retries transient API errors, not other failures."""

    @staticmethod
    def _router(mock_router):
        mock_router.get_model.return_value = "opus"
        mock_router.get_max_turns.return_value = 35
        mock_router.get_timeout.return_value = 1800

    def test_retries_overloaded_then_recovers(self, mock_run_process, mock_router):
        self._router(mock_router)
        # First attempt: 529. Second attempt: valid findings.
        mock_run_process.side_effect = [
            _process_result(stdout=OVERLOAD_MSG, returncode=1),
            _process_result(stdout=VALID_FINDINGS_JSON, returncode=0),
        ]
        sleeper = MagicMock()

        result = run_single_agent("a", "p", _sleep=sleeper, _rng=_random.Random(0))

        assert result.classification == "success"
        assert len(result.findings) == 1
        assert result.error is None
        assert mock_run_process.call_count == 2     # retried once
        sleeper.assert_called_once()           # backed off once between attempts

    def test_does_not_retry_parse_error(self, mock_run_process, mock_router):
        self._router(mock_router)
        mock_run_process.side_effect = [_process_result(stdout="not json", returncode=0)]
        sleeper = MagicMock()

        result = run_single_agent("a", "p", _sleep=sleeper, _rng=_random.Random(0))

        assert result.classification == "parse_error"
        assert result.findings == []
        assert mock_run_process.call_count == 1     # no retry
        sleeper.assert_not_called()

    def test_does_not_retry_timeout(self, mock_run_process, mock_router):
        self._router(mock_router)
        mock_run_process.return_value = _process_result(
            returncode=1,
            timed_out=True,
            error="Timed out after 1800s",
        )
        sleeper = MagicMock()

        result = run_single_agent("a", "p", _sleep=sleeper, _rng=_random.Random(0))

        assert result.classification == "timeout"
        assert result.killed_by_timeout is True
        assert mock_run_process.call_count == 1     # timeouts are not retried (this spec)
        sleeper.assert_not_called()

    def test_gives_up_after_max_attempts(self, mock_run_process, mock_router):
        self._router(mock_router)
        mock_run_process.side_effect = [
            _process_result(stdout=OVERLOAD_MSG, returncode=1) for _ in range(3)
        ]
        sleeper = MagicMock()

        result = run_single_agent(
            "a", "p", max_attempts=3, _sleep=sleeper, _rng=_random.Random(0)
        )

        assert result.classification == "overloaded"
        assert result.findings == []
        assert mock_run_process.call_count == 3      # all attempts used
        assert sleeper.call_count == 2         # sleep between attempts, not after the last
        # The real cause is recorded — no more useless "Non-zero exit code".
        assert "overloaded" in (result.error or "").lower()
