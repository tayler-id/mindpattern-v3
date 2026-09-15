"""Tests for the corrective re-dispatch of failed research agents.

2026-08-19 incident: the Mac slept mid-run, 12 of 13 agents died with
"computer went to sleep mid-response", nothing retried them, and the day's
newsletter was written from 12 findings.
"""

from unittest.mock import patch

from orchestrator.agents import AgentResult, dispatch_research_agents
from orchestrator.runner import (
    _failed_agent_names,
    _merge_retry_results,
    _on_battery_power,
)


def _result(name, findings=None, error=None):
    return AgentResult(
        agent_name=name,
        findings=findings or [],
        error=error,
    )


class TestFailedAgentSelection:
    def test_error_with_no_findings_is_failed(self):
        results = [
            _result("a", error="computer went to sleep"),
            _result("b", findings=[{"title": "x"}]),
            _result("c", findings=[{"title": "y"}], error="partial parse"),
        ]
        assert _failed_agent_names(results) == ["a"]

    def test_healthy_run_selects_nothing(self):
        assert _failed_agent_names([_result("a", findings=[{}])]) == []


class TestMergeRetryResults:
    def test_retry_with_findings_replaces_failure(self):
        original = [_result("a", error="died"), _result("b", findings=[{"t": 1}])]
        retried = [_result("a", findings=[{"t": 2}])]
        merged = _merge_retry_results(original, retried)
        assert merged[0].findings == [{"t": 2}]
        assert merged[0].error is None
        assert merged[1].findings == [{"t": 1}]

    def test_retry_that_also_failed_keeps_original(self):
        original = [_result("a", error="died first")]
        retried = [_result("a", error="died again")]
        merged = _merge_retry_results(original, retried)
        assert merged[0].error == "died first"

    def test_agent_without_retry_is_untouched(self):
        original = [_result("a", error="died"), _result("b", findings=[{}])]
        assert _merge_retry_results(original, []) == original


class TestDispatchOnlyFilter:
    def test_only_restricts_dispatched_agents(self, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill")
        ran = []

        def fake_run(agent_name, prompt):
            ran.append(agent_name)
            return _result(agent_name, findings=[{"title": agent_name}])

        with patch("orchestrator.agents.get_agent_list",
                   return_value=(["a", "b", "c"], tmp_path)), \
             patch("orchestrator.agents.get_agent_skill_path",
                   return_value=skill), \
             patch("orchestrator.agents.build_agent_prompt",
                   return_value="prompt"), \
             patch("orchestrator.agents.missing_granted_binaries",
                   return_value=[]), \
             patch("orchestrator.agents.run_single_agent", fake_run):
            results = dispatch_research_agents(
                "ramsay", "2026-08-19", lambda a, d: "", only={"b"},
            )
        assert ran == ["b"]
        assert [r.agent_name for r in results] == ["b"]

    def test_only_none_dispatches_all(self, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill")
        ran = []

        def fake_run(agent_name, prompt):
            ran.append(agent_name)
            return _result(agent_name)

        with patch("orchestrator.agents.get_agent_list",
                   return_value=(["a", "b"], tmp_path)), \
             patch("orchestrator.agents.get_agent_skill_path",
                   return_value=skill), \
             patch("orchestrator.agents.build_agent_prompt",
                   return_value="prompt"), \
             patch("orchestrator.agents.missing_granted_binaries",
                   return_value=[]), \
             patch("orchestrator.agents.run_single_agent", fake_run):
            dispatch_research_agents("ramsay", "2026-08-19", lambda a, d: "")
        assert sorted(ran) == ["a", "b"]


class TestOnBatteryPower:
    def test_battery_and_ac_outputs(self):
        assert _on_battery_power("Now drawing from 'Battery Power'\n -Internal") is True
        assert _on_battery_power("Now drawing from 'AC Power'\n -Internal") is False
        assert _on_battery_power("") is False
