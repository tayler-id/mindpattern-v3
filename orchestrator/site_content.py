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
_BOLD_LEAD_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(.+?)\*\*\s*(.*)$")
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
_SECTION_CONTAINER_TITLES = {
    "top 5 stories today",
    "top stories",
}
_GENERIC_SECTION_TITLES = _SECTION_CONTAINER_TITLES | {
    "agents",
    "hot projects & oss",
    "hot projects and oss",
    "infrastructure & architecture",
    "infrastructure and architecture",
    "market moves",
    "models",
    "policy & governance",
    "policy and governance",
    "research",
    "saas disruption",
    "security",
    "skills of the day",
    "tools & developer experience",
    "tools and developer experience",
    "vibe coding",
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
_TOPIC_STOPWORDS = _ENTITY_STOPWORDS | {
    "briefing",
    "canonical",
    "cited",
    "citation",
    "citations",
    "cites",
    "com",
    "content",
    "daily",
    "domain",
    "domains",
    "example",
    "fixture",
    "http",
    "https",
    "link",
    "links",
    "mindpattern",
    "news",
    "newsletter",
    "report",
    "reports",
    "said",
    "says",
    "source",
    "sources",
    "story",
    "thread",
    "url",
    "urls",
    "www",
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


def _title_slug(value: str, *, max_length: int = 96) -> str:
    """Create a slug from editorial title text that may contain punctuation."""
    title = re.sub(r"[\\/]+", " ", str(value or ""))
    title = re.sub(r"\s+", " ", title).strip()
    return normalize_slug(title, max_length=max_length)


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


def story_artifact_path(*, slug: str, user: str, reports_root: Path) -> Path:
    """Return a safe artifact path for a public story JSON artifact."""
    if not _SAFE_USER_RE.fullmatch(user or ""):
        raise ValueError("user must be a safe path segment")
    story_slug = normalize_slug(slug)
    base = reports_root.resolve()
    path = (base / user / "site-stories" / f"{story_slug}.json").resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("story artifact path escapes reports root") from exc
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


def _normalize_topic_token(token: str) -> str:
    token = token.lower().strip("-_")
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _topic_terms(text: str, *, limit: int = 16) -> list[str]:
    cleaned = re.sub(r"\[[^\]]+\]\((https?://[^)\s]+)\)", " ", text)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    counts: dict[str, int] = {}
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", cleaned):
        term = _normalize_topic_token(raw)
        if len(term) < 4 or term in _TOPIC_STOPWORDS or term.isdigit():
            continue
        counts[term] = counts.get(term, 0) + 1
    ranked = sorted(counts, key=lambda term: (-counts[term], term))
    return ranked[:limit]


def _plain_summary(text: str, *, limit: int = 280) -> str:
    plain = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1", text)
    plain = re.sub(r"\*\*(.*?)\*\*", r"\1", plain)
    plain = re.sub(r"`([^`]+)`", r"\1", plain)
    plain = re.sub(r"https?://\S+", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) > limit:
        return plain[: limit - 3].rstrip() + "..."
    return plain


def _is_section_container_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title).strip().lower()
    return normalized in _SECTION_CONTAINER_TITLES


def _is_generic_section_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title).strip().lower()
    return normalized in _GENERIC_SECTION_TITLES


def _clean_story_title(title: str) -> str:
    title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title.strip("*_ ")


def _promote_bold_lead_title(title: str, body: str) -> tuple[str, str]:
    if not _is_section_container_title(title):
        return title, body
    match = re.match(r"^\s*\*\*(.+?)\*\*\s*(.*)$", body, flags=re.S)
    if not match:
        return title, body
    promoted = _clean_story_title(match.group(1))
    if len(promoted) < 8:
        return title, body
    rest = match.group(2).strip()
    return promoted, rest or body


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


def _story_graph_connectors(
    *,
    issue_date: str,
    source_refs: list[dict[str, str]],
    entity_refs: list[dict[str, Any]],
    topic_terms: list[str],
    finding_ids: list[Any],
    arc_ids: list[Any],
) -> dict[str, Any]:
    return {
        "issue_date": issue_date,
        "source_urls": sorted({source["url"] for source in source_refs if source.get("url")}),
        "source_domains": sorted({source["domain"] for source in source_refs if source.get("domain")}),
        "entity_ids": sorted({entity["id"] for entity in entity_refs if entity.get("id")}),
        "topic_terms": sorted({term for term in topic_terms if term}),
        "finding_ids": [int(finding_id) for finding_id in finding_ids if str(finding_id).isdigit()],
        "arc_ids": sorted({str(arc_id) for arc_id in arc_ids if str(arc_id)}),
    }


def _story_graph_edges(
    *,
    story_id: str,
    issue_date: str,
    issue_title: str,
    source_refs: list[dict[str, str]],
    entity_refs: list[dict[str, Any]],
    topic_terms: list[str],
    finding_ids: list[int],
    arc_ids: list[str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = [
        {
            "kind": "issue",
            "relationship": "part_of_issue",
            "id": issue_date,
            "label": issue_title,
            "target_url": f"/briefings/{issue_date}",
            "evidence": story_id,
        }
    ]

    seen_domains: set[str] = set()
    for source in source_refs:
        url = source.get("url")
        domain = source.get("domain")
        if url:
            edges.append({
                "kind": "source_url",
                "relationship": "cites_source_url",
                "id": url,
                "label": source.get("title") or domain or url,
                "target_url": url,
                "evidence": story_id,
            })
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            edges.append({
                "kind": "source_domain",
                "relationship": "cites_source_domain",
                "id": domain,
                "label": domain,
                "target_url": f"/source/{domain}",
                "evidence": story_id,
            })

    for entity in entity_refs:
        slug = entity.get("slug") or entity.get("id")
        if not slug:
            continue
        edges.append({
            "kind": "entity",
            "relationship": "mentions_entity",
            "id": entity["id"],
            "label": entity["name"],
            "target_url": f"/e/{slug}",
            "evidence": story_id,
        })

    for term in topic_terms[:12]:
        edges.append({
            "kind": "topic",
            "relationship": "has_topic",
            "id": term,
            "label": term,
            "target_url": "",
            "evidence": story_id,
        })

    for finding_id in finding_ids:
        edges.append({
            "kind": "finding",
            "relationship": "derived_from_finding",
            "id": str(finding_id),
            "label": f"Finding {finding_id}",
            "target_url": f"/f/{finding_id}",
            "evidence": story_id,
        })

    for arc_id in arc_ids:
        edges.append({
            "kind": "arc",
            "relationship": "part_of_arc",
            "id": arc_id,
            "label": arc_id,
            "target_url": "",
            "evidence": story_id,
        })

    return edges


def build_public_story(*, issue: dict[str, Any], story_unit: dict[str, Any]) -> dict[str, Any] | None:
    """Build a public story artifact from a structured issue story unit.

    The MVP publishes only source-backed story units. Sections without source
    evidence remain available inside the canonical briefing but do not get a
    standalone `/s` page.
    """
    source_refs = story_unit.get("source_refs") or []
    if not source_refs:
        return None

    issue_date = validate_run_date(str(story_unit["issue_date"]))
    story_id = normalize_slug(str(story_unit["id"]))
    entity_by_id = {entity["id"]: entity for entity in issue.get("entities", [])}
    entity_refs = [
        entity_by_id[entity_id]
        for entity_id in story_unit.get("entity_ids", [])
        if entity_id in entity_by_id
    ]

    finding_ids = story_unit.get("finding_ids", [])
    arc_ids = story_unit.get("arc_ids", [])
    topic_terms = story_unit.get("topic_terms") or _topic_terms(
        f"{story_unit.get('title', '')}\n{story_unit.get('summary', '')}"
    )
    graph_connectors = _story_graph_connectors(
        issue_date=issue_date,
        source_refs=source_refs,
        entity_refs=entity_refs,
        topic_terms=topic_terms,
        finding_ids=finding_ids,
        arc_ids=arc_ids,
    )
    graph_edges = _story_graph_edges(
        story_id=story_id,
        issue_date=issue_date,
        issue_title=issue["title"],
        source_refs=source_refs,
        entity_refs=entity_refs,
        topic_terms=graph_connectors["topic_terms"],
        finding_ids=graph_connectors["finding_ids"],
        arc_ids=graph_connectors["arc_ids"],
    )

    return {
        "kind": "story",
        "id": story_id,
        "slug": story_id,
        "story_unit_id": story_unit["id"],
        "issue_date": issue_date,
        "issue_title": issue["title"],
        "issue_url": f"/briefings/{issue_date}",
        "section_id": story_unit["section_id"],
        "title": story_unit["title"],
        "summary": story_unit.get("summary", ""),
        "body_excerpt": story_unit.get("body_excerpt", story_unit.get("summary", "")),
        "body_markdown": story_unit.get("body_markdown", story_unit.get("summary", "")),
        "source_refs": source_refs,
        "entity_refs": entity_refs,
        "finding_ids": graph_connectors["finding_ids"],
        "arc_ids": graph_connectors["arc_ids"],
        "graph_connectors": graph_connectors,
        "graph_edges": graph_edges,
        "related_paths": [],
        "target_url": f"/s/{story_id}",
        "confidence": "source-backed",
        "labels": ["source-backed", "canonical briefing excerpt"],
        "json_ld_ready": True,
        "claim_evidence": story_unit.get("claim_evidence", []),
        "provenance": {
            "generated_by": "mindpattern.site_content.public_story",
            "generated_at": issue.get("generated_at"),
            "input_artifacts": issue.get("provenance", {}).get("input_artifacts", []),
            "source_issue_dates": [issue_date],
            "source_story_unit_id": story_unit["id"],
            "redaction_status": issue.get("provenance", {}).get("redaction_status", "passed"),
            "ai_generated": False,
            "human_approved": False,
        },
    }


def _redaction_status(original: str, redacted: str) -> str:
    return "redacted" if original != redacted else "passed"


def _new_section(title: str, index: int) -> dict[str, Any]:
    slug = _title_slug(title)
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
    title, body = _promote_bold_lead_title(title, body)
    title_safe = redact_sensitive_text(_clean_story_title(title))
    slug = _title_slug(title_safe)
    sources = _source_refs(f"{title}\n{body}")
    entities = _extract_entities(f"{title_safe}\n{body}")
    topics = _topic_terms(f"{title_safe}\n{body}")
    summary = _plain_summary(body)
    return {
        "id": f"{date}-{slug}",
        "slug": slug,
        "issue_date": date,
        "section_id": section_id,
        "title": title_safe,
        "summary": summary,
        "body_excerpt": summary,
        "body_markdown": body,
        "finding_ids": [],
        "entity_ids": [entity["id"] for entity in entities],
        "topic_terms": topics,
        "source_refs": sources,
        "arc_ids": [],
        "claim_evidence": [],
        "order": order,
}


def _section_story_units(
    *,
    date: str,
    section: dict[str, Any],
    body_lines: list[str],
    start_order: int,
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_title, current_lines
        if current_title is None:
            return
        story = _story_unit(
            date=date,
            section_id=section["id"],
            title=current_title,
            body_lines=current_lines,
            order=start_order + len(units),
        )
        units.append(story)
        current_title = None
        current_lines = []

    for line in body_lines:
        match = _BOLD_LEAD_RE.match(line)
        if match:
            flush_current()
            current_title = match.group(1).strip()
            rest = match.group(2).strip()
            current_lines = [rest] if rest else []
            continue
        if current_title is not None:
            current_lines.append(line)

    flush_current()

    if units:
        return units
    if _is_generic_section_title(section["title"]):
        return []
    if not re.sub(r"\s+", " ", "\n".join(body_lines)).strip():
        return []
    return [
        _story_unit(
            date=date,
            section_id=section["id"],
            title=section["title"],
            body_lines=body_lines,
            order=start_order,
        )
    ]


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
            section_stories = _section_story_units(
                date=date,
                section=current_section,
                body_lines=section_intro_lines,
                start_order=len(stories) + 1,
            )
            stories.extend(section_stories)
            current_section["story_unit_ids"].extend(story["id"] for story in section_stories)
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
