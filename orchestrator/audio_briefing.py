"""Audio briefing script builder.

This module converts a completed newsletter report into spoken prose,
transcript markdown, source notes, and deterministic TTS metadata. Binary media
artifact writing is a later task.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_SAFE_CONFIG_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_RAW_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_DEGRADED_RE = re.compile(r"^>\s*Degraded issue notice:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class TTSProviderConfig:
    """Explicit live TTS configuration passed to an injected adapter."""

    provider: str
    model: str
    voice: str
    enabled: bool = False


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


def build_tts_audio(
    script_result: dict[str, Any],
    *,
    dry_run: bool = True,
    env: Mapping[str, str] | None = None,
    tts_provider: Callable[[str, TTSProviderConfig], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build deterministic TTS metadata or call an injected live adapter.

    The default path is dry-run and never calls a provider. Live mode requires
    ``dry_run=False``, explicit environment configuration, and an injected
    adapter; missing pieces fail closed without network or provider imports.
    """
    config = tts_provider_config_from_env(env)
    mode = "dry_run" if dry_run else "provider"

    if script_result.get("status") == "failed" or not script_result.get("script"):
        return _failed_tts_result(
            script_result=script_result,
            mode=mode,
            config=config,
            error="Audio script is not usable for TTS.",
        )

    if dry_run:
        metadata = _build_tts_metadata(
            script_result=script_result,
            config=TTSProviderConfig(
                provider="dry_run",
                model="dry-run-tts-v1",
                voice="dry-run",
                enabled=False,
            ),
            mode="dry_run",
            audio_format="mp3",
            duration_seconds=_estimate_duration_seconds(script_result),
            audio_hash=_hash_text(
                "|".join([
                    "dry_run_audio_placeholder",
                    script_result.get("script_hash", ""),
                    script_result.get("date", ""),
                ])
            ),
            audio_placeholder=True,
        )
        return {
            "status": _status_from_script(script_result),
            "mode": "dry_run",
            "date": script_result.get("date", ""),
            "user": script_result.get("user", ""),
            "degraded": bool(script_result.get("degraded")),
            "audio_bytes": None,
            "transcript_markdown": script_result.get("transcript_markdown", ""),
            "metadata": metadata,
            "error": None,
        }

    if not config.enabled:
        return _failed_tts_result(
            script_result=script_result,
            mode="provider",
            config=config,
            error=(
                "Live TTS requires MP_AUDIO_TTS_ENABLED=true and "
                "MP_AUDIO_TTS_PROVIDER."
            ),
        )
    if tts_provider is None:
        return _failed_tts_result(
            script_result=script_result,
            mode="provider",
            config=config,
            error="Live TTS requires an injected provider adapter.",
        )

    try:
        provider_result = tts_provider(script_result["script"], config)
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        return _failed_tts_result(
            script_result=script_result,
            mode="provider",
            config=config,
            error=f"TTS provider adapter failed: {exc}",
        )

    audio_bytes = provider_result.get("audio_bytes")
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        return _failed_tts_result(
            script_result=script_result,
            mode="provider",
            config=config,
            error="TTS provider adapter returned no audio bytes.",
        )

    metadata = _build_tts_metadata(
        script_result=script_result,
        config=config,
        mode="provider",
        audio_format=_safe_config_value(provider_result.get("audio_format"), "mp3").lower(),
        duration_seconds=float(provider_result.get("duration_seconds") or 0),
        audio_hash=_hash_bytes(audio_bytes),
        audio_placeholder=False,
        provider_request_id=provider_result.get("provider_request_id"),
    )
    return {
        "status": _status_from_script(script_result),
        "mode": "provider",
        "date": script_result.get("date", ""),
        "user": script_result.get("user", ""),
        "degraded": bool(script_result.get("degraded")),
        "audio_bytes": audio_bytes,
        "transcript_markdown": script_result.get("transcript_markdown", ""),
        "metadata": metadata,
        "error": None,
    }


def audio_artifact_paths(
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | str | None = None,
) -> dict[str, Path]:
    """Return safe audio artifact paths under reports/<user>/audio/."""
    date = validate_run_date(date)
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")

    root = Path(reports_root) if reports_root is not None else DEFAULT_REPORTS_ROOT
    root = root.resolve()
    base = (root / user / "audio").resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise ValueError("audio artifact path escapes reports root") from exc

    return {
        "audio": base / f"{date}.mp3",
        "transcript": base / f"{date}.transcript.md",
        "metadata": base / f"{date}.json",
        "provenance": base / f"{date}.provenance.json",
    }


def write_audio_artifacts(
    tts_result: dict[str, Any],
    *,
    reports_root: Path | str | None = None,
    traces_conn: Any = None,
    pipeline_run_id: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write audio artifacts and optionally log a compact trace event."""
    date = validate_run_date(str(tts_result.get("date", "")))
    user = str(tts_result.get("user") or "ramsay")
    if not _SAFE_USER_RE.fullmatch(user):
        raise ValueError("user must be a safe path segment")

    status = _safe_status(tts_result.get("status"))
    paths = audio_artifact_paths(date=date, user=user, reports_root=reports_root)
    paths["metadata"].parent.mkdir(parents=True, exist_ok=True)

    audio_bytes = tts_result.get("audio_bytes")
    has_audio_file = isinstance(audio_bytes, bytes) and bool(audio_bytes)
    if has_audio_file:
        paths["audio"].write_bytes(audio_bytes)

    transcript = str(tts_result.get("transcript_markdown") or "").strip()
    if not transcript:
        transcript = _fallback_transcript(date=date, status=status)
    paths["transcript"].write_text(transcript.rstrip() + "\n")

    metadata = dict(tts_result.get("metadata") or {})
    metadata.update({
        "status": status,
        "date": date,
        "user": user,
        "generated_at": _generated_at(generated_at),
        "has_audio_file": has_audio_file,
        "artifact_files": {
            "audio": paths["audio"].name if has_audio_file else "",
            "transcript": paths["transcript"].name,
            "metadata": paths["metadata"].name,
            "provenance": paths["provenance"].name,
        },
    })
    paths["metadata"].write_text(_json_dumps(metadata))

    provenance = _build_audio_provenance(metadata)
    paths["provenance"].write_text(_json_dumps(provenance))

    trace_payload = _audio_trace_payload(metadata)
    trace_logged = _log_audio_trace(
        traces_conn=traces_conn,
        pipeline_run_id=pipeline_run_id,
        payload=trace_payload,
    )
    return {
        "status": status,
        "date": date,
        "user": user,
        "paths": paths,
        "metadata": metadata,
        "provenance": provenance,
        "trace_logged": trace_logged,
    }


def tts_provider_config_from_env(env: Mapping[str, str] | None = None) -> TTSProviderConfig:
    """Read explicit TTS configuration without importing or calling providers."""
    values = os.environ if env is None else env
    enabled = _env_truthy(values.get("MP_AUDIO_TTS_ENABLED"))
    provider = _safe_config_value(values.get("MP_AUDIO_TTS_PROVIDER"), "")
    if not enabled or not provider:
        return TTSProviderConfig(
            provider="dry_run",
            model="dry-run-tts-v1",
            voice="dry-run",
            enabled=False,
        )
    return TTSProviderConfig(
        provider=provider.lower(),
        model=_safe_config_value(values.get("MP_AUDIO_TTS_MODEL"), "gpt-4o-mini-tts"),
        voice=_safe_config_value(values.get("MP_AUDIO_TTS_VOICE"), "alloy"),
        enabled=True,
    )


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


def _failed_tts_result(
    *,
    script_result: dict[str, Any],
    mode: str,
    config: TTSProviderConfig,
    error: str,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "mode": mode,
        "date": script_result.get("date", ""),
        "user": script_result.get("user", ""),
        "degraded": True,
        "audio_bytes": None,
        "transcript_markdown": script_result.get("transcript_markdown", ""),
        "metadata": _build_tts_metadata(
            script_result=script_result,
            config=config,
            mode=mode,
            audio_format="mp3",
            duration_seconds=0,
            audio_hash="",
            audio_placeholder=True,
        ),
        "error": redact_sensitive_text(error),
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


def _build_tts_metadata(
    *,
    script_result: dict[str, Any],
    config: TTSProviderConfig,
    mode: str,
    audio_format: str,
    duration_seconds: float,
    audio_hash: str,
    audio_placeholder: bool,
    provider_request_id: Any = None,
) -> dict[str, Any]:
    metadata = {
        "id": f"{script_result.get('date', '')}-audio-morning-briefing",
        "type": "audio_briefing",
        "date": script_result.get("date", ""),
        "user": script_result.get("user", ""),
        "status": _status_from_script(script_result),
        "mode": mode,
        "provider": config.provider,
        "model": config.model,
        "voice": config.voice,
        "audio_format": audio_format,
        "duration_seconds": duration_seconds,
        "audio_placeholder": audio_placeholder,
        "audio_hash": audio_hash,
        "script_hash": script_result.get("script_hash", ""),
        "source_report_hash": script_result.get("source_report_hash", ""),
        "show_notes": _safe_source_notes(script_result.get("show_notes") or []),
        "word_count": int(script_result.get("word_count") or 0),
        "source_count": int(script_result.get("source_count") or 0),
        "degraded": bool(script_result.get("degraded")),
        "degraded_reason": redact_sensitive_text(script_result.get("degraded_reason") or ""),
        "labels": _audio_labels(script_result),
    }
    if provider_request_id:
        metadata["provider_request_id"] = redact_sensitive_text(str(provider_request_id))
    return metadata


def _audio_labels(script_result: dict[str, Any]) -> list[str]:
    labels = ["AI-generated audio", "manual publish only"]
    if script_result.get("degraded"):
        labels.append("Degraded audio briefing")
    return labels


def _status_from_script(script_result: dict[str, Any]) -> str:
    if script_result.get("status") == "failed":
        return "failed"
    return "degraded" if script_result.get("degraded") else "ready"


def _safe_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in {"ready", "degraded", "failed"} else "failed"


def _safe_source_notes(notes: list[dict[str, Any]]) -> list[dict[str, str]]:
    safe = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        url = _clean_url(note.get("url"))
        if not url:
            continue
        safe.append({
            "label": redact_sensitive_text(note.get("label") or "Source"),
            "url": url,
        })
    return safe


def _fallback_transcript(*, date: str, status: str) -> str:
    return (
        f"# MindPattern Audio Briefing - {date}\n\n"
        f"Status: {status}\n\n"
        "No audio transcript is available for this run.\n"
    )


def _generated_at(value: str | None) -> str:
    if value:
        return redact_sensitive_text(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_audio_provenance(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": metadata.get("id", ""),
        "type": "audio_briefing",
        "date": metadata.get("date", ""),
        "status": metadata.get("status", ""),
        "generated_at": metadata.get("generated_at", ""),
        "source_report_hash": metadata.get("source_report_hash", ""),
        "script_hash": metadata.get("script_hash", ""),
        "audio_hash": metadata.get("audio_hash", ""),
        "source_count": int(metadata.get("source_count") or 0),
        "labels": list(metadata.get("labels") or []),
        "source_notes": _safe_source_notes(metadata.get("show_notes") or []),
        "tts": {
            "provider": metadata.get("provider", ""),
            "model": metadata.get("model", ""),
            "voice": metadata.get("voice", ""),
            "mode": metadata.get("mode", ""),
            "audio_format": metadata.get("audio_format", ""),
            "audio_placeholder": bool(metadata.get("audio_placeholder")),
        },
    }


def _audio_trace_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_artifact": "audio_briefing",
        "status": metadata.get("status", ""),
        "date": metadata.get("date", ""),
        "user": metadata.get("user", ""),
        "mode": metadata.get("mode", ""),
        "provider": metadata.get("provider", ""),
        "model": metadata.get("model", ""),
        "voice": metadata.get("voice", ""),
        "script_hash": metadata.get("script_hash", ""),
        "source_report_hash": metadata.get("source_report_hash", ""),
        "audio_hash": metadata.get("audio_hash", ""),
        "source_count": int(metadata.get("source_count") or 0),
        "has_audio_file": bool(metadata.get("has_audio_file")),
    }


def _log_audio_trace(
    *,
    traces_conn: Any,
    pipeline_run_id: str | None,
    payload: dict[str, Any],
) -> bool:
    if traces_conn is None:
        return False
    from orchestrator.traces_db import log_event

    log_event(
        traces_conn,
        pipeline_run_id or f"audio-{payload.get('date', 'unknown')}",
        "audio_briefing_artifact",
        _json_dumps(payload),
    )
    return True


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _estimate_duration_seconds(script_result: dict[str, Any]) -> float:
    word_count = int(script_result.get("word_count") or 0)
    if word_count <= 0:
        return 0
    return round(max(1.0, word_count / 150 * 60), 2)


def _env_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_config_value(value: Any, default: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return default
    return candidate if _SAFE_CONFIG_RE.fullmatch(candidate) else default


def _clean_url(url: Any) -> str:
    value = str(url or "").strip()
    if not value.startswith(("http://", "https://")):
        return ""
    return redact_sensitive_text(value)


def _hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]
