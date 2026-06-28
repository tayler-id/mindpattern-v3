"""Social Angle Lab contracts and command parsing.

Feature 18 starts with pure request/angle contracts. Generation, Slack wiring,
and social draft handoff are later tasks; this module must not call providers,
Slack, the daily runner, or social posting code.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"

MIN_QUERY_CHARS = 8
PREVIEW_CHARS = 160

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_ARC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_SAFE_LABEL_RE = re.compile(r"[^a-z0-9_-]+")
_VAGUE_QUERIES = {"more", "this", "that", "it", "details", "ideas"}
_NEWSLETTER_CONTROL_RE = re.compile(
    r"\b(send|publish|approve|select|pick|write|block)\s+"
    r"(the\s+)?(newsletter|issue|story|stories)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SocialAngleCandidate:
    """Stable public contract for an angle candidate before social drafting."""

    angle_id: str
    angle_type: str
    platform: str
    hook: str
    thesis: str
    source_urls: list[str]
    confidence: float
    risk_note: str
    verdict: str = "keep"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "angle_id": _safe_label(self.angle_id),
            "angle_type": _safe_label(self.angle_type),
            "platform": _safe_label(self.platform),
            "hook": redact_sensitive_text(self.hook),
            "thesis": redact_sensitive_text(self.thesis),
            "source_urls": _safe_urls(self.source_urls),
            "confidence": _clamp_confidence(self.confidence),
            "risk_note": redact_sensitive_text(self.risk_note),
            "verdict": _safe_label(self.verdict),
        }


def parse_social_angle_request(
    text: str | None,
    *,
    source: str = "slack",
    channel_type: str | None = None,
) -> dict[str, Any] | None:
    """Parse a Slack Social Angle Lab command into a stable request dict.

    Returns ``None`` when the text is not an angle command. Recognized but
    invalid commands return a request with ``error`` populated so callers can
    reply without falling through to approval or posting logic.
    """
    raw_text = (text or "").strip()
    lower = raw_text.lower()
    if not raw_text:
        return None

    finding_match = re.fullmatch(r"angles\s+finding\s+(.+)", raw_text, re.IGNORECASE)
    if finding_match:
        value = finding_match.group(1).strip()
        if not value.isdigit() or int(value) <= 0:
            return _error_request(
                "Angle request needs a numeric finding ID.",
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

    arc_match = re.fullmatch(r"angles\s+arc\s+(.+)", raw_text, re.IGNORECASE)
    if arc_match:
        arc_id = arc_match.group(1).strip().lower()
        if not _SAFE_ARC_ID_RE.fullmatch(arc_id):
            return _error_request(
                "Angle request needs a safe narrative arc ID.",
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

    matched_prefix = None
    for prefix in ("angles:", "angle lab:"):
        if lower.startswith(prefix):
            matched_prefix = prefix
            break

    if matched_prefix is None:
        if lower in {"angles", "angle lab"}:
            return _error_request(
                "Angle request needs a more specific topic, URL, finding ID, or arc ID.",
                source=source,
                channel_type=channel_type,
            )
        return None

    raw_query = raw_text[len(matched_prefix):].strip()
    if _NEWSLETTER_CONTROL_RE.search(raw_query):
        return _error_request(
            "Social Angle Lab cannot send, approve, select, or write newsletter stories.",
            source=source,
            channel_type=channel_type,
        )

    query = redact_sensitive_text(raw_query).strip()
    if len(query) < MIN_QUERY_CHARS or query.lower() in _VAGUE_QUERIES:
        return _error_request(
            "Angle request needs a more specific topic, URL, finding ID, or arc ID.",
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


def social_angles_artifact_path(
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | None = None,
) -> Path:
    """Return the ignored reports path for a day's social-angle artifact."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    date = validate_run_date(date)
    root = (reports_root or DEFAULT_REPORTS_ROOT).resolve()
    path = (root / user / "social-angles" / f"{date}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("social angle artifact path escapes reports root") from exc
    return path


def _request(
    *,
    source_type: str,
    source: str,
    channel_type: str | None,
    query: str,
    finding_id: int | None = None,
    arc_id: str = "",
    url: str = "",
) -> dict[str, Any]:
    query_preview = _safe_preview(query)
    return {
        "command": "social_angle_lab",
        "source": source,
        "channel_type": channel_type,
        "source_type": source_type,
        "query": query,
        "query_preview": query_preview,
        "request_hash": _hash_text(f"{source_type}:{query}"),
        "finding_id": finding_id,
        "arc_id": arc_id,
        "url": url,
        "error": None,
    }


def _error_request(
    error: str,
    *,
    source: str,
    channel_type: str | None,
) -> dict[str, Any]:
    return {
        "command": "social_angle_lab",
        "source": source,
        "channel_type": channel_type,
        "source_type": "",
        "query": "",
        "query_preview": "",
        "request_hash": "",
        "finding_id": None,
        "arc_id": "",
        "url": "",
        "error": error,
    }


def _hash_text(text: str) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"sha256:{digest}"


def _safe_preview(text: str) -> str:
    preview = redact_sensitive_text(text).replace("\n", " ").strip()
    preview = re.sub(r"\s+", " ", preview)
    if len(preview) > PREVIEW_CHARS:
        preview = preview[: PREVIEW_CHARS - 1].rstrip() + "..."
    return preview


def _safe_url(value: Any) -> str:
    url = redact_sensitive_text(value).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _safe_urls(values: list[str]) -> list[str]:
    safe = []
    for value in values:
        url = _safe_url(value)
        if url and url not in safe:
            safe.append(url)
    return safe


def _safe_label(value: Any) -> str:
    label = str(value or "").strip().lower().replace(" ", "_")
    label = _SAFE_LABEL_RE.sub("_", label).strip("_-")
    return label or "unknown"


def _clamp_confidence(value: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return round(max(0.0, min(1.0, confidence)), 3)
