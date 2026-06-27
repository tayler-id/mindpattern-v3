"""Scoped follow-up research service for Slack commands.

This module is deliberately separate from the daily runner. A follow-up request
can research one topic and return a small result, but it must not send
newsletters, post social content, sync Fly, or run the full daily pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from orchestrator import traces_db

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT_DIR = PROJECT_ROOT / "reports" / "ramsay" / "followups"
FOLLOWUP_PIPELINE_RUN_ID = "followup-research"
MIN_QUERY_CHARS = 8
PREVIEW_CHARS = 120

_COMMAND_PREFIXES = ("follow up:", "follow-up:", "research this:")
_VAGUE_QUERIES = {"more", "this", "that", "it", "details", "why"}
_SECRET_PATTERNS = [
    re.compile(r"xox[a-z]-[A-Za-z0-9-]+"),
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(
        r"(?i)\b(api[_ -]?key|token|secret|password)\b\s*[:=]\s*\S+"
    ),
]


def parse_followup_request(
    text: str,
    *,
    source: str = "slack",
    channel_type: str | None = None,
) -> dict[str, Any] | None:
    """Parse a follow-up command into a safe request contract.

    Returns ``None`` when the text is not a follow-up command. Returns a request
    with ``error`` populated for recognized but invalid follow-up commands.
    """
    raw_text = (text or "").strip()
    lower = raw_text.lower()

    matched_prefix = None
    for prefix in _COMMAND_PREFIXES:
        if lower.startswith(prefix):
            matched_prefix = prefix
            break

    if matched_prefix is None:
        return None

    query = raw_text[len(matched_prefix):].strip()
    if len(query) < MIN_QUERY_CHARS or query.lower() in _VAGUE_QUERIES:
        return {
            "command": "follow_up",
            "source": source,
            "channel_type": channel_type,
            "query": "",
            "query_hash": "",
            "query_preview": "",
            "error": "Follow-up request needs a more specific topic, URL, or question.",
        }

    return {
        "command": "follow_up",
        "source": source,
        "channel_type": channel_type,
        "query": query,
        "query_hash": _hash_text(query),
        "query_preview": _safe_preview(query),
        "error": None,
    }


def run_followup_research(
    request: dict[str, Any] | str | None,
    *,
    dry_run: bool | None = None,
    traces_conn=None,
    artifact_dir: Path | str | None = None,
    agent_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run scoped follow-up research and return a structured result."""
    parsed = parse_followup_request(request) if isinstance(request, str) else request
    if not parsed:
        result = _failed_result(
            query_hash="",
            query_preview="",
            reason="No follow-up command was provided.",
            mode="dry_run",
        )
        return _finalize_result(result, traces_conn=traces_conn, artifact_dir=artifact_dir)

    if parsed.get("error"):
        result = _failed_result(
            query_hash=parsed.get("query_hash", ""),
            query_preview=parsed.get("query_preview", ""),
            reason=parsed["error"],
            mode="dry_run",
        )
        return _finalize_result(result, traces_conn=traces_conn, artifact_dir=artifact_dir)

    selected_dry_run = _should_dry_run(dry_run)
    if selected_dry_run:
        result = _dry_run_result(parsed)
    else:
        result = _live_result(parsed, agent_runner=agent_runner)

    return _finalize_result(result, traces_conn=traces_conn, artifact_dir=artifact_dir)


def _should_dry_run(dry_run: bool | None) -> bool:
    if dry_run is not None:
        return dry_run
    return (
        os.environ.get("MP_DISABLE_OUTBOUND") == "1"
        or os.environ.get("MP_FOLLOWUP_DRY_RUN") == "1"
        or os.environ.get("MP_DRY_RUN") == "1"
    )


def _dry_run_result(request: dict[str, Any]) -> dict[str, Any]:
    preview = request["query_preview"]
    findings = [
        {
            "title": "Identify primary sources",
            "summary": (
                f"Dry-run follow-up for '{preview}' would first collect primary "
                "sources and official artifacts before synthesis."
            ),
            "source_name": "Dry Run",
            "source_url": None,
        },
        {
            "title": "Check freshness and prior coverage",
            "summary": (
                "The follow-up would compare the angle against recent coverage "
                "so old stories do not resurface without a new reason."
            ),
            "source_name": "Dry Run",
            "source_url": None,
        },
        {
            "title": "Look for builder impact",
            "summary": (
                "The research pass would extract what changed, why now, and what "
                "a builder or operator can do with it."
            ),
            "source_name": "Dry Run",
            "source_url": None,
        },
        {
            "title": "Return a next action",
            "summary": (
                "The result would recommend whether to cover tomorrow, turn into "
                "a social angle, archive, or ignore."
            ),
            "source_name": "Dry Run",
            "source_url": None,
        },
    ]
    return {
        "status": "completed",
        "degraded": False,
        "mode": "dry_run",
        "query_hash": request["query_hash"],
        "query_preview": preview,
        "findings": findings,
        "why_this_matters": (
            "Dry-run mode proves the follow-up path without calling Claude, "
            "network, Slack, email, social APIs, Fly, or the daily runner."
        ),
        "next_action": "Use a live follow-up only after owner-approved runtime access.",
        "errors": [],
        "artifact": None,
    }


def _live_result(
    request: dict[str, Any],
    *,
    agent_runner: Callable[..., Any] | None,
) -> dict[str, Any]:
    runner = agent_runner or _default_agent_runner
    try:
        agent_result = runner(
            "follow-up-researcher",
            _build_followup_prompt(request["query"]),
            task_type="research_agent",
        )
    except Exception as exc:
        logger.warning("Follow-up agent execution failed: %s", exc)
        return _failed_result(
            query_hash=request["query_hash"],
            query_preview=request["query_preview"],
            reason="Follow-up research failed before producing findings.",
            mode="live",
        )

    findings = _extract_findings(agent_result)
    if not findings:
        return _failed_result(
            query_hash=request["query_hash"],
            query_preview=request["query_preview"],
            reason="Follow-up research completed without usable findings.",
            mode="live",
        )

    return {
        "status": "completed",
        "degraded": False,
        "mode": "live",
        "query_hash": request["query_hash"],
        "query_preview": request["query_preview"],
        "findings": findings[:7],
        "why_this_matters": _result_why_this_matters(findings),
        "next_action": "Review the follow-up findings and decide whether to cover, draft, archive, or ignore.",
        "errors": [],
        "artifact": None,
    }


def _default_agent_runner(*args, **kwargs):
    from orchestrator.agents import run_single_agent

    return run_single_agent(*args, **kwargs)


def _build_followup_prompt(query: str) -> str:
    return f"""You are running a scoped MindPattern follow-up research pass.

Question:
{query}

Return JSON only:
{{
  "findings": [
    {{
      "title": "specific title",
      "summary": "2-3 sentence summary with why it matters",
      "source_url": "public URL or null",
      "source_name": "source name"
    }}
  ],
  "next_action": "cover tomorrow | social angle | archive | ignore"
}}

Requirements:
- Find fresh, source-grounded information.
- Prefer primary sources.
- Explain why now.
- Do not send newsletters or post social content.
"""


def _extract_findings(agent_result: Any) -> list[dict[str, Any]]:
    if isinstance(agent_result, dict):
        raw_findings = agent_result.get("findings") or []
    else:
        raw_findings = getattr(agent_result, "findings", None) or []

    findings = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not title or not summary:
            continue
        findings.append({
            "title": title,
            "summary": summary,
            "source_url": item.get("source_url"),
            "source_name": item.get("source_name") or item.get("source") or "Unknown",
        })
    return findings


def _failed_result(
    *,
    query_hash: str,
    query_preview: str,
    reason: str,
    mode: str,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "degraded": True,
        "mode": mode,
        "query_hash": query_hash,
        "query_preview": query_preview,
        "findings": [],
        "why_this_matters": f"Follow-up research failed: {reason}",
        "next_action": "Retry with a more specific question or inspect source health.",
        "errors": [reason],
        "artifact": None,
    }


def _finalize_result(
    result: dict[str, Any],
    *,
    traces_conn,
    artifact_dir: Path | str | None,
) -> dict[str, Any]:
    result = dict(result)
    result["artifact"] = str(_write_artifact(result, artifact_dir))
    if traces_conn is not None:
        _log_trace(traces_conn, result)
    return result


def _write_artifact(result: dict[str, Any], artifact_dir: Path | str | None) -> Path:
    target_dir = Path(artifact_dir) if artifact_dir is not None else DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(result.get("query_preview") or "followup")
    suffix = (result.get("query_hash") or _hash_text(slug)).split(":", 1)[-1][:8]
    path = target_dir / f"{today}-{slug}-{suffix}.md"

    lines = [
        f"# Follow-Up Research - {today}",
        "",
        f"Status: {result.get('status', 'unknown')}",
        f"Mode: {result.get('mode', 'unknown')}",
        f"Query preview: {result.get('query_preview', '')}",
        "",
        "## Why This Matters",
        "",
        result.get("why_this_matters", ""),
        "",
        "## Findings",
        "",
    ]
    findings = result.get("findings") or []
    if not findings:
        lines.append("- No findings returned.")
    else:
        for finding in findings:
            lines.append(f"- {finding.get('title', 'Untitled')}")
            lines.append(f"  {finding.get('summary', '')}")
            source_url = finding.get("source_url")
            if source_url:
                lines.append(f"  Source: {source_url}")
    lines.extend(["", "## Next Action", "", result.get("next_action", "")])
    path.write_text("\n".join(lines).strip() + "\n")
    return path


def _log_trace(traces_conn, result: dict[str, Any]) -> None:
    event_type = (
        "followup_research_complete"
        if result.get("status") == "completed"
        else "followup_research_failed"
    )
    payload = {
        "source": "slack",
        "query_hash": result.get("query_hash", ""),
        "query_preview": result.get("query_preview", ""),
        "status": result.get("status", "unknown"),
        "degraded": bool(result.get("degraded")),
        "mode": result.get("mode", "unknown"),
        "finding_count": len(result.get("findings") or []),
        "artifact": result.get("artifact"),
        "errors": result.get("errors") or [],
    }
    traces_db.log_event(
        traces_conn,
        FOLLOWUP_PIPELINE_RUN_ID,
        event_type,
        json.dumps(payload, sort_keys=True),
    )


def _result_why_this_matters(findings: list[dict[str, Any]]) -> str:
    first = findings[0]
    return (
        f"The follow-up found {len(findings)} source-grounded item(s). "
        f"Start with: {first.get('title', 'the strongest finding')}."
    )


def _hash_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _safe_preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    preview = " ".join((text or "").split())
    for pattern in _SECRET_PATTERNS:
        preview = pattern.sub("[redacted]", preview)
    if len(preview) > limit:
        return preview[: limit - 1].rstrip() + "..."
    return preview


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "followup"

