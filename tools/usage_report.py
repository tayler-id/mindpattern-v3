#!/usr/bin/env python3
"""Model usage for one pipeline day, read from Claude Code session transcripts.

Every `claude -p` the pipeline starts leaves a transcript under
~/.claude/projects/<project>/. This totals their token usage by task and model
and prices it at API list rates from config/pricing.json. It is the baseline
until traces.db model_calls records usage at call time.

    .venv/bin/python3 tools/usage_report.py --date 2026-10-01
    .venv/bin/python3 tools/usage_report.py --date 2026-10-01 --json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRICING = PROJECT_ROOT / "config" / "pricing.json"
DEFAULT_TRANSCRIPTS = Path.home() / ".claude" / "projects" / "-Users-taylerramsay-Projects-mindpattern-v3"

# First-prompt prefixes of each pipeline call. Order matters: first match wins.
# The site writer's revision and gate-retry prompts start with the writer prompt,
# so they count as site_story_writer.
TASK_SIGNATURES: list[tuple[str, re.Pattern[str]]] = [
    ("research_agent", re.compile(r"CRITICAL: Output ONLY valid JSON matching this schema")),
    ("site_story_writer", re.compile(r"Write one Rabbit Hole site story")),
    ("site_story_critic", re.compile(r"Judge this Rabbit Hole story draft")),
    ("story_selection", re.compile(r"Select exactly \d+ stories")),
    ("newsletter_writer", re.compile(r"OUTPUT CONTRACT: Your stdout is published verbatim")),
    ("kg_extract", re.compile(r"You are an information-extraction system for an AI-industry knowledge graph")),
    ("knowledge_flush_hook", re.compile(r"You are a knowledge extraction assistant")),
    ("identity_evolve", re.compile(r"You are the EVOLVE phase")),
    ("learnings_update", re.compile(r"Date: \d{4}-\d{2}-\d{2}\s+Database stats:")),
]

_DATE_SUFFIX = re.compile(r"-\d{8}$")
# `claude -p -` reads the prompt from stdin, and the transcript keeps the "-"
# argument as the prompt's first line.
_STDIN_MARKER = re.compile(r"^-\s*\n")


@dataclass(frozen=True)
class Response:
    """One API response. A response spans several transcript lines that repeat its usage."""

    task: str
    model: str
    input_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    output_tokens: int


def classify(first_prompt: str) -> str:
    text = _STDIN_MARKER.sub("", first_prompt.lstrip())
    for task, pattern in TASK_SIGNATURES:
        if pattern.match(text):
            return task
    return "other"


def normalize_model(model: str) -> str:
    return _DATE_SUFFIX.sub("", model or "unknown")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def read_session(path: Path) -> tuple[date | None, list[Response]]:
    """The session's local start date and its deduplicated responses."""
    started: date | None = None
    task = "other"
    seen: set[tuple[str, str]] = set()
    responses: list[Response] = []
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if started is None and entry.get("timestamp"):
                stamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                started = stamp.astimezone().date()
            message = entry.get("message") or {}
            if entry.get("type") == "user" and task == "other" and not responses:
                task = classify(_text_of(message.get("content")))
            usage = message.get("usage")
            if entry.get("type") != "assistant" or not usage:
                continue
            key = (str(message.get("id")), str(entry.get("requestId")))
            if key in seen:
                continue
            seen.add(key)
            responses.append(Response(
                task=task,
                model=normalize_model(message.get("model", "")),
                input_tokens=int(usage.get("input_tokens") or 0),
                cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ))
    return started, responses


def price(response: Response, pricing: dict[str, dict[str, float]]) -> float | None:
    rates = pricing.get(response.model)
    if rates is None:
        return None
    return (
        response.input_tokens * rates["input"]
        + response.cache_write_tokens * rates["cache_write"]
        + response.cache_read_tokens * rates["cache_read"]
        + response.output_tokens * rates["output"]
    ) / 1_000_000


def build_report(transcripts: Path, day: date, pricing: dict[str, dict[str, float]]) -> dict:
    # mtime is only a prefilter: a session that ends on `day` can't have been
    # modified before it starts. The entry timestamps decide attribution.
    earliest = datetime.combine(day, datetime.min.time()).timestamp()
    rows: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "sessions": 0, "responses": 0, "input_tokens": 0, "cache_write_tokens": 0,
        "cache_read_tokens": 0, "output_tokens": 0, "api_price_usd": 0.0, "unpriced_responses": 0,
    })
    for path in sorted(transcripts.glob("*.jsonl")):
        if path.stat().st_mtime < earliest:
            continue
        started, responses = read_session(path)
        if started != day or not responses:
            continue
        counted: set[tuple[str, str]] = set()
        for response in responses:
            row = rows[(response.task, response.model)]
            if (response.task, response.model) not in counted:
                row["sessions"] += 1
                counted.add((response.task, response.model))
            row["responses"] += 1
            row["input_tokens"] += response.input_tokens
            row["cache_write_tokens"] += response.cache_write_tokens
            row["cache_read_tokens"] += response.cache_read_tokens
            row["output_tokens"] += response.output_tokens
            cost = price(response, pricing)
            if cost is None:
                row["unpriced_responses"] += 1
            else:
                row["api_price_usd"] += cost
    ordered = sorted(rows.items(), key=lambda item: -item[1]["api_price_usd"])
    report_rows = [
        {"task": task, "model": model, **values, "api_price_usd": round(values["api_price_usd"], 2)}
        for (task, model), values in ordered
    ]
    totals = {
        key: sum(row[key] for row in report_rows)
        for key in ("responses", "input_tokens", "cache_write_tokens", "cache_read_tokens",
                    "output_tokens", "unpriced_responses")
    }
    totals["api_price_usd"] = round(sum(row["api_price_usd"] for row in report_rows), 2)
    return {"date": day.isoformat(), "transcripts": str(transcripts), "rows": report_rows, "totals": totals}


def render_text(report: dict) -> str:
    header = f"{'task':22} {'model':18} {'sess':>5} {'resp':>5} {'output':>10} {'new in':>10} {'cache wr':>10} {'cache rd':>12} {'API $':>8}"
    lines = [f"Model usage for {report['date']}", header, "-" * len(header)]
    for row in report["rows"]:
        lines.append(
            f"{row['task']:22} {row['model']:18} {row['sessions']:>5} {row['responses']:>5} "
            f"{row['output_tokens']:>10,} {row['input_tokens']:>10,} {row['cache_write_tokens']:>10,} "
            f"{row['cache_read_tokens']:>12,} {row['api_price_usd']:>8.2f}"
        )
    totals = report["totals"]
    lines.append("-" * len(header))
    lines.append(
        f"{'total':22} {'':18} {'':>5} {totals['responses']:>5} {totals['output_tokens']:>10,} "
        f"{totals['input_tokens']:>10,} {totals['cache_write_tokens']:>10,} "
        f"{totals['cache_read_tokens']:>12,} {totals['api_price_usd']:>8.2f}"
    )
    if totals["unpriced_responses"]:
        lines.append(f"{totals['unpriced_responses']} responses used a model missing from the pricing file.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="local date, YYYY-MM-DD")
    parser.add_argument("--transcripts", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING)
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)

    if not args.transcripts.is_dir():
        print(f"transcripts directory not found: {args.transcripts}", file=sys.stderr)
        return 2
    pricing = json.loads(args.pricing.read_text())["models"]
    report = build_report(args.transcripts, args.date, pricing)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
