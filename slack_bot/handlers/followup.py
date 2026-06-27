"""Slack helpers for scoped follow-up research.

Follow-up replies are intentionally handled inside existing owner-polled
approval loops. The global Slack router still ignores thread replies so a
follow-up cannot start a second social or newsletter pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.followup import (
    apply_followup_action,
    followup_action_help,
    parse_followup_action,
    parse_followup_request,
    run_followup_research,
)
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
    remember_followup_result(handler, result, channel_type=channel_type)
    handler.reply(format_followup_result(result), thread_ts=thread_ts)
    return True


def remember_followup_result(
    handler,
    result: dict[str, Any],
    *,
    channel_type: str,
) -> None:
    """Attach the latest follow-up result to a handler for the next reply."""
    if result.get("status") != "completed" or not result.get("findings"):
        return
    handler._last_followup_result = result
    handler._last_followup_channel_type = channel_type


def handle_followup_action_reply(
    handler,
    reply_text: str,
    thread_ts: str,
    *,
    channel_type: str,
) -> bool:
    """Apply cover/draft/archive/ignore to the last follow-up result."""
    action = parse_followup_action(reply_text)
    if not action:
        return False

    result = getattr(handler, "_last_followup_result", None)
    if not result:
        handler.reply(
            "I do not have a recent follow-up result to apply that action to.",
            thread_ts=thread_ts,
        )
        return True

    if action == "draft":
        handler.reply(
            "Creating social drafts from the follow-up findings with the existing post pipeline...",
            thread_ts=thread_ts,
        )
        setattr(handler, "_last_followup_result", None)
        _run_social_draft_pipeline(handler, result, thread_ts)
        return True

    action_result = apply_followup_action(result, action)
    setattr(handler, "_last_followup_result", None)
    handler.reply(action_result["message"], thread_ts=thread_ts)
    return True


def format_followup_result(result: dict[str, Any]) -> str:
    """Format follow-up research for phone-readable Slack review."""
    status = result.get("status", "unknown")
    header = f"*Follow-up research*: {status}"
    if result.get("degraded"):
        header += " :warning:"

    lines = [header]
    if result.get("agent_count"):
        lines.append(
            f"Agents: {result.get('successful_agent_count', 0)}/"
            f"{result.get('agent_count', 0)} returned usable findings"
        )
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
        lines.extend(["", f"*Suggested next step:* {result['next_action']}"])
    action_help = result.get("action_help") or followup_action_help()
    if result.get("status") == "completed" and findings and action_help:
        lines.extend(["", f"*Actions:* {action_help}"])
    if result.get("artifact"):
        lines.append(f"Artifact: `{result['artifact']}`")

    return "\n".join(lines)


def _run_social_draft_pipeline(handler, result: dict[str, Any], thread_ts: str) -> None:
    topic = _followup_result_to_social_topic(result)
    if hasattr(handler, "_run_and_approve"):
        handler._run_and_approve(topic, thread_ts)
        return

    from slack_bot.handlers.posts import PostsHandler

    post_handler = PostsHandler(
        client=handler.client,
        channel_id=handler.channel_id,
        owner_user_id=handler.owner_user_id,
    )
    post_handler._run_and_approve(topic, thread_ts)


def _followup_result_to_social_topic(result: dict[str, Any]) -> dict[str, Any]:
    findings = result.get("findings") or []
    anchor_parts = []
    source_urls = []
    for finding in findings[:5]:
        title = finding.get("title", "Untitled")
        summary = finding.get("summary", "")
        anchor_parts.append(f"{title}: {summary}".strip())
        if finding.get("source_url"):
            source_urls.append(finding["source_url"])

    query_preview = result.get("query_preview") or "Follow-up research"
    anchor = "\n\n".join(anchor_parts) or query_preview
    return {
        "anchor": anchor,
        "anchor_source": f"Follow-up research: {query_preview}",
        "connection": result.get("why_this_matters", ""),
        "connection_source": result.get("artifact", ""),
        "reaction": (
            "Turn this follow-up research into social post drafts. Use the "
            "strongest source-backed angle and keep the owner approval gate."
        ),
        "source_urls": list(dict.fromkeys(source_urls)),
        "confidence": "HIGH",
    }


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
            "action_help": "",
            "errors": [str(exc)],
            "artifact": None,
        }
