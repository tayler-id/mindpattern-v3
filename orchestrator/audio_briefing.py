"""Audio briefing script builder.

This module only converts a completed newsletter report into spoken prose,
transcript markdown, and source notes. Provider adapters and binary media
artifacts are later tasks.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_RAW_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_DEGRADED_RE = re.compile(r"^>\s*Degraded issue notice:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def build_audio_script(
    report_path: Path | str,
    *,
    date: str,
    user: str = "ramsay",
    max_words: int = 700,
) -> dict[str, Any]:
    """Build a deterministic spoken script and transcript from a report."""
    date = validate_run_date(date)
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")

    path = Path(report_path)
    if not path.exists():
        return _failed_result(date=date, user=user, error=f"Report missing: {path}")

    markdown_text = path.read_text(errors="replace")
    if not markdown_text.strip():
        return _failed_result(date=date, user=user, error=f"Report is empty: {path}")

    degraded_reason = _degraded_reason(markdown_text)
    show_notes = _extract_show_notes(markdown_text)
    spoken = _markdown_to_spoken(markdown_text, max_words=max_words)
    if degraded_reason:
        spoken = (
            "This audio briefing is marked degraded. "
            f"Reason: {redact_sensitive_text(degraded_reason)}. "
            + spoken
        ).strip()

    status = "degraded" if degraded_reason else "ready"
    labels = ["AI-generated audio briefing", "manual publish only"]
    if degraded_reason:
        labels.append("Degraded audio briefing")

    result = {
        "status": status,
        "date": date,
        "user": user,
        "degraded": bool(degraded_reason),
        "degraded_reason": redact_sensitive_text(degraded_reason),
        "script": spoken,
        "word_count": len(spoken.split()),
        "show_notes": show_notes,
        "source_count": len(show_notes),
        "labels": labels,
        "source_report_path": str(path),
        "source_report_hash": _hash_text(markdown_text),
        "script_hash": _hash_text(spoken),
        "transcript_markdown": _format_transcript(
            date=date,
            status=status,
            script=spoken,
            show_notes=show_notes,
            labels=labels,
        ),
        "error": None,
    }
    return result


def _failed_result(*, date: str, user: str, error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "date": date,
        "user": user,
        "degraded": True,
        "degraded_reason": "",
        "script": "",
        "word_count": 0,
        "show_notes": [],
        "source_count": 0,
        "labels": ["AI-generated audio briefing", "manual publish only"],
        "source_report_path": "",
        "source_report_hash": "",
        "script_hash": "",
        "transcript_markdown": "",
        "error": error,
    }


def _degraded_reason(markdown_text: str) -> str:
    match = _DEGRADED_RE.search(markdown_text)
    return redact_sensitive_text(match.group(1).strip()) if match else ""


def _extract_show_notes(markdown_text: str) -> list[dict[str, str]]:
    notes = []
    seen = set()
    for label, url in _MARKDOWN_LINK_RE.findall(markdown_text):
        clean_url = _clean_url(url)
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        notes.append({
            "label": redact_sensitive_text(_strip_inline_markdown(label)).strip() or "Source",
            "url": clean_url,
        })
    return notes


def _markdown_to_spoken(markdown_text: str, *, max_words: int) -> str:
    text = _FENCED_BLOCK_RE.sub("", markdown_text)
    text = _remove_table_lines(text)
    text = _MARKDOWN_LINK_RE.sub(lambda m: _strip_inline_markdown(m.group(1)), text)
    text = _RAW_URL_RE.sub("", text)

    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(">"):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        line = re.sub(r"^\s*\d+\.\s+", "", line)
        line = _strip_inline_markdown(line)
        if line:
            lines.append(line)

    spoken = " ".join(lines)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    words = spoken.split()
    if len(words) > max_words:
        spoken = " ".join(words[:max_words]).rstrip(" ,;:") + "."
    return redact_sensitive_text(spoken)


def _remove_table_lines(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped and re.search(r"\|.*\|", stripped):
            continue
        if re.fullmatch(r"[:\-\s|]+", stripped):
            continue
        kept.append(line)
    return "\n".join(kept)


def _strip_inline_markdown(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"\*([^*]+)\*", r"\1", value)
    value = re.sub(r"_([^_]+)_", r"\1", value)
    return redact_sensitive_text(value)


def _format_transcript(
    *,
    date: str,
    status: str,
    script: str,
    show_notes: list[dict[str, str]],
    labels: list[str],
) -> str:
    lines = [
        f"# MindPattern Audio Briefing - {date}",
        "",
        f"Status: {status}",
        f"Labels: {', '.join(labels)}",
        "",
        "## Spoken Script",
        "",
        script,
        "",
        "## Source notes",
    ]
    if show_notes:
        for note in show_notes:
            lines.append(f"- [{note['label']}]({note['url']})")
    else:
        lines.append("- No source links found in source report.")
    return "\n".join(lines).strip() + "\n"


def _clean_url(url: Any) -> str:
    value = str(url or "").strip()
    if not value.startswith(("http://", "https://")):
        return ""
    return redact_sensitive_text(value)


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]
