"""Internal site analytics: what readers actually do on Rabbit Hole.

Private (bearer token) — answers: which stories are popular (today / 7d /
all time), what gets clicked, where readers come from, subscribe conversion.
"""

from __future__ import annotations

import time
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from memory.events_db import open_events_db

router = APIRouter()

_WINDOWS = {"today": 1, "7d": 7, "all": 3650}


def _summary(window: str) -> dict:
    days = _WINDOWS.get(window, 7)
    cutoff = int(time.time() - days * 86400)
    conn = open_events_db()
    try:
        top_stories = [
            dict(r) for r in conn.execute(
                """SELECT target, COUNT(*) views, COUNT(DISTINCT anon_id) readers
                   FROM events WHERE type='story_view' AND ts>=? AND target!=''
                   GROUP BY target ORDER BY views DESC LIMIT 25""", (cutoff,))
        ]
        clicks = [
            dict(r) for r in conn.execute(
                """SELECT type, COUNT(*) count FROM events
                   WHERE ts>=? AND type IN ('related_click','entity_click',
                     'source_click','briefing_click','outbound_source_click',
                     'search_query')
                   GROUP BY type ORDER BY count DESC""", (cutoff,))
        ]
        referrers = [
            dict(r) for r in conn.execute(
                """SELECT ref_domain, COUNT(*) count FROM events
                   WHERE ts>=? AND ref_domain!='' GROUP BY ref_domain
                   ORDER BY count DESC LIMIT 15""", (cutoff,))
        ]
        subs = {
            r["type"]: r["c"] for r in conn.execute(
                """SELECT type, COUNT(*) c FROM events
                   WHERE ts>=? AND type IN ('subscribe_submitted','subscribe_success')
                   GROUP BY type""", (cutoff,))
        }
        totals = dict(conn.execute(
            """SELECT COUNT(*) events, COUNT(DISTINCT anon_id) readers
               FROM events WHERE ts>=?""", (cutoff,)).fetchone())
    finally:
        conn.close()
    submitted = subs.get("subscribe_submitted", 0)
    success = subs.get("subscribe_success", 0)
    return {
        "window": window,
        "totals": totals,
        "top_stories": top_stories,
        "clicks": clicks,
        "referrers": referrers,
        "subscribe": {
            "submitted": submitted,
            "success": success,
            "conversion": round(success / submitted, 3) if submitted else None,
        },
    }


@router.get("/api/site-analytics/summary")
async def site_analytics_summary(window: str = Query("7d")):
    """Private: reader-behavior summary for the internal dash."""
    if window not in _WINDOWS:
        window = "7d"
    return _summary(window)


@router.get("/site-analytics", response_class=HTMLResponse)
async def site_analytics_page(request: Request, window: str = Query("7d")):
    """Private: minimal internal dash — tables over the summary."""
    if window not in _WINDOWS:
        window = "7d"
    data = _summary(window)
    tabs = " · ".join(
        f'<a href="/site-analytics?window={w}"{" style=\"font-weight:bold\"" if w == window else ""}>{w}</a>'
        for w in _WINDOWS
    )
    story_rows = "".join(
        f'<tr><td><a href="https://mindpattern.ai/s/{s["target"]}">{s["target"]}</a></td>'
        f'<td>{s["views"]}</td><td>{s["readers"]}</td></tr>'
        for s in data["top_stories"]
    ) or '<tr><td colspan="3">no story views in window</td></tr>'
    click_rows = "".join(
        f'<tr><td>{c["type"]}</td><td>{c["count"]}</td></tr>' for c in data["clicks"]
    ) or '<tr><td colspan="2">none</td></tr>'
    ref_rows = "".join(
        f'<tr><td>{r["ref_domain"]}</td><td>{r["count"]}</td></tr>' for r in data["referrers"]
    ) or '<tr><td colspan="2">direct / none</td></tr>'
    sub = data["subscribe"]
    html = f"""<!doctype html><html><head><title>Site analytics · {window}</title>
<style>body{{font-family:ui-monospace,monospace;max-width:860px;margin:2rem auto;padding:0 1rem;background:#f4f1ea;color:#1a1a1a}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}}td,th{{border:1px solid #d8d2c4;padding:.35rem .6rem;text-align:left;font-size:13px}}
th{{background:#ece7db;text-transform:uppercase;font-size:11px;letter-spacing:.08em}}h1{{font-size:20px}}h2{{font-size:14px;text-transform:uppercase;letter-spacing:.08em}}</style></head><body>
<h1>Rabbit Hole — reader analytics</h1>
<p>Window: {tabs} · {data["totals"]["events"]} events · {data["totals"]["readers"]} readers</p>
<h2>Top stories</h2><table><tr><th>story</th><th>views</th><th>readers</th></tr>{story_rows}</table>
<h2>Clicks</h2><table><tr><th>type</th><th>count</th></tr>{click_rows}</table>
<h2>Referrers</h2><table><tr><th>domain</th><th>count</th></tr>{ref_rows}</table>
<h2>Subscribe</h2><p>submitted {sub["submitted"]} · success {sub["success"]} · conversion {sub["conversion"] if sub["conversion"] is not None else "n/a"}</p>
</body></html>"""
    return HTMLResponse(html)
