"""Short-form video script contracts and command parsing.

Feature 21 starts with strict Slack command parsing and stable public package
objects. Generation, Slack wiring, file upload, and any MP4 provider adapter
are later tasks.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import (
    normalize_artifact_slug,
    redact_sensitive_text,
    validate_run_date,
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"

MIN_QUERY_CHARS = 8
PREVIEW_CHARS = 160

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_ARC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_SAFE_LABEL_RE = re.compile(r"[^a-z0-9_-]+")
_VAGUE_QUERIES = {"more", "this", "that", "it", "details", "ideas"}
_LIVE_POST_RE = re.compile(
    r"\b(post|publish|send|upload|schedule)\b.*"
    r"\b(tiktok|instagram|reels|youtube|shorts|linkedin|bluesky|twitter|x|social|live)\b|"
    r"\blive\s+post\b",
    re.IGNORECASE,
)
_NEWSLETTER_CONTROL_RE = re.compile(
    r"\b(send|publish|approve|select|pick|write|block)\s+"
    r"(the\s+)?(newsletter|issue|story|stories)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoScriptPackage:
    """Stable public package contract for a Slack-ready video script."""

    package_id: str
    date: str
    source_type: str
    source_ref: str
    duration_seconds: int
    hook: str
    spoken_script: str
    shot_list: list[str]
    captions: list[str]
    source_urls: list[str]
    labels: list[str]
    risk_labels: list[str]
    status: str = "ready"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "package_id": _safe_label(self.package_id),
            "date": validate_run_date(self.date),
            "source_type": _safe_label(self.source_type),
            "source_ref": redact_sensitive_text(self.source_ref),
            "duration_seconds": _safe_duration(self.duration_seconds),
            "status": _safe_label(self.status),
            "hook": redact_sensitive_text(self.hook),
            "spoken_script": redact_sensitive_text(self.spoken_script),
            "shot_list": [redact_sensitive_text(item) for item in self.shot_list],
            "captions": [redact_sensitive_text(item) for item in self.captions],
            "source_urls": _safe_urls(self.source_urls),
            "labels": [redact_sensitive_text(item) for item in self.labels],
            "risk_labels": [redact_sensitive_text(item) for item in self.risk_labels],
        }


def parse_video_script_request(
    text: str | None,
    *,
    source: str = "slack",
    channel_type: str | None = None,
) -> dict[str, Any] | None:
    """Parse a Slack video command into a stable request dict.

    Returns ``None`` when the text is not a video command. Recognized but
    invalid commands return a request with ``error`` populated so callers can
    reply without falling through to approval, posting, or generation logic.
    """
    raw_text = (text or "").strip()
    lower = raw_text.lower()
    if not raw_text:
        return None

    finding_match = re.fullmatch(r"video\s+finding\s+(.+)", raw_text, re.IGNORECASE)
    if finding_match:
        value = finding_match.group(1).strip()
        if not value.isdigit() or int(value) <= 0:
            return _error_request(
                "Video script request needs a numeric finding ID.",
                source=source,
                channel_type=channel_type,
            )
        finding_id = int(value)
        return _request(
            source_type="finding",
            source=source,
            channel_type=channel_type,
            query=f"finding:{finding_id}",
            finding_id=finding_id,
        )

    arc_match = re.fullmatch(r"video\s+arc\s+(.+)", raw_text, re.IGNORECASE)
    if arc_match:
        arc_id = arc_match.group(1).strip().lower()
        if not _SAFE_ARC_ID_RE.fullmatch(arc_id):
            return _error_request(
                "Video script request needs a safe narrative arc ID.",
                source=source,
                channel_type=channel_type,
            )
        return _request(
            source_type="arc",
            source=source,
            channel_type=channel_type,
            query=f"arc:{arc_id}",
            arc_id=arc_id,
        )

    angle_match = re.fullmatch(r"video\s+angle\s+(.+)", raw_text, re.IGNORECASE)
    if angle_match:
        value = angle_match.group(1).strip()
        if not value.isdigit() or int(value) <= 0:
            return _error_request(
                "Video script request needs a positive angle number.",
                source=source,
                channel_type=channel_type,
            )
        angle_index = int(value)
        return _request(
            source_type="angle",
            source=source,
            channel_type=channel_type,
            query=f"angle:{angle_index}",
            angle_index=angle_index,
        )

    prefix = "video script:"
    if not lower.startswith(prefix):
        if lower in {"video", "video script", "video finding", "video arc", "video angle"}:
            return _error_request(
                "Video script request needs a specific topic, URL, finding ID, arc ID, or angle number.",
                source=source,
                channel_type=channel_type,
            )
        return None

    raw_query = raw_text[len(prefix):].strip()
    if _NEWSLETTER_CONTROL_RE.search(raw_query):
        return _error_request(
            "Video script mode cannot send, approve, select, or write newsletter stories.",
            source=source,
            channel_type=channel_type,
        )
    if _LIVE_POST_RE.search(raw_query):
        return _error_request(
            "Video script mode is manual publish only and cannot live-post to social platforms.",
            source=source,
            channel_type=channel_type,
        )

    query = redact_sensitive_text(raw_query).strip()
    if len(query) < MIN_QUERY_CHARS or query.lower() in _VAGUE_QUERIES:
        return _error_request(
            "Video script request needs a specific topic, URL, finding ID, arc ID, or angle number.",
            source=source,
            channel_type=channel_type,
        )

    source_url = _safe_url(query)
    if source_url:
        return _request(
            source_type="url",
            source=source,
            channel_type=channel_type,
            query=source_url,
            url=source_url,
        )

    return _request(
        source_type="topic",
        source=source,
        channel_type=channel_type,
        query=query,
    )


def generate_video_script_package(
    request: dict[str, Any] | str | None,
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | None = None,
    source_context: dict[str, Any] | None = None,
    duration_seconds: int = 45,
    write_artifact: bool = True,
) -> dict[str, Any]:
    """Generate a deterministic Slack-ready video script package.

    This is an offline package builder. It does not call providers, Slack,
    social APIs, the daily runner, or a video renderer.
    """
    parsed = parse_video_script_request(request) if isinstance(request, str) else request
    date = validate_run_date(date)
    if not parsed:
        return _video_result(
            status="failed",
            date=date,
            user=user,
            request={},
            package=None,
            claim_evidence=[],
            recommendation="No video script request was provided.",
            reports_root=reports_root,
            write_artifact=False,
            error="No video script request was provided.",
        )
    if parsed.get("error"):
        return _video_result(
            status="failed",
            date=date,
            user=user,
            request=parsed,
            package=None,
            claim_evidence=[],
            recommendation=parsed["error"],
            reports_root=reports_root,
            write_artifact=False,
            error=parsed["error"],
        )

    context = _normalize_video_context(parsed, source_context or {})
    source_urls = context["source_urls"]
    status = "ready" if source_urls else "degraded"
    risk_labels = ["source-backed"] if source_urls else ["weak evidence", "follow-up recommended"]
    recommendation = (
        "Ready for Slack review. Keep manual publish approval before using on social."
        if source_urls
        else "Run follow-up research or attach a source URL before publishing this video script."
    )

    package = VideoScriptPackage(
        package_id=f"video_{_hash_text(context['title'])[-8:]}",
        date=date,
        source_type=parsed.get("source_type", "topic"),
        source_ref=_source_ref(parsed),
        duration_seconds=duration_seconds,
        hook=f"{context['title']}: the source check most people skip.",
        spoken_script=_spoken_script(context, has_evidence=bool(source_urls)),
        shot_list=_shot_list(context, has_evidence=bool(source_urls)),
        captions=_captions(context, has_evidence=bool(source_urls)),
        source_urls=source_urls,
        labels=["AI-assisted script", "manual publish only"],
        risk_labels=risk_labels,
        status=status,
    ).to_public_dict()

    claim_evidence = _claim_evidence(context, parsed) if source_urls else []
    return _video_result(
        status=status,
        date=date,
        user=user,
        request=parsed,
        package=package,
        claim_evidence=claim_evidence,
        recommendation=recommendation,
        artifact_slug=context["title"],
        reports_root=reports_root,
        write_artifact=write_artifact,
    )


def video_script_artifact_paths(
    *,
    date: str,
    user: str = "ramsay",
    slug: str,
    reports_root: Path | None = None,
) -> dict[str, Path]:
    """Return ignored reports paths for a video script JSON/Markdown pair."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError("slug must not contain path separators")
    date = validate_run_date(date)
    root = (reports_root or DEFAULT_REPORTS_ROOT).resolve()
    base = (root / user / "video-scripts").resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise ValueError("video script artifact path escapes reports root") from exc
    safe_slug = normalize_artifact_slug(slug)
    stem = f"{date}-{safe_slug}"
    return {
        "json": base / f"{stem}.json",
        "markdown": base / f"{stem}.md",
    }


def _request(
    *,
    source_type: str,
    source: str,
    channel_type: str | None,
    query: str,
    finding_id: int | None = None,
    arc_id: str = "",
    angle_index: int | None = None,
    url: str = "",
) -> dict[str, Any]:
    preview = _short_text(query, PREVIEW_CHARS)
    return {
        "command": "video_script",
        "source": source,
        "channel_type": channel_type,
        "source_type": source_type,
        "query": redact_sensitive_text(query),
        "query_preview": redact_sensitive_text(preview),
        "request_hash": _hash_text(f"{source_type}:{query}"),
        "finding_id": finding_id,
        "arc_id": arc_id,
        "angle_index": angle_index,
        "url": _safe_url(url),
        "error": None,
    }


def _error_request(
    error: str,
    *,
    source: str,
    channel_type: str | None,
) -> dict[str, Any]:
    return {
        "command": "video_script",
        "source": source,
        "channel_type": channel_type,
        "source_type": "",
        "query": "",
        "query_preview": "",
        "request_hash": "",
        "finding_id": None,
        "arc_id": "",
        "angle_index": None,
        "url": "",
        "error": error,
    }


def _video_result(
    *,
    status: str,
    date: str,
    user: str,
    request: dict[str, Any],
    package: dict[str, Any] | None,
    claim_evidence: list[dict[str, str]],
    recommendation: str,
    reports_root: Path | None,
    write_artifact: bool,
    artifact_slug: str = "video-script",
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "date": validate_run_date(date),
        "user": user,
        "request": _public_request(request),
        "package": package,
        "claim_evidence": claim_evidence,
        "recommendation": redact_sensitive_text(recommendation),
        "artifacts": {"json": "", "markdown": ""},
        "error": error,
    }
    if write_artifact and package:
        paths = video_script_artifact_paths(
            date=date,
            user=user,
            slug=artifact_slug,
            reports_root=reports_root,
        )
        paths["json"].parent.mkdir(parents=True, exist_ok=True)
        payload["artifacts"] = {key: str(path) for key, path in paths.items()}
        paths["json"].write_text(json.dumps(payload, indent=2, sort_keys=True))
        paths["markdown"].write_text(_video_markdown(payload))
    return payload


def _public_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": request.get("command", ""),
        "source": request.get("source", ""),
        "channel_type": request.get("channel_type"),
        "source_type": request.get("source_type", ""),
        "query_preview": redact_sensitive_text(request.get("query_preview", "")),
        "request_hash": request.get("request_hash", ""),
        "finding_id": request.get("finding_id"),
        "arc_id": request.get("arc_id", ""),
        "angle_index": request.get("angle_index"),
        "url": _safe_url(request.get("url", "")),
        "error": request.get("error"),
    }


def _normalize_video_context(
    request: dict[str, Any],
    source_context: dict[str, Any],
) -> dict[str, Any]:
    title = source_context.get("title") or request.get("query_preview") or "Video script"
    summary = source_context.get("summary") or "A source-backed short-form video script request."
    urls = []
    if request.get("url"):
        urls.append(request["url"])
    urls.extend(source_context.get("source_urls") or [])
    urls.extend(
        item.get("source_url", "")
        for item in source_context.get("evidence", []) or []
        if isinstance(item, dict)
    )
    return {
        "title": _short_text(redact_sensitive_text(title), 96),
        "summary": _short_text(redact_sensitive_text(summary), 220),
        "source_urls": _safe_urls(urls),
    }


def _source_ref(request: dict[str, Any]) -> str:
    source_type = request.get("source_type")
    if source_type == "finding":
        return f"finding:{request.get('finding_id')}"
    if source_type == "arc":
        return f"arc:{request.get('arc_id')}"
    if source_type == "angle":
        return f"angle:{request.get('angle_index')}"
    if source_type == "url":
        return request.get("url", "")
    return request.get("query_preview", "")


def _spoken_script(context: dict[str, Any], *, has_evidence: bool) -> str:
    if not has_evidence:
        return (
            f"Here is the angle to research further: {context['title']}. "
            "Before recording, attach source evidence so every claim can be checked."
        )
    return (
        f"{context['title']}. {context['summary']} "
        "The takeaway is simple: check the source evidence before turning the finding into a post."
    )


def _shot_list(context: dict[str, Any], *, has_evidence: bool) -> list[str]:
    if not has_evidence:
        return [
            "Open with the unresolved question.",
            "Show placeholder source slots.",
            "End with follow-up research request.",
        ]
    return [
        "Open on the headline or source title.",
        "Show the source mix that supports the claim.",
        "End on the builder takeaway and manual-publish label.",
    ]


def _captions(context: dict[str, Any], *, has_evidence: bool) -> list[str]:
    if not has_evidence:
        return [f"Needs follow-up research: {context['title']}"]
    return [
        f"{context['title']}",
        "Source evidence before the take.",
        "Manual publish only.",
    ]


def _claim_evidence(
    context: dict[str, Any],
    request: dict[str, Any],
) -> list[dict[str, str]]:
    source_url = context["source_urls"][0]
    source_ref = _source_ref(request)
    return [
        {
            "claim": context["title"],
            "source_url": source_url,
            "source_ref": source_ref,
        },
        {
            "claim": context["summary"],
            "source_url": source_url,
            "source_ref": source_ref,
        },
    ]


def _video_markdown(payload: dict[str, Any]) -> str:
    package = payload["package"]
    lines = [
        f"# Video Script Package - {payload['date']}",
        "",
        f"Status: {payload['status']}",
        f"Labels: {', '.join(package.get('labels') or [])}",
        f"Recommendation: {payload['recommendation']}",
        "",
        "## Hook",
        "",
        package.get("hook", ""),
        "",
        "## Spoken Script",
        "",
        package.get("spoken_script", ""),
        "",
        "## Shot List",
    ]
    for item in package.get("shot_list") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Captions"])
    for item in package.get("captions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Evidence"])
    if payload.get("claim_evidence"):
        for item in payload["claim_evidence"]:
            lines.append(f"- {item['claim']} ({item['source_url']})")
    else:
        lines.append("- No usable source evidence attached.")
    return "\n".join(lines).strip() + "\n"


def _safe_duration(seconds: int) -> int:
    return int(seconds) if int(seconds) in {30, 45, 60} else 45


def _safe_urls(values: list[str]) -> list[str]:
    urls = []
    seen = set()
    for value in values:
        url = _safe_url(value)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return redact_sensitive_text(url)


def _safe_label(value: Any) -> str:
    label = str(value or "").lower().strip()
    label = _SAFE_LABEL_RE.sub("_", label).strip("_")
    return label or "unknown"


def _short_text(text: str, limit: int) -> str:
    value = redact_sensitive_text(text).strip()
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]
