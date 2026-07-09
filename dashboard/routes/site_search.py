"""Unified site search: stories + findings + entities + sources, one request.

Stories match on title/dek/summary with a recency boost; findings reuse the
semantic embedding search; entities match on name; sources on domain.
Grouped response so the UI renders labeled sections in one round-trip.
"""

from __future__ import annotations

import re
from fastapi import APIRouter, Query

router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _story_matches(story: dict, terms: list[str]) -> bool:
    haystack = _norm(
        f"{story.get('title','')} {story.get('dek','')} {story.get('summary','')}"
    )
    return all(term in haystack for term in terms)


@router.get("/api/search/site")
async def search_site(
    q: str = Query("", max_length=200),
    types: str = Query("stories,findings,entities,sources"),
    section: str = Query(""),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    domain: str = Query(""),
    limit: int = Query(8, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    take: int = Query(0, ge=0, le=1),
    user: str = Query("ramsay"),
):
    """Public: grouped search across the whole public graph.

    An empty query with take=1 is allowed: it lists every story that has
    a take, archive-wide.
    """
    query = q.strip()
    if not query and not take and not section:
        return {"kind": "site_search", "q": q, "groups": {}}

    from dashboard.routes import api as api_routes

    return await api_routes._cached_await(
        ("site-search", user, query, types, section, date_from, date_to, domain, limit, offset, take),
        user,
        lambda: _search_site_uncached(
            query=query, types=types, section=section, date_from=date_from,
            date_to=date_to, domain=domain, limit=limit, offset=offset,
            take=take, user=user,
        ),
    )


async def _search_site_uncached(
    *,
    query: str,
    types: str,
    section: str,
    date_from: str,
    date_to: str,
    domain: str,
    limit: int,
    offset: int,
    take: int,
    user: str,
):
    wanted = {t.strip() for t in types.split(",") if t.strip()}
    if not query:
        wanted = {"stories"}
    terms = [t for t in _norm(query).split(" ") if t]
    groups: dict[str, list] = {}

    from dashboard.routes import api as api_routes

    totals: dict[str, int] = {}
    if "stories" in wanted:
        stories = await api_routes._all_public_stories(user)
        hits = []
        matched = 0
        for story in stories:
            if not _story_matches(story, terms):
                continue
            if take and not story.get("take"):
                continue
            if section and story.get("section_id") != section:
                continue
            issue_date = str(story.get("issue_date") or "")
            if _DATE_RE.match(date_from or "") and issue_date < date_from:
                continue
            if _DATE_RE.match(date_to or "") and issue_date > date_to:
                continue
            if domain and domain not in (story.get("graph_connectors", {}).get("source_domains") or []):
                continue
            matched += 1
            if matched <= offset:
                continue
            if len(hits) < limit:
                hits.append({
                    "slug": story["slug"],
                    "title": story["title"],
                    "summary": str(story.get("summary") or "")[:220],
                    "issue_date": issue_date,
                    "target_url": story.get("target_url") or f"/s/{story['slug']}",
                    "has_take": bool(story.get("take")),
                    "section_id": story.get("section_id") or "",
                    "source_count": len(story.get("source_refs") or []),
                    "entity_count": len(story.get("entity_refs") or []),
                })
        groups["stories"] = hits
        totals["stories"] = matched
        totals["stories_corpus"] = len(stories)

    if "findings" in wanted:
        findings = await api_routes.search_findings(q=query, limit=limit, user=user)
        groups["findings"] = [
            {
                "id": f.get("id"),
                "title": f.get("title", ""),
                "summary": str(f.get("summary") or "")[:220],
                "run_date": f.get("run_date", ""),
                "target_url": f"/f/{f.get('id')}",
                "similarity": f.get("similarity"),
            }
            for f in (findings or [])
            if not domain or domain in str(f.get("source_url") or "")
        ]

    if "entities" in wanted:
        opened = api_routes._open_graph_model(user)
        entity_hits = []
        if opened is not None:
            conn, model = opened
            try:
                listing = model.list_entities(q=query, limit=limit)
                for item in listing.get("items") or []:
                    slug = str(item.get("slug") or "")
                    if not api_routes._is_public_entity_slug(slug):
                        continue
                    entity_hits.append({
                        "slug": slug,
                        "name": item.get("name", ""),
                        "mention_count": item.get("mention_count", 0),
                        "target_url": f"/e/{slug}",
                    })
            finally:
                conn.close()
        groups["entities"] = entity_hits

    if "sources" in wanted:
        conn = api_routes.get_memory_db(user)
        source_hits = []
        if conn is not None:
            try:
                rows = conn.execute(
                    """SELECT url_domain, display_name, hit_count FROM sources
                       WHERE url_domain LIKE ? OR display_name LIKE ?
                       ORDER BY hit_count DESC LIMIT ?""",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
                source_hits = [
                    {
                        "domain": row["url_domain"],
                        "name": row["display_name"] or row["url_domain"],
                        "hit_count": row["hit_count"],
                        "target_url": f"/source/{row['url_domain']}",
                    }
                    for row in rows
                ]
            finally:
                conn.close()
        groups["sources"] = source_hits

    return {"kind": "site_search", "q": query, "groups": groups, "totals": totals}
