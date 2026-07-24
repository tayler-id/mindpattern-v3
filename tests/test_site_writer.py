"""Agentic site story copywriter (orchestrator/site_writer.py)."""

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.site_content_engine import build_graph_pack, load_fixture_cases, run_site_content_for_date
from orchestrator.site_writer import (
    apply_story_copy,
    build_site_writer_prompt,
    parse_writer_output,
    site_story_copywriter_from_env,
    site_writer_enabled,
    write_story_copy_with_agent,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "site_content" / "graph_pack_cases.json"


def _graph_pack():
    payload = load_fixture_cases(FIXTURE_PATH)
    candidate = next(
        case for case in payload["cases"] if case["id"] == "openai-agent-runtime-reliability"
    )
    return build_graph_pack(candidate, date="2026-07-01", user="ramsay")


def _valid_copy() -> dict:
    return {
        "title": "OpenAI puts agent runtime reliability on the buyer's scorecard",
        "dek": "Reliability is becoming the procurement metric for agent platforms.",
        "take": "The runtime is the new control plane, and everyone is racing to own it.",
        "why_now": "The July 1 source trail made reliability a buyer-visible benchmark.",
        "body_markdown": "OpenAI made agent runtime reliability a buyer-visible benchmark.\n\nThat changes procurement.",
    }


def test_prompt_contains_evidence_and_voice_guide():
    pack = _graph_pack()
    prompt = build_site_writer_prompt(pack, [{"role": "Skeptic", "summary": "checks out"}], voice_text="Be sharp.")
    assert "openai.com" in prompt
    assert "Skeptic: checks out" in prompt
    assert "Be sharp." in prompt
    assert "JSON only" in prompt


def test_writer_system_prompt_carries_the_voice_rules():
    from orchestrator.site_writer import WRITER_SYSTEM_PROMPT

    text = WRITER_SYSTEM_PROMPT.read_text()
    assert "NEVER use em dashes" in text
    assert "delve" in text
    assert "Tayler Ramsay" in text
    assert "Self-Audit" in text


def test_parse_rejects_voice_violations():
    banned = _valid_copy()
    banned["body_markdown"] = "This is a robust improvement."
    assert parse_writer_output(json.dumps(banned), allowed_urls=set()) is None

    dashed = _valid_copy()
    dashed["take"] = "Runtime is the control plane \u2014 everyone wants it."
    assert parse_writer_output(json.dumps(dashed), allowed_urls=set()) is None


def test_parse_rejects_shared_hard_fail_lint():
    internal = _valid_copy()
    internal["why_now"] = "The evidence pack makes the timing clear."
    assert parse_writer_output(json.dumps(internal), allowed_urls=set()) is None

    relative_time = _valid_copy()
    relative_time["why_now"] = "OpenAI made reliability a buyer-visible benchmark this week."
    assert parse_writer_output(json.dumps(relative_time), allowed_urls=set()) is None


def test_parse_accepts_valid_json_and_strips_fences():
    copy = _valid_copy()
    out = parse_writer_output("noise before\n" + json.dumps(copy) + "\nnoise after", allowed_urls=set())
    assert out == {key: value.strip() for key, value in copy.items()}


def test_parse_rejects_missing_fields_bad_json_and_invented_urls():
    assert parse_writer_output("not json", allowed_urls=set()) is None
    partial = _valid_copy()
    del partial["take"]
    assert parse_writer_output(json.dumps(partial), allowed_urls=set()) is None

    invented = _valid_copy()
    invented["body_markdown"] += " See https://fabricated.example/proof for details."
    assert parse_writer_output(json.dumps(invented), allowed_urls=set()) is None
    assert (
        parse_writer_output(
            json.dumps(invented), allowed_urls={"https://fabricated.example/proof"}
        )
        is not None
    )


def test_write_story_copy_fails_closed_on_process_error():
    @dataclass
    class FailedProcess:
        stdout: str = ""
        stderr: str = "boom"
        returncode: int = 1
        timed_out: bool = False

    result = write_story_copy_with_agent(
        _graph_pack(), [], voice_text="v", runner=lambda *a, **k: FailedProcess()
    )
    assert result is None


def test_write_story_copy_returns_validated_copy():
    @dataclass
    class OkProcess:
        stdout: str
        stderr: str = ""
        returncode: int = 0
        timed_out: bool = False

    copy = _valid_copy()
    result = write_story_copy_with_agent(
        _graph_pack(), [], voice_text="v", runner=lambda *a, **k: OkProcess(stdout=json.dumps(copy))
    )
    assert result == copy


def test_apply_story_copy_marks_ai_provenance():
    story = {"title": "old", "provenance": {"ai_generated": False}}
    updated = apply_story_copy(story, _valid_copy())
    assert updated["title"] != "old"
    assert updated["provenance"]["ai_generated"] is True
    assert updated["provenance"]["writer"] == "claude-cli"


def test_env_gate_defaults_off(monkeypatch):
    monkeypatch.delenv("MP_SITE_STORY_WRITER", raising=False)
    assert not site_writer_enabled()
    assert site_story_copywriter_from_env() is None
    monkeypatch.setenv("MP_SITE_STORY_WRITER", "claude")
    assert site_writer_enabled()
    assert site_story_copywriter_from_env() is not None


def test_engine_applies_agent_copy_and_falls_back_on_bad_copy(tmp_path):
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE findings (
            id INTEGER PRIMARY KEY, run_date TEXT, agent TEXT, title TEXT,
            summary TEXT, importance TEXT, category TEXT, source_url TEXT,
            source_name TEXT, created_at TEXT)"""
    )
    conn.execute(
        """INSERT INTO findings VALUES
        (101, '2026-07-01', 'agent', 'OpenAI hardened agent runtime reliability',
         'OpenAI made agent runtime reliability a buyer-visible benchmark.',
         'high', 'ai', 'https://openai.com/news/agents', 'OpenAI', '2026-07-01')"""
    )
    conn.commit()

    calls = {"n": 0}

    def copywriter(graph_pack, expert_results):
        calls["n"] += 1
        return _valid_copy()

    ledger = run_site_content_for_date(
        date="2026-07-01",
        user="ramsay",
        reports_root=tmp_path,
        conn=conn,
        max_stories=2,
        story_copywriter=copywriter,
    )
    assert calls["n"] >= 1
    assert ledger["generated_story_count"] >= 1
    story_files = list((tmp_path / "ramsay" / "site-stories").rglob("*.json"))
    assert story_files
    story = json.loads(story_files[0].read_text())
    assert story["title"] == _valid_copy()["title"]
    assert story["provenance"]["ai_generated"] is True
    assert story["status"] == "published"

    # A copywriter that returns junk copy (markdown links in public fields)
    # must not survive the quality gate — deterministic copy stays.
    def bad_copywriter(graph_pack, expert_results):
        bad = _valid_copy()
        bad["take"] = "See [link](https://openai.com/news/agents) now"
        return bad

    ledger = run_site_content_for_date(
        date="2026-07-01",
        user="ramsay",
        reports_root=tmp_path,
        conn=conn,
        max_stories=2,
        story_copywriter=bad_copywriter,
    )
    story = json.loads(story_files[0].read_text())
    assert "[link]" not in story["take"]
    assert story["provenance"].get("writer") != "claude-cli"


def test_write_story_copy_retries_once_after_gate_rejection():
    @dataclass
    class OkProcess:
        stdout: str
        stderr: str = ""
        returncode: int = 0
        timed_out: bool = False

    bad = _valid_copy()
    bad["body_markdown"] = "A claim — with an em dash the gate rejects."
    outputs = [json.dumps(bad), json.dumps(_valid_copy())]
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return OkProcess(stdout=outputs[len(calls) - 1])

    result = write_story_copy_with_agent(_graph_pack(), [], voice_text="v", runner=runner)
    assert result == _valid_copy()
    assert len(calls) == 2
    retry_prompt = calls[1][2] if calls[1][:2] == ["claude", "-p"] else str(calls[1])
    assert "rejected by the mechanical copy gate" in str(retry_prompt)


def test_write_story_copy_fails_closed_when_retry_also_rejected():
    @dataclass
    class OkProcess:
        stdout: str
        stderr: str = ""
        returncode: int = 0
        timed_out: bool = False

    bad = _valid_copy()
    bad["body_markdown"] = "A claim — with an em dash the gate rejects."
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return OkProcess(stdout=json.dumps(bad))

    result = write_story_copy_with_agent(_graph_pack(), [], voice_text="v", runner=runner)
    assert result is None
    assert len(calls) == 2
