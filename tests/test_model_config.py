"""config/models.json routes every task, and a bad file fails before any model call."""
import json

import pytest

from core.config import ConfigError, Route, load_routes, main, parse_routes, route_for

# The routing Tayler chose on 2026-10-02: Opus 5.5 decides and writes the
# newsletter, Sonnet 5.5 researches and writes site stories, Haiku extracts.
# (model, max_turns, timeout_s, effort)
ROUTING_DECIDED_2026_10_02 = {
    "trend_scan": ("claude-haiku-4-5", 5, 60, None),
    "research_agent": ("claude-opus-5-5", 35, 1800, "high"),
    "synthesis_pass1": ("claude-opus-5-5", 10, 600, "high"),
    "synthesis_pass2": ("claude-opus-5-5", 30, 900, "high"),
    "learnings_update": ("claude-sonnet-5-5", 5, 120, "low"),
    "identity": ("claude-sonnet-5-5", 5, 300, "medium"),
    "evolve": ("claude-opus-5-5", 10, 600, "high"),
    "site_story_writer": ("claude-sonnet-5-5", 8, 300, "medium"),
    "kg_extract": ("claude-haiku-4-5", 1, 300, None),
    "knowledge_flush": ("claude-sonnet-5-5", 1, 120, "low"),
    "eic": ("claude-opus-5-5", 15, 600, "high"),
    "writer": ("sonnet", 15, 300, "high"),
    "some_task_nobody_listed": ("sonnet", 10, 300, "high"),
}

# MP_SITE_STORY_WRITER=codex (the backfill operator's setting) drafted with the
# Codex CLI's own default model, which was gpt-6.1-sol on 2026-10-02.
CODEX_WRITER = Route("site_story_writer_codex", "codex", "gpt-6.1-sol", 300, effort="medium")


def test_the_shipped_config_routes_each_task_as_decided():
    actual = {task: (route_for(task).model, route_for(task).max_turns, route_for(task).timeout_s,
                     route_for(task).effort) for task in ROUTING_DECIDED_2026_10_02}
    assert actual == ROUTING_DECIDED_2026_10_02


def test_every_shipped_claude_route_pins_its_effort_except_haiku():
    for task, route in load_routes().items():
        if route.provider == "claude":
            assert (route.effort is None) == ("haiku" in route.model), task


def test_the_codex_writer_route_names_its_model():
    assert route_for("site_story_writer_codex") == CODEX_WRITER


def test_an_unlisted_task_gets_the_default_route_under_its_own_name():
    assert route_for("engagement") == Route("engagement", "claude", "sonnet", 300, "high", 10, None, True)


def test_a_fallback_route_is_parsed():
    routes = parse_routes({"tasks": {
        "_default": {"provider": "claude", "model": "sonnet", "effort": "high", "timeout_s": 300},
        "site_story_critic": {"provider": "codex", "model": "gpt-6.1-sol", "effort": "low", "timeout_s": 300,
                              "fallback": {"provider": "claude", "model": "claude-sonnet-5-5", "max_turns": 5,
                                           "effort": "medium", "timeout_s": 300}},
    }})
    critic = routes["site_story_critic"]
    assert (critic.provider, critic.model, critic.effort) == ("codex", "gpt-6.1-sol", "low")
    assert critic.fallback == Route("site_story_critic", "claude", "claude-sonnet-5-5", 300, "medium", 5, None, True)


@pytest.mark.parametrize("tasks,message", [
    ({"x": {"provider": "claude", "model": "m", "effort": "low", "timeout_s": 1}}, '"_default" task'),
    ({"_default": {"provider": "gemini", "model": "m", "timeout_s": 1}}, "provider must be one of"),
    ({"_default": {"provider": "claude", "model": "", "timeout_s": 1}}, "model must be a non-empty string"),
    ({"_default": {"provider": "claude", "model": "m", "effort": "low"}}, "timeout_s is required"),
    ({"_default": {"provider": "claude", "model": "m", "effort": "low", "timeout_s": 0}}, "timeout_s must be a positive integer"),
    ({"_default": {"provider": "claude", "model": "m", "timeout_s": 5}}, "effort is required"),
    ({"_default": {"provider": "claude", "model": "claude-haiku-4-5", "effort": "low", "timeout_s": 5}}, "left out for Haiku"),
    ({"_default": {"provider": "claude", "model": "m", "timeout_s": 5, "effort": "huge"}}, "effort must be one of"),
    ({"_default": {"provider": "claude", "model": "m", "timeout_s": 5, "modle": "typo"}}, "unknown keys: modle"),
    ({"_default": {"provider": "claude", "model": "m", "effort": "low", "timeout_s": 5, "max_turns": True}},
     "max_turns must be"),
    ({"_default": {"provider": "claude", "model": "m", "effort": "low", "timeout_s": 5, "fallback": {
        "provider": "claude", "model": "n", "effort": "low", "timeout_s": 5, "fallback": {
            "provider": "claude", "model": "o", "effort": "low", "timeout_s": 5}}}}, "cannot itself have a fallback"),
])
def test_invalid_config_is_rejected_with_the_reason(tasks, message):
    with pytest.raises(ConfigError, match=message):
        parse_routes({"tasks": tasks})


def test_check_command_validates_a_file(tmp_path, capsys):
    good = tmp_path / "models.json"
    good.write_text(json.dumps({"tasks": {"_default": {"provider": "claude", "model": "sonnet", "effort": "high",
                                                       "timeout_s": 300}}}))
    assert main(["check", str(good)]) == 0
    assert "OK: 1 routes" in capsys.readouterr().out

    bad = tmp_path / "bad.json"
    bad.write_text('{"tasks": {"_default": {"provider": "claude"}}}')
    assert main(["check", str(bad)]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_load_routes_rereads_a_changed_file(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"tasks": {"_default": {"provider": "claude", "model": "a", "effort": "low",
                                                       "timeout_s": 1}}}))
    assert load_routes(path)["_default"].model == "a"
    path.write_text(json.dumps({"tasks": {"_default": {"provider": "claude", "model": "b", "effort": "low",
                                                       "timeout_s": 1}}}))
    import os
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
    assert load_routes(path)["_default"].model == "b"
