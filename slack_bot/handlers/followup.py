"""Slack helpers for scoped follow-up research.

Follow-up replies are intentionally handled inside existing owner-polled
approval loops. The global Slack router still ignores thread replies so a
follow-up cannot start a second social or newsletter pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.followup import parse_followup_request, run_followup_research
from orchestrator.traces_db import open_traces_db

logger = logging.getLogger(__name__)


def handle_followup_reply(
    handler,
    reply_text: str,
    thread_ts: str,
    *,
    channel_type: str,
) -> bool:
    """Run a follow-up command if ``reply_text`` contains one.

    Returns True when the reply was a follow-up command and should be consumed.
    Returns False for normal approval/edit text so callers can continue their
    existing approval parsing.
    """
    request = parse_followup_request(reply_text, channel_type=channel_type)
    if request is None:
        return False

    if request.get("error"):
        handler.reply(request["error"], thread_ts=thread_ts)
        return True

    handler.reply("Running follow-up research...", thread_ts=thread_ts)
    result = _run_with_trace_fallback(request)
    handler.reply(format_followup_result(result), thread_ts=thread_ts)
    return True


def format_followup_result(result: dict[str, Any]) -> str:
    """Format follow-up research for phone-readable Slack review."""
    status = result.get("status", "unknown")
    header = f"*Follow-up research*: {status}"
    if result.get("degraded"):
        header += " :warning:"

    lines = [header]
    if result.get("why_this_matters"):
        lines.extend(["", f"*Why this matters:* {result['why_this_matters']}"])

    findings = result.get("findings") or []
    if findings:
        lines.append("")
        lines.append("*Findings:*")
        for idx, finding in enumerate(findings[:7], 1):
            title = finding.get("title", "Untitled")
            summary = finding.get("summary", "")
            source = finding.get("source_url") or finding.get("source_name")
            line = f"{idx}. *{title}*"
            if summary:
                line += f" - {summary}"
            if source:
                line += f"\n   Source: {source}"
            lines.append(line)
    else:
        lines.extend(["", "No usable findings returned."])

    if result.get("next_action"):
        lines.extend(["", f"*Next action:* {result['next_action']}"])
    if result.get("artifact"):
        lines.append(f"Artifact: `{result['artifact']}`")

    return "\n".join(lines)


def _run_with_trace_fallback(request: dict[str, Any]) -> dict[str, Any]:
    try:
        with open_traces_db() as traces_conn:
            return run_followup_research(request, traces_conn=traces_conn)
    except Exception as exc:
        logger.warning("Follow-up trace setup failed; running without trace: %s", exc)

    try:
        return run_followup_research(request)
    except Exception as exc:
        logger.exception("Follow-up research failed before returning a result")
        return {
            "status": "failed",
            "degraded": True,
            "findings": [],
            "why_this_matters": f"Follow-up research failed: {exc}",
            "next_action": "Retry with a more specific question or inspect source health.",
            "errors": [str(exc)],
            "artifact": None,
        }
