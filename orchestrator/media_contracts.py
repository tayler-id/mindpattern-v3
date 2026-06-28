"""Shared public artifact contracts for arcs, angles, audio, and video.

These helpers keep public-facing feature artifacts consistent and path-safe.
They intentionally avoid database, network, Slack, and provider dependencies so
focused tests can run without private state.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_SUFFIX_RE = re.compile(r"^\.[a-z0-9]+$")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}(?!\d)"
)
_SLACK_MENTION_RE = re.compile(r"<[@#][A-Z0-9][A-Z0-9._|-]*>")
_SLACK_TOKEN_RE = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+")
_OPENAI_TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]+")
_GITHUB_TOKEN_RE = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{10,}")
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"
)


def validate_run_date(value: str) -> str:
    """Validate an ISO date path segment and reject traversal-like values."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must be a real calendar date") from exc
    return value


def normalize_artifact_slug(value: str, *, max_length: int = 96) -> str:
    """Return a deterministic, filesystem-safe slug for display text."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        text = "artifact"
    return text[:max_length].strip("-") or "artifact"


def redact_sensitive_text(text: Any) -> str:
    """Redact contact data, Slack IDs, and common token shapes from text."""
    value = "" if text is None else str(text)
    value = _EMAIL_RE.sub("[redacted]", value)
    value = _SLACK_MENTION_RE.sub("[redacted]", value)
    value = _SLACK_TOKEN_RE.sub("[redacted]", value)
    value = _OPENAI_TOKEN_RE.sub("[redacted]", value)
    value = _GITHUB_TOKEN_RE.sub("[redacted]", value)
    value = _KEY_VALUE_SECRET_RE.sub("[redacted]", value)

    def _redact_phone(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if 10 <= len(digits) <= 15:
            return "[redacted]"
        return match.group(0)

    return _PHONE_RE.sub(_redact_phone, value)


def _public_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return redact_sensitive_text(url)


def safe_artifact_path(
    *,
    root: Path,
    user: str,
    date: str,
    slug: str,
    suffix: str,
) -> Path:
    """Build an artifact path and ensure it cannot escape ``root``."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    date = validate_run_date(date)
    if "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError("slug must not contain path separators")
    if not _SAFE_SUFFIX_RE.fullmatch(suffix or ""):
        raise ValueError("suffix must be a dot extension such as .json")

    base = root.resolve()
    path = (base / user / date / f"{normalize_artifact_slug(slug)}{suffix}").resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("artifact path escapes root") from exc
    return path


@dataclass(frozen=True)
class EvidenceReference:
    run_date: str
    agent: str
    title: str
    summary: str
    source_url: str = ""
    source_name: str = ""
    finding_id: int | None = None

    @classmethod
    def from_finding(cls, finding: dict[str, Any]) -> "EvidenceReference":
        raw_id = finding.get("id") or finding.get("finding_id")
        finding_id = int(raw_id) if raw_id not in (None, "") else None
        return cls(
            finding_id=finding_id,
            run_date=validate_run_date(str(finding.get("run_date", ""))),
            agent=redact_sensitive_text(finding.get("agent", "")),
            title=redact_sensitive_text(finding.get("title", "")),
            summary=redact_sensitive_text(finding.get("summary", "")),
            source_url=_public_url(finding.get("source_url") or finding.get("url")),
            source_name=redact_sensitive_text(finding.get("source_name", "")),
        )

    def to_public_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.finding_id is not None:
            data["finding_id"] = self.finding_id
        data.update(
            {
                "run_date": validate_run_date(self.run_date),
                "agent": redact_sensitive_text(self.agent),
                "title": redact_sensitive_text(self.title),
                "summary": redact_sensitive_text(self.summary),
                "source_url": _public_url(self.source_url),
                "source_name": redact_sensitive_text(self.source_name),
            }
        )
        return data


@dataclass(frozen=True)
class PublicArtifactMetadata:
    artifact_id: str
    date: str
    artifact_type: str
    title: str
    status: str
    evidence: list[EvidenceReference] = field(default_factory=list)
    source_count: int = 0
    ai_generated: bool = False
    public_url: str | None = None
    transcript_url: str | None = None
    duration_seconds: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": normalize_artifact_slug(self.artifact_id),
            "date": validate_run_date(self.date),
            "type": normalize_artifact_slug(self.artifact_type).replace("-", "_"),
            "title": redact_sensitive_text(self.title),
            "status": normalize_artifact_slug(self.status),
            "source_count": int(self.source_count),
            "ai_generated": bool(self.ai_generated),
            "evidence": [ref.to_public_dict() for ref in self.evidence],
        }
        if self.public_url:
            data["public_url"] = _public_url(self.public_url)
        if self.transcript_url:
            data["transcript_url"] = _public_url(self.transcript_url)
        if self.duration_seconds is not None:
            data["duration_seconds"] = int(self.duration_seconds)
        for key, value in self.extra.items():
            if isinstance(key, str) and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", key):
                data[key] = redact_sensitive_text(value) if isinstance(value, str) else value
        return data
