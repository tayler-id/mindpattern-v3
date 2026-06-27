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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
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
_FOLLOWUP_ACTION_HELP = (
    "Reply `cover` to queue this as a next-day newsletter coverage candidate, "
    "`draft` to run the social post pipeline, `archive`/`save` to store it in "
    "memory and the entity graph, or `ignore` to mark it handled."
)
_FOLLOWUP_ACTION_ALIASES = {
    "cover": "cover",
    "cover tomorrow": "cover",
    "newsletter": "cover",
    "queue": "cover",
    "queue for newsletter": "cover",
    "draft": "draft",
    "social": "draft",
    "social draft": "draft",
    "post draft": "draft",
    "archive": "archive",
    "save": "archive",
    "saved": "archive",
    "store": "archive",
    "ignore": "ignore",
    "ignored": "ignore",
    "reject": "ignore",
    "drop": "ignore",
}
_FOLLOWUP_AGENT_ROLES = [
    {
        "name": "followup-web-researcher",
        "focus": (
            "Find fresh web and primary-source evidence. Prefer official docs, "
            "release notes, original posts, repos, and source pages."
        ),
    },
    {
        "name": "followup-social-researcher",
        "focus": (
            "Find community signal and practitioner discussion. Check Reddit, "
            "X/Twitter, HN, forums, and builder communities when available."
        ),
    },
    {
        "name": "followup-technical-researcher",
        "focus": (
            "Find technical implementation details, tradeoffs, APIs, libraries, "
            "GitHub issues, benchmarks, and operational constraints."
        ),
    },
    {
        "name": "followup-skeptic-researcher",
        "focus": (
            "Verify claims, freshness, duplication risk, counter-evidence, and "
            "whether there is a real why-now angle."
        ),
    },
]
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


def parse_followup_action(text: str | None) -> str | None:
    """Parse a post-result follow-up action.

    These are real workflow actions, separate from the agent's suggested next
    step. Unknown text returns None so approval/edit parsers can handle it.
    """
    normalized = " ".join((text or "").strip().lower().split())
    normalized = normalized.strip(" .!?:;")
    return _FOLLOWUP_ACTION_ALIASES.get(normalized)


def followup_action_help() -> str:
    """Return the Slack-facing action help text."""
    return _FOLLOWUP_ACTION_HELP


def apply_followup_action(
    result: dict[str, Any],
    action_text: str,
    *,
    db=None,
    db_path: Path | str | None = None,
    user_id: str = "ramsay",
    today: str | None = None,
) -> dict[str, Any]:
    """Apply a completed follow-up action to memory/graph state.

    ``draft`` intentionally returns a handoff result: Slack must run the social
    post pipeline because only Slack can enforce the owner approval loop.
    """
    action = parse_followup_action(action_text)
    if not action:
        return {
            "status": "ignored",
            "action": None,
            "message": "No follow-up action matched.",
        }

    if action == "draft":
        return {
            "status": "needs_social_pipeline",
            "action": "draft",
            "message": (
                "Running the existing social draft pipeline from these follow-up "
                "findings. No live post happens without Slack approval."
            ),
        }

    owns_connection = db is None
    if owns_connection:
        import memory

        db = memory.get_db(db_path, user_id=user_id)

    try:
        if action == "cover":
            run_date = _next_day(today)
            persisted = _persist_followup_findings(
                db,
                result,
                run_date=run_date,
                category="followup_cover_candidate",
                importance="high",
                agent_name="followup-cover-candidate",
            )
            return {
                "status": "completed",
                "action": "cover",
                "run_date": run_date,
                **persisted,
                "message": (
                    f"Saved {persisted['finding_count']} follow-up finding(s) "
                    f"as next-day coverage candidates for {run_date}. "
                    "The normal newsletter pipeline will consider them; no "
                    "newsletter was sent now."
                ),
            }

        if action == "archive":
            run_date = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            persisted = _persist_followup_findings(
                db,
                result,
                run_date=run_date,
                category="followup_archive",
                importance="medium",
                agent_name=None,
            )
            return {
                "status": "completed",
                "action": "archive",
                "run_date": run_date,
                **persisted,
                "message": (
                    f"Archived {persisted['finding_count']} follow-up finding(s) "
                    "into memory and linked them into the entity graph."
                ),
            }

        if action == "ignore":
            run_date = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            note_id = _store_followup_note(
                db,
                result,
                run_date=run_date,
                note_type="followup_ignored",
            )
            return {
                "status": "completed",
                "action": "ignore",
                "run_date": run_date,
                "note_id": note_id,
                "finding_count": 0,
                "relationship_count": 0,
                "message": "Marked this follow-up as ignored so it is not treated as an open candidate.",
            }
    finally:
        if owns_connection:
            db.close()

    return {
        "status": "ignored",
        "action": action,
        "message": "No follow-up action was applied.",
    }


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
            "title": "Return workflow actions",
            "summary": (
                "The result would offer owner actions: cover tomorrow, create a "
                "social draft, archive to memory/entity graph, or ignore."
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
        "action_help": _FOLLOWUP_ACTION_HELP,
        "errors": [],
        "artifact": None,
    }


def _live_result(
    request: dict[str, Any],
    *,
    agent_runner: Callable[..., Any] | None,
) -> dict[str, Any]:
    agent_results = _run_followup_agents(request, agent_runner=agent_runner)
    findings = _merge_followup_findings(agent_results)
    errors = [
        f"{result['agent_name']}: {result['error']}"
        for result in agent_results
        if result.get("error")
    ]
    successful_agent_count = sum(1 for result in agent_results if result.get("findings"))
    if not findings:
        return _failed_result(
            query_hash=request["query_hash"],
            query_preview=request["query_preview"],
            reason=_failure_reason(errors),
            mode="live",
        )

    next_action = _first_next_action(agent_results)
    return {
        "status": "completed",
        "degraded": bool(errors),
        "mode": "live",
        "query_hash": request["query_hash"],
        "query_preview": request["query_preview"],
        "findings": findings[:7],
        "why_this_matters": _result_why_this_matters(
            findings,
            agent_count=len(agent_results),
            successful_agent_count=successful_agent_count,
        ),
        "next_action": next_action
        or "Review the follow-up findings, then choose one owner action.",
        "action_help": _FOLLOWUP_ACTION_HELP,
        "errors": errors,
        "agent_count": len(agent_results),
        "successful_agent_count": successful_agent_count,
        "failed_agent_count": len(errors),
        "artifact": None,
    }


def _default_agent_runner(*args, **kwargs):
    from orchestrator.agents import run_single_agent

    return run_single_agent(*args, **kwargs)


def _run_followup_agents(
    request: dict[str, Any],
    *,
    agent_runner: Callable[..., Any] | None,
) -> list[dict[str, Any]]:
    runner = agent_runner or _default_agent_runner
    roles = _FOLLOWUP_AGENT_ROLES
    max_workers = max(1, min(len(roles), _followup_worker_count()))
    indexed_results: dict[int, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_role = {
            executor.submit(
                runner,
                role["name"],
                _build_followup_prompt(request["query"], role),
                task_type="research_agent",
            ): (idx, role)
            for idx, role in enumerate(roles)
        }
        for future in as_completed(future_to_role):
            idx, role = future_to_role[future]
            try:
                agent_payload = _extract_agent_payload(future.result())
                findings = _tag_findings(agent_payload["findings"], role["name"])
                indexed_results[idx] = {
                    "agent_name": role["name"],
                    "findings": findings,
                    "next_action": agent_payload.get("next_action"),
                    "error": None,
                }
            except Exception as exc:
                logger.warning("Follow-up agent %s failed: %s", role["name"], exc)
                indexed_results[idx] = {
                    "agent_name": role["name"],
                    "findings": [],
                    "next_action": None,
                    "error": str(exc),
                }

    return [indexed_results[idx] for idx in sorted(indexed_results)]


def _followup_worker_count() -> int:
    raw = os.environ.get("MP_FOLLOWUP_AGENT_WORKERS", "")
    if not raw:
        return len(_FOLLOWUP_AGENT_ROLES)
    try:
        return int(raw)
    except ValueError:
        return len(_FOLLOWUP_AGENT_ROLES)


def _tag_findings(findings: list[dict[str, Any]], agent_name: str) -> list[dict[str, Any]]:
    tagged = []
    for finding in findings:
        item = dict(finding)
        item.setdefault("agent", agent_name)
        tagged.append(item)
    return tagged


def _merge_followup_findings(agent_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in agent_results:
        for finding in result.get("findings") or []:
            key = (
                _normalize_dedupe_key(finding.get("title")),
                _normalize_dedupe_key(
                    finding.get("source_url") or finding.get("source_name")
                ),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(finding))
    return merged


def _normalize_dedupe_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _first_next_action(agent_results: list[dict[str, Any]]) -> str | None:
    for result in agent_results:
        text = _safe_optional_text(result.get("next_action"))
        if text:
            return text
    return None


def _failure_reason(errors: list[str]) -> str:
    if not errors:
        return "Follow-up research completed without usable findings."
    return "All follow-up agents failed or returned no usable findings: " + "; ".join(errors)


def _build_followup_prompt(query: str, role: dict[str, str] | None = None) -> str:
    role_focus = role["focus"] if role else "Find fresh, source-grounded information."
    return f"""You are running a scoped MindPattern follow-up research pass.

Question:
{query}

Agent focus:
{role_focus}

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
- Do not summarize only existing MindPattern findings; use fresh research and
  external/public evidence when tool access is available.
- Explain why now.
- Do not send newsletters or post social content.
"""


def _extract_agent_payload(agent_result: Any) -> dict[str, Any]:
    """Normalize the live agent boundary into follow-up result fields."""
    if isinstance(agent_result, dict):
        payload = agent_result
    elif isinstance(agent_result, str):
        payload = _parse_agent_payload_text(agent_result)
    else:
        raw_findings = getattr(agent_result, "findings", None) or []
        if raw_findings:
            payload = {"findings": raw_findings}
        else:
            raw_output = str(getattr(agent_result, "raw_output", "") or "").strip()
            payload = _parse_agent_payload_text(raw_output)

    findings = _coerce_findings(payload.get("findings") or [])
    if not findings and payload.get("raw_text"):
        findings = [_raw_text_finding(str(payload["raw_text"]))]
    return {
        "findings": findings,
        "next_action": _safe_optional_text(payload.get("next_action")),
    }


def _parse_agent_payload_text(text: str) -> dict[str, Any]:
    """Parse JSON/fenced JSON when possible; otherwise preserve useful text."""
    clean = (text or "").strip()
    if not clean:
        return {"findings": []}

    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    for block in _extract_balanced_json_blocks(clean):
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    return {"findings": [], "raw_text": clean}


def _extract_balanced_json_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            start = i
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < n:
                ch = text[j]
                if escape:
                    escape = False
                elif ch == "\\":
                    if in_string:
                        escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            blocks.append(text[start : j + 1])
                            i = j
                            break
                j += 1
        i += 1
    return blocks


def _coerce_findings(raw_findings: Any) -> list[dict[str, Any]]:
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


def _raw_text_finding(text: str) -> dict[str, Any]:
    preview = " ".join(text.split())
    if len(preview) > 900:
        preview = preview[:899].rstrip() + "..."
    return {
        "title": "Follow-up response",
        "summary": preview,
        "source_url": None,
        "source_name": "Claude Follow-Up",
    }


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
        "action_help": "",
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
    if result.get("agent_count"):
        lines.extend([
            "",
            "## Agent Coverage",
            "",
            (
                f"{result.get('successful_agent_count', 0)}/"
                f"{result.get('agent_count', 0)} follow-up agents returned usable findings."
            ),
        ])
    lines.extend([
        "",
        "## Suggested Next Step",
        "",
        result.get("next_action", ""),
    ])
    if result.get("action_help"):
        lines.extend(["", "## Available Owner Actions", "", result["action_help"]])
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
        "agent_count": result.get("agent_count"),
        "successful_agent_count": result.get("successful_agent_count"),
        "failed_agent_count": result.get("failed_agent_count"),
        "errors": result.get("errors") or [],
    }
    traces_db.log_event(
        traces_conn,
        FOLLOWUP_PIPELINE_RUN_ID,
        event_type,
        json.dumps(payload, sort_keys=True),
    )


def _result_why_this_matters(
    findings: list[dict[str, Any]],
    *,
    agent_count: int | None = None,
    successful_agent_count: int | None = None,
) -> str:
    first = findings[0]
    if agent_count:
        return (
            f"The follow-up ran {agent_count} focused research agent(s); "
            f"{successful_agent_count or 0} returned usable findings. "
            f"Start with: {first.get('title', 'the strongest finding')}."
        )
    return (
        f"The follow-up found {len(findings)} source-grounded item(s). "
        f"Start with: {first.get('title', 'the strongest finding')}."
    )


def _persist_followup_findings(
    db,
    result: dict[str, Any],
    *,
    run_date: str,
    category: str,
    importance: str,
    agent_name: str | None,
) -> dict[str, Any]:
    import memory

    try:
        from kg.schema import init_kg_schema

        init_kg_schema(db)
    except Exception as exc:
        logger.warning("KG schema init failed during follow-up persistence: %s", exc)

    finding_ids: list[int] = []
    relationship_count = 0
    for finding in result.get("findings") or []:
        title = str(finding.get("title") or "").strip()
        summary = str(finding.get("summary") or "").strip()
        if not title or not summary:
            continue

        agent = agent_name or str(finding.get("agent") or "followup-research")
        existing = db.execute(
            """SELECT id FROM findings
               WHERE run_date = ? AND agent = ? AND title = ? AND category = ?
               LIMIT 1""",
            (run_date, agent, title, category),
        ).fetchone()
        if existing:
            finding_id = int(existing["id"])
        else:
            finding_id = memory.store_finding(
                db,
                run_date=run_date,
                agent=agent,
                title=title,
                summary=_followup_summary_with_context(summary, result),
                importance=importance,
                category=category,
                source_url=finding.get("source_url"),
                source_name=finding.get("source_name"),
            )
        finding_ids.append(finding_id)
        relationship_count += _link_followup_finding(db, finding, finding_id, result)

    return {
        "finding_ids": finding_ids,
        "finding_count": len(finding_ids),
        "relationship_count": relationship_count,
    }


def _followup_summary_with_context(summary: str, result: dict[str, Any]) -> str:
    preview = result.get("query_preview") or ""
    artifact = result.get("artifact") or ""
    suffix_parts = []
    if preview:
        suffix_parts.append(f"Follow-up query: {preview}")
    if artifact:
        suffix_parts.append(f"Artifact: {artifact}")
    if not suffix_parts:
        return summary
    return f"{summary}\n\n" + "\n".join(suffix_parts)


def _link_followup_finding(
    db,
    finding: dict[str, Any],
    finding_id: int,
    result: dict[str, Any],
) -> int:
    import memory

    title = str(finding.get("title") or "Untitled follow-up")[:100]
    count = 0
    memory.store_relationship(
        db,
        entity_a="Follow-Up Research",
        relationship="surfaced",
        entity_b=title,
        entity_a_type="workflow",
        entity_b_type="topic",
        finding_id=finding_id,
    )
    count += 1

    source_name = str(finding.get("source_name") or "").strip()
    if source_name and source_name.lower() not in {"unknown", "dry run"}:
        memory.store_relationship(
            db,
            entity_a=source_name[:100],
            relationship="reported_on",
            entity_b=title,
            entity_a_type="source",
            entity_b_type="topic",
            finding_id=finding_id,
        )
        count += 1

    query_preview = str(result.get("query_preview") or "").strip()
    if query_preview:
        memory.store_relationship(
            db,
            entity_a=query_preview[:100],
            relationship="led_to",
            entity_b=title,
            entity_a_type="question",
            entity_b_type="topic",
            finding_id=finding_id,
        )
        count += 1
    return count


def _store_followup_note(
    db,
    result: dict[str, Any],
    *,
    run_date: str,
    note_type: str,
) -> int:
    import memory

    titles = [
        str(f.get("title") or "Untitled")
        for f in (result.get("findings") or [])[:5]
    ]
    content = {
        "query_hash": result.get("query_hash", ""),
        "query_preview": result.get("query_preview", ""),
        "artifact": result.get("artifact", ""),
        "finding_titles": titles,
    }
    return memory.store_note(
        db,
        run_date=run_date,
        agent="followup-research",
        note_type=note_type,
        content=json.dumps(content, sort_keys=True),
    )


def _next_day(today: str | None) -> str:
    if today:
        base = datetime.strptime(today, "%Y-%m-%d")
    else:
        base = datetime.now(timezone.utc).replace(tzinfo=None)
    return (base + timedelta(days=1)).strftime("%Y-%m-%d")


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
