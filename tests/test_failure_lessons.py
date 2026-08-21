"""The quality-drop lesson must name a cause, not restate the score.

Every one of the 27 rows in failure_lessons reads like
"Overall score 0.573 vs 7-day avg 0.719". That text is injected into the
synthesis prompt under "Previous failures to avoid", where it tells the
newsletter writer nothing it can act on.
"""

import pytest

from orchestrator.runner import _build_quality_drop_lesson


BASE_QUALITY = {"overall_score": 0.573, "7day_avg": 0.719}


class TestQualityDropLesson:
    def test_names_the_agents_that_returned_nothing(self):
        lesson = _build_quality_drop_lesson(
            BASE_QUALITY,
            agent_coverage={
                "contributing_agents": 9,
                "target_agents": 13,
                "zero_finding_agents": ["reddit-researcher"],
                "failed_agents": ["hn-researcher", "arxiv-researcher"],
            },
            source_health_summary={},
        )
        assert "reddit-researcher" in lesson
        assert "hn-researcher" in lesson
        assert "9/13" in lesson

    def test_names_degraded_sources(self):
        lesson = _build_quality_drop_lesson(
            BASE_QUALITY,
            agent_coverage={},
            source_health_summary={
                "degraded_sources": ["reddit", "twitter"],
                "unavailable_sources": ["exa"],
            },
        )
        assert "reddit" in lesson
        assert "twitter" in lesson

    def test_falls_back_to_the_score_when_no_cause_is_known(self):
        lesson = _build_quality_drop_lesson(
            BASE_QUALITY, agent_coverage={}, source_health_summary={}
        )
        assert "0.573" in lesson
        assert "no degraded agents or sources" in lesson.lower()

    def test_is_a_single_line_short_enough_for_a_prompt(self):
        lesson = _build_quality_drop_lesson(
            BASE_QUALITY,
            agent_coverage={
                "contributing_agents": 4,
                "target_agents": 13,
                "zero_finding_agents": [f"agent-{i}" for i in range(9)],
                "failed_agents": [],
            },
            source_health_summary={"degraded_sources": ["a", "b", "c", "d"]},
        )
        assert "\n" not in lesson
        assert len(lesson) <= 400

    def test_missing_seven_day_average_does_not_crash(self):
        lesson = _build_quality_drop_lesson(
            {"overall_score": 0.5}, agent_coverage={}, source_health_summary={}
        )
        assert "0.5" in lesson
