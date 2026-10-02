"""tools/usage_report.py totals one day of pipeline usage from session transcripts.

A Claude Code transcript writes one API response as several lines that each
repeat the response's usage. Summing lines counted Oct 1 2026 about 2.5 times
over (1,582 usage lines, 634 responses), so responses are deduplicated by id.
"""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("usage_report", PROJECT_ROOT / "tools" / "usage_report.py")
usage_report = importlib.util.module_from_spec(SPEC)
sys.modules["usage_report"] = usage_report
SPEC.loader.exec_module(usage_report)

PRICING = json.loads((PROJECT_ROOT / "config" / "pricing.json").read_text())["models"]


def _session(path: Path, *, prompt: str, stamp: str, responses: list[tuple[str, str, dict, int]]) -> None:
    """responses: (message id, model, usage, number of transcript lines it spans)."""
    lines = [{"type": "user", "timestamp": stamp, "message": {"role": "user", "content": prompt}}]
    for message_id, model, usage, copies in responses:
        for _ in range(copies):
            lines.append({
                "type": "assistant", "timestamp": stamp, "requestId": f"req-{message_id}",
                "message": {"id": message_id, "model": model, "usage": usage, "content": []},
            })
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _usage(input_tokens=0, cache_write=0, cache_read=0, output=0) -> dict:
    return {"input_tokens": input_tokens, "cache_creation_input_tokens": cache_write,
            "cache_read_input_tokens": cache_read, "output_tokens": output}


def _write_day(root: Path) -> None:
    _session(root / "research.jsonl", prompt="CRITICAL: Output ONLY valid JSON matching this schema.",
             stamp="2026-10-01T12:00:00Z", responses=[
                 ("m1", "claude-opus-5-5", _usage(100_000, 1_000_000, 10_000_000, 500_000), 3),
                 ("m2", "claude-opus-5-5", _usage(0, 0, 5_000_000, 250_000), 1),
             ])
    _session(root / "writer.jsonl", prompt="Write one Rabbit Hole site story from the evidence pack below.",
             stamp="2026-10-01T13:00:00Z", responses=[
                 ("w1", "claude-sonnet-5", _usage(output=1_000_000), 2),
             ])
    _session(root / "kg.jsonl", prompt="You are an information-extraction system for an AI-industry knowledge graph.",
             stamp="2026-10-01T14:00:00Z", responses=[
                 ("k1", "claude-haiku-4-5-20251001", _usage(output=200_000), 1),
             ])
    _session(root / "mystery.jsonl", prompt="hello there",
             stamp="2026-10-01T15:00:00Z", responses=[
                 ("x1", "claude-mystery-9", _usage(output=10), 1),
             ])
    _session(root / "yesterday.jsonl", prompt="CRITICAL: Output ONLY valid JSON matching this schema.",
             stamp="2026-09-30T12:00:00Z", responses=[
                 ("y1", "claude-opus-5-5", _usage(output=9_000_000), 1),
             ])


def test_day_totals_count_each_response_once_and_price_it(tmp_path):
    _write_day(tmp_path)

    report = usage_report.build_report(tmp_path, date(2026, 10, 1), PRICING)

    summary = [
        (row["task"], row["model"], row["sessions"], row["responses"], row["output_tokens"],
         row["cache_read_tokens"], row["api_price_usd"])
        for row in report["rows"]
    ]
    assert summary == [
        ("research_agent", "claude-opus-5-5", 1, 2, 750_000, 15_000_000, 23.4),
        ("site_story_writer", "claude-sonnet-5", 1, 1, 1_000_000, 0, 10.0),
        ("kg_extract", "claude-haiku-4-5", 1, 1, 200_000, 0, 1.0),
        ("other", "claude-mystery-9", 1, 1, 10, 0, 0.0),
    ]
    assert report["totals"]["output_tokens"] == 1_950_010
    assert report["totals"]["api_price_usd"] == 34.4
    assert report["totals"]["unpriced_responses"] == 1


def test_text_report_and_json_flag_from_the_command_line(tmp_path, capsys):
    _write_day(tmp_path)

    assert usage_report.main(["--date", "2026-10-01", "--transcripts", str(tmp_path), "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["totals"]["api_price_usd"] == 34.4

    assert usage_report.main(["--date", "2026-10-01", "--transcripts", str(tmp_path)]) == 0
    table = capsys.readouterr().out
    assert "research_agent" in table
    assert "1 responses used a model missing from the pricing file." in table


def test_missing_transcripts_directory_exits_2(tmp_path, capsys):
    assert usage_report.main(["--date", "2026-10-01", "--transcripts", str(tmp_path / "absent")]) == 2
    assert "transcripts directory not found" in capsys.readouterr().err


def test_stdin_prompts_are_classified_without_the_dash_line():
    assert usage_report.classify("-\nOUTPUT CONTRACT: Your stdout is published verbatim to subscribers") == "newsletter_writer"
    assert usage_report.classify("-\nSelect exactly 5 stories from these 181 findings") == "story_selection"
    assert usage_report.classify("Select exactly 5 stories from these 181 findings") == "story_selection"
