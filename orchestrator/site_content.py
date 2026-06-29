"""Public Rabbit Hole content contracts and deterministic issue splitting.

This module is intentionally pure: no database, network, Slack, model, provider,
or deploy dependencies. It converts canonical newsletter markdown into safe
public graph-shaped data that Rabbit Hole can render.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import (
    normalize_artifact_slug,
    redact_sensitive_text,
    validate_run_date,
)

_SAFE_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9]+|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z0-9]+|[A-Z]{2,}))*\b")
_COMMON_ENTITIES = {
    "AI",
    "API",
    "Briefing",
    "Daily Briefing",
    "MindPattern Daily Briefing",
    "Opening",
    "See",
    "Top Stories",
    "Why",
}
_ENTITY_STOPWORDS = {
    "a",
    "about",
    "add",
    "after",
    "all",
    "also",
    "an",
    "and",
    "because",
    "before",
    "below",
    "both",
    "but",
    "by",
    "day",
    "default",
    "delete",
    "every",
    "for",
    "from",
    "here",
    "his",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "january",
    "just",
    "june",
    "less",
    "let",
    "live",
    "long",
    "make",
    "may",
    "more",
    "move",
    "new",
    "neither",
    "not",
    "now",
    "on",
    "open",
    "overall",
    "pair",
    "patch",
    "prefer",
    "pull",
    "put",
    "quick",
    "read",
    "real",
    "reply",
    "route",
    "see",
    "single",
    "source",
    "stories",
    "story",
    "stop",
    "the",
    "these",
    "this",
    "to",
    "today",
    "top",
    "two",
    "use",
    "via",
    "want",
    "why",
    "wire",
    "with",
    "work",
    "you",
    "your",
}


def normalize_slug(value: str, *, max_length: int = 96) -> str:
    """Normalize a public slug and reject path-like or empty values."""
    raw = str(value or "")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("slug must not contain path separators")
    slug = normalize_artifact_slug(raw, max_length=max_length)
    if slug == "artifact":
        raise ValueError("slug must contain at least one alphanumeric character")
    return slug


def issue_artifact_path(*, date: str, user: str, reports_root: Path) -> Path:
    """Return a safe artifact path for structured issue JSON."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    date = validate_run_date(date)
    base = reports_root.resolve()
    path = (base / user / "site-issues" / f"{date}.json").resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("issue artifact path escapes reports root") from exc
    return path


def _source_refs(text: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, url in _MARKDOWN_LINK_RE.findall(text):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        safe_url = redact_sensitive_text(url)
        if safe_url in seen:
            continue
        seen.add(safe_url)
        refs.append(
            {
                "url": safe_url,
                "domain": parsed.netloc.replace("www.", "", 1).lower(),
                "title": redact_sensitive_text(label.strip()),
            }
        )
    return refs


def _extract_entities(text: str) -> list[dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}
    for match in _ENTITY_RE.findall(text):
        name = re.sub(r"\s+", " ", match).strip()
        if not _is_entity_candidate(name):
            continue
        slug = normalize_artifact_slug(name)
        entities[slug] = {
            "id": slug,
            "slug": slug,
            "name": redact_sensitive_text(name),
            "kind": "unknown",
        }
    return sorted(entities.values(), key=lambda item: item["name"].lower())


def _is_entity_candidate(name: str) -> bool:
    if len(name) < 3 or name in _COMMON_ENTITIES:
        return False

    tokens = name.split()
    if len(tokens) > 5:
        return False

    lower_tokens = [token.lower() for token in tokens]
    if name.lower() in _ENTITY_STOPWORDS:
        return False

    meaningful = [
        token
        for token, lower in zip(tokens, lower_tokens)
        if lower not in _ENTITY_STOPWORDS
    ]
    if not meaningful:
        return False

    stopword_ratio = (len(tokens) - len(meaningful)) / len(tokens)
    if len(tokens) > 1 and stopword_ratio >= 0.5:
        return False

    if len(tokens) == 1:
        token = tokens[0]
        lower = lower_tokens[0]
        if lower in {"ai", "api"}:
            return False
        if token.isupper():
            return len(token) >= 2
        return (
            len(token) >= 4
            or any(char.isupper() for char in token[1:])
            or any(char.isdigit() for char in token)
        )

    return True


def _redaction_status(original: str, redacted: str) -> str:
    return "redacted" if original != redacted else "passed"


def _new_section(title: str, index: int) -> dict[str, Any]:
    slug = normalize_slug(title)
    return {
        "id": slug,
        "slug": slug,
        "title": redact_sensitive_text(title),
        "order": index,
        "summary": "",
        "story_unit_ids": [],
    }


def _story_unit(
    *,
    date: str,
    section_id: str,
    title: str,
    body_lines: list[str],
    order: int,
) -> dict[str, Any]:
    body = redact_sensitive_text("\n".join(body_lines).strip())
    title_safe = redact_sensitive_text(title)
    slug = normalize_slug(title)
    sources = _source_refs(body)
    entities = _extract_entities(f"{title_safe}\n{body}")
    summary = re.sub(r"\s+", " ", body).strip()
    if len(summary) > 240:
        summary = summary[:237].rstrip() + "..."
    return {
        "id": f"{date}-{slug}",
        "slug": slug,
        "issue_date": date,
        "section_id": section_id,
        "title": title_safe,
        "summary": summary,
        "body_excerpt": summary,
        "finding_ids": [],
        "entity_ids": [entity["id"] for entity in entities],
        "source_refs": sources,
        "arc_ids": [],
        "claim_evidence": [],
        "order": order,
    }


def build_structured_issue(
    *,
    date: str,
    user: str,
    title: str,
    content: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Split a canonical newsletter markdown report into public issue graph data."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    date = validate_run_date(date)
    generated = generated_at or datetime.now(timezone.utc).isoformat()

    redacted_content = redact_sensitive_text(content)
    status = _redaction_status(content, redacted_content)
    lines = redacted_content.splitlines()

    issue_title = redact_sensitive_text(title)
    sections: list[dict[str, Any]] = []
    stories: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_story_title: str | None = None
    current_story_lines: list[str] = []
    section_intro_lines: list[str] = []

    def flush_story() -> None:
        nonlocal current_story_title, current_story_lines
        if current_story_title is None or current_section is None:
            return
        story = _story_unit(
            date=date,
            section_id=current_section["id"],
            title=current_story_title,
            body_lines=current_story_lines,
            order=len(stories) + 1,
        )
        stories.append(story)
        current_section["story_unit_ids"].append(story["id"])
        current_story_title = None
        current_story_lines = []

    def flush_section_intro() -> None:
        nonlocal section_intro_lines
        if current_section is None or not section_intro_lines:
            section_intro_lines = []
            return
        summary = re.sub(r"\s+", " ", "\n".join(section_intro_lines)).strip()
        current_section["summary"] = summary[:240]
        if not current_section["story_unit_ids"] and summary:
            story = _story_unit(
                date=date,
                section_id=current_section["id"],
                title=current_section["title"],
                body_lines=section_intro_lines,
                order=len(stories) + 1,
            )
            stories.append(story)
            current_section["story_unit_ids"].append(story["id"])
        section_intro_lines = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if not match:
            if current_story_title is not None:
                current_story_lines.append(line)
            elif current_section is not None:
                section_intro_lines.append(line)
            continue

        level = len(match.group(1))
        heading = match.group(2).strip()
        if level == 1:
            continue
        if level == 2:
            flush_story()
            flush_section_intro()
            current_section = _new_section(heading, len(sections) + 1)
            sections.append(current_section)
            continue
        if level >= 3:
            if current_section is None:
                current_section = _new_section("Briefing", len(sections) + 1)
                sections.append(current_section)
            flush_story()
            flush_section_intro()
            current_story_title = heading
            current_story_lines = []

    flush_story()
    flush_section_intro()

    if not sections:
        section = _new_section("Briefing", 1)
        sections.append(section)
        story = _story_unit(
            date=date,
            section_id=section["id"],
            title=issue_title,
            body_lines=lines,
            order=1,
        )
        stories.append(story)
        section["story_unit_ids"].append(story["id"])

    all_text = "\n".join([issue_title, redacted_content])
    entities = _extract_entities(all_text)
    source_refs = _source_refs(redacted_content)
    return {
        "date": date,
        "user": user,
        "title": issue_title,
        "slug": date,
        "sections": sections,
        "entities": entities,
        "story_units": stories,
        "source_trail": source_refs,
        "claim_evidence": [],
        "generated_at": generated,
        "provenance": {
            "generated_by": "mindpattern.site_content.issue_splitter",
            "generated_at": generated,
            "input_artifacts": [f"reports/{user}/{date}.md"],
            "source_finding_ids": [],
            "source_issue_dates": [date],
            "redaction_status": status,
            "ai_generated": False,
            "human_approved": False,
        },
    }
