"""Writer -> critic -> revise harness (orchestrator/site_critic.py)."""

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.site_content_engine import build_graph_pack, load_fixture_cases
from orchestrator.site_critic import (
    build_critic_prompt,
    parse_critic_output,
    write_story_with_review,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "site_content" / "graph_pack_cases.json"


@dataclass
class FakeProcess:
    stdout: str
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False


def _graph_pack():
    payload = load_fixture_cases(FIXTURE_PATH)
    candidate = next(
        case for case in payload["cases"] if case["id"] == "openai-agent-runtime-reliability"
    )
    return build_graph_pack(candidate, date="2026-07-01", user="ramsay")


def _copy(take="Runtime reliability is the new buying criteria, and OpenAI knows it."):
    return {
        "title": "OpenAI puts agent runtime reliability on the buyer's scorecard",
        "dek": "Reliability is becoming the procurement metric for agent platforms.",
        "take": take,
        "why_now": "OpenAI made reliability a buyer-visible benchmark this week.",
        "body_markdown": "OpenAI made agent runtime reliability a buyer-visible benchmark.\n\nThat changes procurement.",
    }


def test_parse_critic_output_validates_shape():
    assert parse_critic_output("junk") is None
    assert parse_critic_output('{"score": 22, "verdict": "pass"}') is None
    good = parse_critic_output('{"score": 9, "verdict": "pass", "issues": []}')
    assert good == {"score": 9.0, "verdict": "pass", "issues": []}
    low = parse_critic_output('{"score": 5, "verdict": "pass", "issues": ["weak lede"]}')
    assert low["verdict"] == "revise"


def test_critic_prompt_contains_rules_and_draft():
    prompt = build_critic_prompt(_copy(), _graph_pack(), rules_text="RULE: front-load the point.")
    assert "RULE: front-load the point." in prompt
    assert "buyer's scorecard" in prompt
    assert "automatic 0" in prompt


def test_review_passes_clean_draft_through():
    calls = []

    def runner(cmd, **kwargs):
        prompt = cmd[2]
        calls.append(prompt[:40])
        if "Judge this Rabbit Hole story draft" in prompt:
            return FakeProcess(stdout='{"score": 9, "verdict": "pass", "issues": []}')
        return FakeProcess(stdout=json.dumps(_copy()))

    result = write_story_with_review(
        _graph_pack(), [], voice_text="v", rules_text="rules", runner=runner
    )
    assert result == _copy()
    assert len(calls) == 2


def test_review_revises_once_on_critic_notes():
    revised = _copy(take="The runtime is the control plane now, and everyone is bidding for it.")
    state = {"writer_calls": 0, "critic_calls": 0}

    def runner(cmd, **kwargs):
        prompt = cmd[2]
        if "Judge this Rabbit Hole story draft" in prompt:
            state["critic_calls"] += 1
            if state["critic_calls"] == 1:
                return FakeProcess(stdout='{"score": 6, "verdict": "revise", "issues": ["take is soft"]}')
            return FakeProcess(stdout='{"score": 9, "verdict": "pass", "issues": []}')
        state["writer_calls"] += 1
        if state["writer_calls"] == 1:
            return FakeProcess(stdout=json.dumps(_copy()))
        assert "Editor's notes" in prompt
        assert "take is soft" in prompt
        return FakeProcess(stdout=json.dumps(revised))

    result = write_story_with_review(
        _graph_pack(), [], voice_text="v", rules_text="rules", runner=runner
    )
    assert result == revised
    assert state["writer_calls"] == 2
    assert state["critic_calls"] == 2


def test_review_fails_closed_on_fabrication_score_zero():
    def runner(cmd, **kwargs):
        prompt = cmd[2]
        if "Judge this Rabbit Hole story draft" in prompt:
            return FakeProcess(stdout='{"score": 0, "verdict": "revise", "issues": ["fabricated number"]}')
        return FakeProcess(stdout=json.dumps(_copy()))

    assert (
        write_story_with_review(_graph_pack(), [], voice_text="v", rules_text="r", runner=runner)
        is None
    )


def test_review_publishes_draft_when_critic_unavailable():
    def runner(cmd, **kwargs):
        prompt = cmd[2]
        if "Judge this Rabbit Hole story draft" in prompt:
            return FakeProcess(stdout="", returncode=1)
        return FakeProcess(stdout=json.dumps(_copy()))

    result = write_story_with_review(
        _graph_pack(), [], voice_text="v", rules_text="r", runner=runner
    )
    assert result == _copy()


def test_rules_spec_exists_and_reaches_the_writer_prompt():
    from orchestrator.site_writer import build_site_writer_prompt, load_writer_rules

    rules = load_writer_rules()
    assert "falsifiable" in rules
    assert "160 characters" in rules
    prompt = build_site_writer_prompt(_graph_pack(), [], voice_text="v")
    assert "Writer's Rules" in prompt
    assert "falsifiable" in prompt


def test_critic_system_prompt_exists():
    from orchestrator.site_critic import CRITIC_SYSTEM_PROMPT

    text = CRITIC_SYSTEM_PROMPT.read_text()
    assert "score of 0" in text
    assert "NOT fabrication" in text
    assert '"verdict": "pass" | "revise"' in text
