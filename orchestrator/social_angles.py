"""Social Angle Lab contracts and command parsing.

Feature 18 starts with pure request/angle contracts. Generation, Slack wiring,
and social draft handoff are later tasks; this module must not call providers,
Slack, the daily runner, or social posting code.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
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
_PRODUCT_PITCH_RE = re.compile(
    r"powered by mindpattern|built with mindpattern|mindpattern found|"
    r"mindpattern's agents|try mindpattern|built with my autonomous pipeline",
    re.IGNORECASE,
)
_INFRA_FLEX_RE = re.compile(
    r"\bagent counts?\b|\bcron\b|\bpipeline flex|\bmy pipeline\b|"
    r"\bautomated[- ]infrastructure\b",
    re.IGNORECASE,
)
_GENERIC_AI_RE = re.compile(
    r"\bai is changing everything\b|\bfuture of (work|software|ai)\b|"
    r"\bevery team needs\b",
    re.IGNORECASE,
)
_WHY_NOW_RE = re.compile(
    r"\b(today|now|this week|shipped|launched|released|caught|changed|changes|"
    r"restores|restored|breaks|broke|matters)\b",
    re.IGNORECASE,
)

CRITIC_DIMENSIONS = (
    "focus",
    "why_now",
    "audience_value",
    "evidence_strength",
    "freshness",
    "tension",
    "specificity",
    "platform_fit",
    "tayler_fit",
    "risk_calibration",
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


def generate_social_angles(
    request: dict[str, Any] | str | None,
    *,
    date: str,
    user: str = "ramsay",
    reports_root: Path | None = None,
    dry_run: bool = True,
    source_context: dict[str, Any] | None = None,
    recent_angles: list[dict[str, Any]] | None = None,
    angle_provider: Callable[..., list[dict[str, Any]]] | None = None,
    write_artifact: bool = True,
) -> dict[str, Any]:
    """Generate, critique, rank, and optionally persist social angles.

    ``angle_provider`` is the live/provider boundary. Missing provider config
    fails closed to deterministic dry-run behavior instead of calling Claude,
    Slack, network, social APIs, or posting code.
    """
    parsed = parse_social_angle_request(request) if isinstance(request, str) else request
    date = validate_run_date(date)
    if not parsed:
        return _angle_result(
            status="failed",
            mode="dry_run",
            date=date,
            user=user,
            request={},
            angles=[],
            error="No social angle request was provided.",
            reports_root=reports_root,
            write_artifact=write_artifact,
        )
    if parsed.get("error"):
        return _angle_result(
            status="failed",
            mode="dry_run",
            date=date,
            user=user,
            request=parsed,
            angles=[],
            error=parsed["error"],
            reports_root=reports_root,
            write_artifact=write_artifact,
        )

    context = _normalize_source_context(parsed, source_context or {})
    mode = "provider" if not dry_run and angle_provider else "dry_run"
    raw_candidates = (
        angle_provider(parsed, context)
        if mode == "provider"
        else _deterministic_angle_candidates(parsed, context)
    )
    candidates = [_coerce_candidate(item) for item in raw_candidates]

    reviewed = []
    for candidate in candidates:
        public = candidate.to_public_dict()
        critique = critique_social_angle(candidate, recent_angles=recent_angles)
        public.update(critique)
        reviewed.append(public)

    reviewed.sort(key=lambda item: (-float(item["score"]), item["angle_id"]))
    return _angle_result(
        status="completed",
        mode=mode,
        date=date,
        user=user,
        request=parsed,
        angles=reviewed,
        reports_root=reports_root,
        write_artifact=write_artifact,
    )


def critique_social_angle(
    candidate: SocialAngleCandidate,
    *,
    recent_angles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assignment-editor style critic for a single social angle."""
    text = " ".join([candidate.hook, candidate.thesis, candidate.risk_note])
    source_urls = _safe_urls(candidate.source_urls)
    kill_switches = []

    if not source_urls:
        kill_switches.append("no_source_backed_evidence")
    if _PRODUCT_PITCH_RE.search(text) or _INFRA_FLEX_RE.search(text):
        kill_switches.append("product_pitch_framing")
    if _GENERIC_AI_RE.search(text):
        kill_switches.append("generic_ai_framing")
    if _recent_angle_match(candidate, recent_angles or []):
        kill_switches.append("same_as_recent_angle")

    scores = {
        "focus": _score_focus(candidate),
        "why_now": 8 if _WHY_NOW_RE.search(text) else 5,
        "audience_value": _score_contains_any(text, ["builder", "operator", "workflow", "team", "source"], 8, 5),
        "evidence_strength": 9 if source_urls else 2,
        "freshness": 7 if not _recent_angle_match(candidate, recent_angles or []) else 2,
        "tension": _score_contains_any(text, ["not ", "but", "instead", "tradeoff", "risk", "brittle"], 8, 5),
        "specificity": _score_specificity(text),
        "platform_fit": _score_platform_fit(candidate),
        "tayler_fit": _score_tayler_fit(text),
        "risk_calibration": 8 if candidate.risk_note else 5,
    }

    score = round(sum(scores.values()) / len(scores), 2)
    if kill_switches:
        verdict = "reject"
    elif score >= 7.5:
        verdict = "keep"
    elif score >= 6.0:
        verdict = "revise"
    else:
        verdict = "reject"

    reason = _critique_reason(verdict, kill_switches)
    revision_note = ""
    if verdict == "revise":
        revision_note = "Tighten the why-now and name the source-backed tension before drafting."
    elif verdict == "reject":
        revision_note = "Do not draft this angle unless the kill switches are removed and evidence is added."

    return {
        "verdict": verdict,
        "score": score,
        "scores": scores,
        "reason": reason,
        "revision_note": revision_note,
        "kill_switches": kill_switches,
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


def _angle_result(
    *,
    status: str,
    mode: str,
    date: str,
    user: str,
    request: dict[str, Any],
    angles: list[dict[str, Any]],
    reports_root: Path | None,
    write_artifact: bool,
    error: str | None = None,
) -> dict[str, Any]:
    shown_angles = [angle for angle in angles if angle.get("verdict") in {"keep", "revise"}]
    payload = {
        "status": status,
        "mode": mode,
        "date": validate_run_date(date),
        "user": user,
        "request": _public_request(request),
        "angles": angles,
        "shown_angles": shown_angles,
        "summary": {
            "generated_count": len(angles),
            "shown_count": len(shown_angles),
            "rejected_count": sum(1 for angle in angles if angle.get("verdict") == "reject"),
        },
        "error": error,
        "artifact": None,
    }
    if write_artifact:
        path = social_angles_artifact_path(date=date, user=user, reports_root=reports_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["artifact"] = str(path)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
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
        "url": _safe_url(request.get("url", "")),
        "error": request.get("error"),
    }


def _normalize_source_context(
    request: dict[str, Any],
    source_context: dict[str, Any],
) -> dict[str, Any]:
    title = source_context.get("title") or request.get("query_preview") or "Social angle"
    summary = source_context.get("summary") or (
        "Source-backed angle request from Slack Social Angle Lab."
    )
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
        "title": redact_sensitive_text(title),
        "summary": redact_sensitive_text(summary),
        "source_urls": _safe_urls(urls),
    }


def _deterministic_angle_candidates(
    request: dict[str, Any],
    context: dict[str, Any],
) -> list[SocialAngleCandidate]:
    title = _short_text(context.get("title") or request.get("query_preview"), 80)
    summary = _short_text(context.get("summary"), 140)
    source_urls = context.get("source_urls") or []
    needs_source = "Needs source before drafting." if not source_urls else "Source-backed; verify wording before drafting."
    return [
        SocialAngleCandidate(
            angle_id="angle_1",
            angle_type="builder_lesson",
            platform="linkedin",
            hook=f"What {title} changes in my own research workflow.",
            thesis=f"{summary} The useful lesson is to check source reliability before turning a finding into a post.",
            source_urls=source_urls,
            confidence=0.82,
            risk_note=needs_source,
        ),
        SocialAngleCandidate(
            angle_id="angle_2",
            angle_type="contrarian_take",
            platform="bluesky",
            hook=f"The interesting part of {title} is reliability, not reach.",
            thesis="More sources are not automatically better. The angle is whether the source mix makes the conclusion less brittle.",
            source_urls=source_urls,
            confidence=0.78,
            risk_note=needs_source,
        ),
        SocialAngleCandidate(
            angle_id="angle_3",
            angle_type="tactical_tip",
            platform="linkedin",
            hook=f"Before drafting from {title}, inspect the source mix.",
            thesis="The practical move is to name what changed, which source proves it, and what a builder should do differently now.",
            source_urls=source_urls,
            confidence=0.8,
            risk_note=needs_source,
        ),
        SocialAngleCandidate(
            angle_id="angle_4",
            angle_type="market_take",
            platform="linkedin",
            hook=f"{title} points to a workflow shift, not just another tool update.",
            thesis="The market signal is that source reliability is becoming part of the product experience.",
            source_urls=source_urls,
            confidence=0.72,
            risk_note=needs_source,
        ),
        SocialAngleCandidate(
            angle_id="angle_5",
            angle_type="short_video_hook",
            platform="video",
            hook=f"One thing {title} changes today: trust the source mix before the take.",
            thesis="Open with the surprising source detail, show the workflow consequence, then end with the manual-publish social angle.",
            source_urls=source_urls,
            confidence=0.74,
            risk_note=needs_source,
        ),
        SocialAngleCandidate(
            angle_id="angle_6",
            angle_type="generic_product_pitch",
            platform="linkedin",
            hook="Powered by MindPattern, AI is changing everything.",
            thesis="Every team needs this now because automation is the future.",
            source_urls=[],
            confidence=0.2,
            risk_note="Rejected audit candidate: product pitch and no source evidence.",
        ),
    ]


def _coerce_candidate(item: dict[str, Any] | SocialAngleCandidate) -> SocialAngleCandidate:
    if isinstance(item, SocialAngleCandidate):
        return item
    return SocialAngleCandidate(
        angle_id=str(item.get("angle_id", "")),
        angle_type=str(item.get("angle_type", "")),
        platform=str(item.get("platform", "")),
        hook=str(item.get("hook", "")),
        thesis=str(item.get("thesis", "")),
        source_urls=list(item.get("source_urls") or []),
        confidence=float(item.get("confidence", 0.0) or 0.0),
        risk_note=str(item.get("risk_note", "")),
        verdict=str(item.get("verdict", "keep")),
    )


def _recent_angle_match(
    candidate: SocialAngleCandidate,
    recent_angles: list[dict[str, Any]],
) -> bool:
    current = _token_set(f"{candidate.hook} {candidate.thesis}")
    if not current:
        return False
    for recent in recent_angles:
        other = _token_set(f"{recent.get('hook', '')} {recent.get('thesis', '')}")
        if not other:
            continue
        overlap = len(current & other) / max(1, len(current | other))
        if overlap >= 0.72:
            return True
    return False


def _score_focus(candidate: SocialAngleCandidate) -> int:
    text = f"{candidate.hook} {candidate.thesis}"
    if len(re.split(r"\band\b|;|,", text, maxsplit=3)) > 3:
        return 6
    return 8


def _score_contains_any(text: str, needles: list[str], hit: int, miss: int) -> int:
    lower = text.lower()
    return hit if any(needle in lower for needle in needles) else miss


def _score_specificity(text: str) -> int:
    if _safe_urls([text]):
        return 8
    named = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", text)
    if named:
        return 8
    if any(term in text.lower() for term in ["source", "workflow", "builder", "operator"]):
        return 7
    return 5


def _score_platform_fit(candidate: SocialAngleCandidate) -> int:
    platform = _safe_label(candidate.platform)
    hook_len = len(candidate.hook)
    if platform == "bluesky":
        return 8 if hook_len <= 220 else 5
    if platform == "linkedin":
        return 8 if len(candidate.thesis) >= 60 else 6
    if platform == "video":
        return 8 if "open" in candidate.thesis.lower() or "hook" in candidate.angle_type else 6
    return 5


def _score_tayler_fit(text: str) -> int:
    lower = text.lower()
    if _PRODUCT_PITCH_RE.search(text) or _INFRA_FLEX_RE.search(text):
        return 2
    if any(
        phrase in lower
        for phrase in (
            "in my own research workflow",
            "reviewed the source mix",
            "checked my codebase",
            "tools i rely on",
            "triage sources",
            "builder",
            "operator",
        )
    ):
        return 8
    return 6


def _critique_reason(verdict: str, kill_switches: list[str]) -> str:
    if kill_switches:
        return f"Rejected by hard kill switch: {', '.join(kill_switches)}."
    if verdict == "keep":
        return "Sharp enough to hand to a social writer with source-backed tension."
    if verdict == "revise":
        return "Promising, but needs a tighter why-now or more concrete source detail."
    return "Too generic or weakly evidenced for a writer's time."


def _short_text(value: Any, limit: int) -> str:
    text = redact_sensitive_text(value).replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text or "this story"


def _token_set(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())
        if token not in {"this", "that", "with", "from", "into", "because"}
    }


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
