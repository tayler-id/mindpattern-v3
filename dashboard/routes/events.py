"""Public event ingestion + trending/popular reads.

POST /api/event   — privacy-safe first-party event capture (202 always)
GET  /api/trending — blended on-site + corpus trending, with direction
GET  /api/popular  — most read, all-time or 7d window
"""

from __future__ import annotations

import time
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from memory.events_db import ALLOWED_EVENTS, open_events_db, record_event
from orchestrator.trending import (
    blend_scores,
    corpus_score,
    onsite_score,
    trend_direction,
)

router = APIRouter()

_MAX_BODY = 1024
_TRENDING_CACHE: dict[str, tuple[float, list]] = {}
_TRENDING_TTL = 300.0


@router.post("/api/event", status_code=202)
async def post_event(request: Request):
    """Public: record one site event. Always 202 — analytics never break pages."""
    try:
        body = await request.body()
        if len(body) > _MAX_BODY:
            return {"status": "ignored"}
        import json

        payload = json.loads(body)
        if not isinstance(payload, dict):
            return {"status": "ignored"}
        conn = open_events_db()
        try:
            ok = record_event(conn, payload)
        finally:
            conn.close()
        return {"status": "ok" if ok else "ignored"}
    except Exception:
        return {"status": "ignored"}


def _events_for_scoring(conn, *, since_hours: float = 96.0) -> dict[str, list[dict]]:
    cutoff = int(time.time() - since_hours * 3600)
    rows = conn.execute(
        "SELECT type, target, ts, value FROM events WHERE ts >= ? AND target != ''",
        (cutoff,),
    ).fetchall()
    by_target: dict[str, list[dict]] = {}
    for row in rows:
        by_target.setdefault(row["target"], []).append(dict(row))
    return by_target


def _domain_recurrence(user: str) -> dict[str, int]:
    from dashboard.routes.api import get_memory_db

    conn = get_memory_db(user)
    if conn is None:
        return {}
    try:
        rows = conn.execute(
            """SELECT source_url, COUNT(*) c FROM findings
               WHERE run_date >= date('now', '-7 day') GROUP BY source_url"""
        ).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()
    recurrence: dict[str, int] = {}
    for row in rows:
        url = str(row["source_url"] or "")
        if url.startswith("http") and len(url.split("/")) > 2:
            domain = url.split("/")[2]
            recurrence[domain] = recurrence.get(domain, 0) + int(row["c"])
    return recurrence


async def _ranked_stories(user: str, limit: int) -> list[dict]:
    from dashboard.routes import api as api_routes

    stories = await api_routes._all_public_stories(user)
    recent = stories[:400]  # trending pool: newest 400

    events_conn = open_events_db()
    try:
        by_target = _events_for_scoring(events_conn)
        prior_by_target = {
            slug: [dict(e, ts=e["ts"] + 24 * 3600) for e in evs]
            for slug, evs in by_target.items()
        }
    finally:
        events_conn.close()

    recurrence = _domain_recurrence(user)
    onsite = {s["slug"]: onsite_score(by_target.get(s["slug"], [])) for s in recent}
    corpus = {s["slug"]: corpus_score(s, domain_recurrence=recurrence) for s in recent}
    blended = blend_scores(onsite, corpus)

    now = time.time()
    prior_onsite = {
        s["slug"]: onsite_score(prior_by_target.get(s["slug"], []), now=now)
        for s in recent
    }
    prior_blended = blend_scores(prior_onsite, corpus)

    ranked = sorted(recent, key=lambda s: blended.get(s["slug"], 0.0), reverse=True)
    items = []
    for story in ranked[:limit]:
        slug = story["slug"]
        item = dict(story)
        item["trending_score"] = round(blended.get(slug, 0.0), 4)
        item["trend"] = trend_direction(
            blended.get(slug, 0.0), prior_blended.get(slug, 0.0)
        )
        items.append(item)
    return items


@router.get("/api/trending")
async def get_trending(user: str = Query("ramsay"), limit: int = Query(30, ge=1, le=100)):
    """Public: stories ranked by blended on-site + corpus trending score."""
    cache_key = f"{user}:{limit}"
    now = time.monotonic()
    cached = _TRENDING_CACHE.get(cache_key)
    if cached and now - cached[0] < _TRENDING_TTL:
        return {"kind": "trending", "items": cached[1], "total": len(cached[1])}
    items = await _ranked_stories(user, limit)
    _TRENDING_CACHE[cache_key] = (now, items)
    return {"kind": "trending", "items": items, "total": len(items)}


@router.get("/api/popular")
async def get_popular(
    user: str = Query("ramsay"),
    window: str = Query("all"),
    limit: int = Query(30, ge=1, le=100),
):
    """Public: most-read stories by raw view count (all time or 7d)."""
    if window not in {"all", "7d"}:
        return JSONResponse(status_code=400, content={"error": "window must be all|7d"})
    conn = open_events_db()
    try:
        where = "type = 'story_view' AND target != ''"
        params: list = []
        if window == "7d":
            where += " AND ts >= ?"
            params.append(int(time.time() - 7 * 86400))
        rows = conn.execute(
            f"""SELECT target, COUNT(*) views, COUNT(DISTINCT anon_id) readers
                FROM events WHERE {where} GROUP BY target
                ORDER BY views DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
    finally:
        conn.close()

    from dashboard.routes import api as api_routes

    stories = {s["slug"]: s for s in await api_routes._all_public_stories(user)}
    items = []
    for row in rows:
        story = stories.get(row["target"])
        if story is None:
            continue
        item = dict(story)
        item["views"] = int(row["views"])
        item["unique_readers"] = int(row["readers"])
        items.append(item)
    return {"kind": "popular", "window": window, "items": items, "total": len(items)}
