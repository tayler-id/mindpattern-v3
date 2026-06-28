"""Short-form video script contracts and command parsing.

Feature 21 starts with strict Slack command parsing and stable public package
objects. Generation, Slack wiring, file upload, and any MP4 provider adapter
are later tasks.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date

MIN_QUERY_CHARS = 8
PREVIEW_CHARS = 160

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
