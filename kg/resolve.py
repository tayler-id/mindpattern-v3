"""Entity resolution: extracted names → canonical kg_entities rows.

Resolution tiers (cheapest first, per docs/v4-research.md §2):
  1. exact alias match (NOCASE index on kg_entity_aliases.alias)
  2. deterministic normalized-alias match (punctuation/spacing variants)
New names create a canonical entity plus aliases for their variants, so the
second time any variant appears it resolves in tier 1.

Junk filtering is deliberately strict: a junk node on the public site is worse
than a missing one (lesson of the ``/e/announced`` cleanup, 2026-07-01).
"""

from __future__ import annotations

import re
import sqlite3

_FALLBACK_STOPWORDS = {
    "announced", "update", "updates", "release", "releases", "new", "news",
    "report", "reports", "launch", "launches", "today", "week", "year",
}


def _topic_stopwords() -> set[str]:
    """Reuse the site-content noise vocabulary; fall back if unimportable."""
    try:
        from orchestrator.site_content import _TOPIC_STOPWORDS

        return set(_TOPIC_STOPWORDS)
    except Exception:
        return set(_FALLBACK_STOPWORDS)


_JUNK_SUBSTRINGS = ("http", "://", " — ", " – ", " | ", " / ")
_SENTENCE_RE = re.compile(r"[.!?]\s+\w")
_HAS_ALNUM_RE = re.compile(r"[A-Za-z0-9]")


def is_junk_entity(name: str) -> bool:
    """True when a name must never become a public graph node."""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text or not _HAS_ALNUM_RE.search(text):
        return True
    if len(text) > 60 or len(text.split()) > 6:
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in _JUNK_SUBSTRINGS):
        return True
    if _SENTENCE_RE.search(text):
        return True
    words = re.findall(r"[a-z0-9']+", lowered)
    if words and all(w in _topic_stopwords() for w in words):
        return True
    return False


def normalize_alias(name: str) -> str:
    """Deterministic matching key: lowercase, alphanumerics joined by spaces."""
    return " ".join(re.findall(r"[a-z0-9]+", str(name or "").lower()))


def public_slug(name: str) -> str:
    """The entity's public URL slug — same normalizer the site API applies to
    inbound ``/api/entities/{slug}`` requests, so list URLs always round-trip
    to detail lookups (names like "Node.js" and "GPT-5.2" would otherwise 404).
    """
    try:
        from orchestrator.site_content import normalize_slug

        return normalize_slug(str(name or ""))
    except ValueError:
        return ""
    except Exception:
        slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
        return slug[:96]


_TYPE_RANK = {"Other": 0}  # every concrete type outranks Other


def _lookup_alias(conn: sqlite3.Connection, alias: str) -> int | None:
    row = conn.execute(
        "SELECT entity_id FROM kg_entity_aliases WHERE alias = ? COLLATE NOCASE LIMIT 1",
        (alias,),
    ).fetchone()
    return int(row[0]) if row else None


def _add_alias(conn: sqlite3.Connection, entity_id: int, alias: str) -> None:
    if alias:
        conn.execute(
            "INSERT OR IGNORE INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)",
            (entity_id, alias),
        )


def resolve_entity(
    conn: sqlite3.Connection,
    name: str,
    entity_type: str,
    *,
    seen_date: str | None = None,
) -> int | None:
    """Return the canonical kg_entities id for ``name``, creating it if new.

    Returns None for junk names. Updates first/last_seen bounds and upgrades
    entity_type when a concrete type arrives for an entity typed 'Other'.
    """
    display = re.sub(r"\s+", " ", str(name or "")).strip()
    if is_junk_entity(display):
        return None

    normalized = normalize_alias(display)
    slug = public_slug(display)
    if not slug:
        return None
    entity_id = _lookup_alias(conn, display)
    if entity_id is None and normalized:
        entity_id = _lookup_alias(conn, normalized)
    if entity_id is None:
        # third tier: two names that render the same public slug are one page,
        # so they must be one entity ("GPT-5.2" / "GPT 5 2" / "gpt-5-2")
        row = conn.execute(
            "SELECT id FROM kg_entities WHERE slug = ? LIMIT 1", (slug,)
        ).fetchone()
        entity_id = int(row[0]) if row else None

    if entity_id is None:
        cursor = conn.execute(
            """
            INSERT INTO kg_entities (canonical_name, slug, entity_type, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            """,
            (display, slug, entity_type, seen_date, seen_date),
        )
        entity_id = int(cursor.lastrowid)
        _add_alias(conn, entity_id, display)
        if normalized and normalized.casefold() != display.casefold():
            _add_alias(conn, entity_id, normalized)
        return entity_id

    _add_alias(conn, entity_id, display)
    if seen_date:
        conn.execute(
            """
            UPDATE kg_entities SET
                first_seen = CASE WHEN first_seen IS NULL OR first_seen > ?
                                  THEN ? ELSE first_seen END,
                last_seen  = CASE WHEN last_seen IS NULL OR last_seen < ?
                                  THEN ? ELSE last_seen END
            WHERE id = ?
            """,
            (seen_date, seen_date, seen_date, seen_date, entity_id),
        )
    if entity_type != "Other":
        conn.execute(
            "UPDATE kg_entities SET entity_type = ? WHERE id = ? AND entity_type = 'Other'",
            (entity_type, entity_id),
        )
    return entity_id
