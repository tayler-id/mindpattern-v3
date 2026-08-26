"""Internal site analytics: what readers actually do on Rabbit Hole.

Private (bearer token) — answers: which stories are popular (today / 7d /
all time), what gets clicked, where readers come from, subscribe conversion,
and how much of the traffic is AI crawlers vs humans.

The /site-analytics page is the live version of the editorial dashboard
originally built as a static artifact (2026-07-09): same design, but every
number is computed from site_events.db at request time.
"""

from __future__ import annotations

import json
import logging
import time
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from memory.events_db import open_events_db

logger = logging.getLogger(__name__)

router = APIRouter()

_WINDOWS = {"today": 1, "7d": 7, "all": 3650}
_WINDOW_LABELS = {"today": "last 24 hours", "7d": "last 7 days", "all": "all time"}
_MAX_DAILY_COLUMNS = 60

_MIX_LABELS = {
    "page_view": "Page views",
    "story_view": "Story views",
    "scroll_depth": "Scroll-depth pings",
    "related_click": "Related-story clicks",
    "entity_click": "Entity clicks",
    "source_click": "Source clicks",
    "briefing_click": "Briefing clicks",
    "outbound_source_click": "Outbound source clicks",
    "search_query": "Searches",
    "subscribe_submitted": "Subscribe submitted",
    "subscribe_success": "Subscribe confirmed",
    "share": "Shares",
    "web_vital": "Web vitals (sampled)",
}

# Correlated existence probe: did this anon_id send anything before the window
# opened? Rides idx_events_anon_ts, so it is one index seek per reader, not a
# scan. Crawler hits are excluded because they carry no anon_id and would only
# ever match the empty string, which the callers already filter out. Owner-
# flagged events DO count as prior presence: the same browser was here before,
# whoever was driving it.
_SEEN_BEFORE = (
    "EXISTS(SELECT 1 FROM events prior"
    " WHERE prior.anon_id={alias}.anon_id AND prior.ts<?"
    " AND prior.type!='agent_hit')"
)


def _summary(window: str) -> dict:
    days = _WINDOWS.get(window, 7)
    cutoff = int(time.time() - days * 86400)
    # The all-time window reaches back before the store existed, so nothing can
    # precede it and the probe would answer "new" for every reader. Skip the
    # work rather than run one index seek per reader to produce a number the
    # page hides and a payload consumer would misread as fact.
    new_split = window != "all"
    conn = open_events_db()
    try:
        # Reader metrics exclude owner-flagged events; owner activity is
        # reported alongside, marked, never blended into reader counts.
        top_stories = [
            dict(r) for r in conn.execute(
                """SELECT target,
                          SUM(owner=0) views,
                          COUNT(DISTINCT CASE WHEN owner=0 THEN anon_id END) readers,
                          SUM(owner=1) owner_views
                   FROM events WHERE type='story_view' AND ts>=? AND target!=''
                   GROUP BY target ORDER BY views DESC, owner_views DESC
                   LIMIT 25""", (cutoff,))
        ]
        clicks = [
            dict(r) for r in conn.execute(
                """SELECT type, COUNT(*) count FROM events
                   WHERE ts>=? AND owner=0 AND type IN ('related_click','entity_click',
                     'source_click','briefing_click','outbound_source_click',
                     'search_query')
                   GROUP BY type ORDER BY count DESC""", (cutoff,))
        ]
        # Per-referrer readers, split new vs returning, so "google sent me N,
        # M of them new" is one row rather than a subtraction. A reader who
        # arrived from two domains counts once under each; the split is a
        # property of the anon_id, not of the referrer.
        if new_split:
            referrers = [
                dict(r) for r in conn.execute(
                    f"""WITH pairs AS (
                         SELECT DISTINCT ref_domain, anon_id FROM events
                         WHERE ts>=? AND type='page_view' AND owner=0
                           AND anon_id!='' AND ref_domain!=''
                       )
                       SELECT ref_domain,
                              COUNT(*) count,
                              SUM(CASE WHEN {_SEEN_BEFORE.format(alias='pairs')}
                                       THEN 0 ELSE 1 END) new_count
                       FROM pairs GROUP BY ref_domain
                       ORDER BY count DESC, ref_domain LIMIT 15""",
                    (cutoff, cutoff))
            ]
            for row in referrers:
                row["new_count"] = row["new_count"] or 0
                row["returning_count"] = row["count"] - row["new_count"]
        else:
            referrers = [
                dict(r) for r in conn.execute(
                    """SELECT ref_domain, COUNT(DISTINCT anon_id) count FROM events
                       WHERE ts>=? AND type='page_view' AND owner=0
                         AND anon_id!='' AND ref_domain!=''
                       GROUP BY ref_domain
                       ORDER BY count DESC, ref_domain LIMIT 15""", (cutoff,))
            ]
        subs = {
            r["type"]: r["c"] for r in conn.execute(
                """SELECT type, COUNT(*) c FROM events
                   WHERE ts>=? AND owner=0
                     AND type IN ('subscribe_submitted','subscribe_success')
                   GROUP BY type""", (cutoff,))
        }
        agent_hits = [
            dict(r) for r in conn.execute(
                """SELECT target, COUNT(*) hits FROM events
                   WHERE type='agent_hit' AND ts>=? GROUP BY target
                   ORDER BY hits DESC LIMIT 20""", (cutoff,))
        ]
        agent_pages = [
            dict(r) for r in conn.execute(
                """SELECT path, COUNT(*) hits FROM events
                   WHERE type='agent_hit' AND ts>=? AND path!=''
                   GROUP BY path ORDER BY hits DESC LIMIT 15""", (cutoff,))
        ]
        search_terms = [
            dict(r) for r in conn.execute(
                """SELECT target, SUM(owner=0) count, SUM(owner=1) owner_count
                   FROM events WHERE type='search_query' AND ts>=? AND target!=''
                   GROUP BY target ORDER BY count DESC LIMIT 20""", (cutoff,))
        ]
        daily = [
            dict(r) for r in conn.execute(
                """SELECT date(ts,'unixepoch') d,
                          SUM(type='agent_hit') bots,
                          SUM(type!='agent_hit' AND owner=0) readers,
                          SUM(type!='agent_hit' AND owner=1) owner,
                          SUM(type='story_view' AND owner=0) views
                   FROM events WHERE ts>=? GROUP BY d ORDER BY d""", (cutoff,))
        ][-_MAX_DAILY_COLUMNS:]
        mix = [
            {"type": r["type"], "label": _MIX_LABELS.get(r["type"], r["type"]),
             "count": r["readers"], "owner_count": r["owner_n"]}
            for r in conn.execute(
                """SELECT type, SUM(owner=0) readers, SUM(owner=1) owner_n
                   FROM events WHERE ts>=? AND type!='agent_hit'
                   GROUP BY type ORDER BY readers DESC, owner_n DESC""", (cutoff,))
        ]
        scroll = [
            dict(r) for r in conn.execute(
                """SELECT value, COUNT(*) n FROM events
                   WHERE type='scroll_depth' AND ts>=? AND value>0 AND owner=0
                   GROUP BY value ORDER BY value""", (cutoff,))
        ]
        totals = dict(conn.execute(
            """SELECT COUNT(*) events,
                      COUNT(DISTINCT CASE WHEN anon_id!='' AND owner=0
                            AND type!='agent_hit' THEN anon_id END) readers,
                      SUM(type='agent_hit') crawler_hits,
                      SUM(type='story_view' AND owner=0) story_views,
                      SUM(type!='agent_hit' AND owner=1) owner_events
               FROM events WHERE ts>=?""", (cutoff,)).fetchone())
        # New vs returning. totals["readers"] is unique-in-window, which is not
        # the same question. A reader is new when their anon_id sent no event
        # before the window opened.
        split = conn.execute(
            f"""SELECT COUNT(*) window_readers,
                       SUM(CASE WHEN {_SEEN_BEFORE.format(alias='w')}
                                THEN 0 ELSE 1 END) new_readers
                FROM (SELECT DISTINCT anon_id FROM events
                      WHERE ts>=? AND owner=0 AND type!='agent_hit'
                        AND anon_id!='') w""", (cutoff, cutoff)).fetchone() if new_split else None
    finally:
        conn.close()
    if split is None:
        # None, not a number. "Every all-time reader is new" is true only
        # because the question is unanswerable in that window, and a consumer
        # of /api/site-analytics/summary would read a number as fact.
        totals["new_readers"] = None
        totals["returning_readers"] = None
    else:
        # The page states that new + returning equals unique readers, so derive
        # returning from totals["readers"] rather than from the split's own count.
        # The two predicates are identical; if they ever drift, that is a bug and
        # the copy would be lying, so say so in the log.
        identified = split["window_readers"] or 0
        new_readers = min(split["new_readers"] or 0, totals["readers"] or 0)
        if identified != (totals["readers"] or 0):
            logger.warning(
                "site-analytics: reader counts disagree (split=%s totals=%s)",
                identified, totals["readers"])
        totals["new_readers"] = new_readers
        totals["returning_readers"] = (totals["readers"] or 0) - new_readers
    events = totals["events"] or 0
    crawler_hits = totals["crawler_hits"] or 0
    owner_events = totals["owner_events"] or 0
    totals["crawler_hits"] = crawler_hits
    totals["owner_events"] = owner_events
    totals["story_views"] = totals["story_views"] or 0
    totals["human_events"] = events - crawler_hits
    totals["reader_events"] = events - crawler_hits - owner_events
    totals["crawler_share"] = round(crawler_hits / events * 100, 1) if events else 0.0
    submitted = subs.get("subscribe_submitted", 0)
    success = subs.get("subscribe_success", 0)
    return {
        "window": window,
        "window_label": _WINDOW_LABELS.get(window, window),
        "window_start": time.strftime("%d %b %Y %H:%M UTC", time.gmtime(cutoff)),
        # False on the all-time window: see the note where new_split is set.
        # totals.new_readers / returning_readers are null when this is false.
        "new_split": new_split,
        "totals": totals,
        "daily": daily,
        "mix": mix,
        "scroll": scroll,
        "top_stories": top_stories,
        "clicks": clicks,
        "referrers": referrers,
        "agents": {"by_bot": agent_hits, "top_pages": agent_pages},
        "search_terms": search_terms,
        "subscribe": {
            "submitted": submitted,
            "success": success,
            "conversion": round(success / submitted, 3) if submitted else None,
        },
    }


async def _story_titles(slugs: list[str]) -> dict[str, str]:
    """Best-effort slug → headline map from the site read model."""
    if not slugs:
        return {}
    try:
        from dashboard.routes import api as api_routes
        stories = await api_routes._all_public_stories("ramsay")
    except Exception:
        logger.warning("site-analytics: story title lookup failed", exc_info=True)
        return {}
    wanted = set(slugs)
    return {
        s["slug"]: s["title"]
        for s in stories
        if s.get("slug") in wanted and s.get("title")
    }


async def _summary_with_titles(window: str) -> dict:
    data = _summary(window)
    titles = await _story_titles([s["target"] for s in data["top_stories"]])
    for story in data["top_stories"]:
        story["title"] = titles.get(story["target"], "")
    return data


@router.get("/api/site-analytics/summary")
async def site_analytics_summary(window: str = Query("7d")):
    """Private: reader-behavior summary for the internal dash."""
    if window not in _WINDOWS:
        window = "7d"
    return await _summary_with_titles(window)


# The page shell. Placeholders (__DATA__, __TABS__, __GENERATED__) are
# replaced server-side; everything dynamic renders client-side from the
# injected JSON so user-supplied strings never touch raw HTML.
_PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>MindPattern — Site Analytics</title>
<style>
  :root {
    --paper: #ffffff; --panel: #f2f2f4; --ink: #0e0e0f; --ink-prose: #1d1d20;
    --ink-soft: #55555a; --line: #e8e8ea; --line-strong: #0e0e0f;
    --human: #e63b12; --human-wash: #fdeae4; --crawler: #0797a6; --crawler-wash: #e2f4f6;
    --owner: #b98900;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --paper: #141416; --panel: #1e1e21; --ink: #f0f0f2; --ink-prose: #d8d8dc;
      --ink-soft: #9a9aa2; --line: #2a2a2e; --line-strong: #f0f0f2;
      --human: #f0552b; --human-wash: #2c1a14; --crawler: #12a8b8; --crawler-wash: #10262a;
      --owner: #d9a80f;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink-prose);
    font-family: "Source Serif 4", "Source Serif Pro", Georgia, "Times New Roman", serif;
    font-size: 15px; line-height: 1.55;
  }
  .mono { font-family: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  .display {
    font-family: Archivo, "Archivo Variable", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-weight: 850; letter-spacing: -0.02em; color: var(--ink);
  }
  .page { max-width: 1080px; margin: 0 auto; padding: 0 28px 72px; }
  .folio {
    display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: baseline;
    justify-content: space-between; border-bottom: 2px solid var(--line-strong);
    padding: 18px 0 12px;
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-soft);
  }
  .folio b { color: var(--ink); font-weight: 600; }
  .folio a { color: var(--ink-soft); text-decoration: none; }
  .folio a.active, .folio a:hover { color: var(--ink); font-weight: 600; }
  h1 {
    margin: 34px 0 0; font-size: clamp(38px, 6vw, 62px); line-height: 0.98;
    text-transform: uppercase; text-wrap: balance;
  }
  h1 .flood { background: var(--ink); color: var(--paper); padding: 0 0.12em; }
  .dek { max-width: 62ch; margin: 18px 0 0; font-size: 17px; color: var(--ink-prose); }
  .dek b { color: var(--ink); }
  .tiles {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    border-top: 2px solid var(--line-strong); border-bottom: 1px solid var(--line);
    margin-top: 34px;
  }
  .tile { padding: 16px 18px 18px 0; border-right: 1px solid var(--line); }
  .tile:last-child { border-right: none; }
  .tile + .tile { padding-left: 18px; }
  .tile .k {
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 10.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-soft);
  }
  .tile .v {
    font-family: Archivo, "Helvetica Neue", Arial, sans-serif;
    font-weight: 800; font-size: 30px; color: var(--ink); margin-top: 6px;
    font-variant-numeric: tabular-nums; letter-spacing: -0.01em;
  }
  .tile .v .unit { font-size: 14px; font-weight: 600; color: var(--ink-soft); margin-left: 2px; }
  .tile.human .v { color: var(--human); }
  .tile.crawler .v { color: var(--crawler); }
  .tile.owner .v { color: var(--owner); }
  section { margin-top: 52px; }
  .kicker {
    display: flex; align-items: baseline; gap: 12px;
    border-bottom: 2px solid var(--line-strong); padding-bottom: 8px;
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink);
  }
  .kicker .sub { color: var(--ink-soft); letter-spacing: 0.1em; }
  .kicker .dot { width: 8px; height: 8px; border-radius: 50%; align-self: center; flex: none; }
  .dot.h { background: var(--human); }
  .dot.c { background: var(--crawler); }
  .dot.o { background: var(--owner); }
  .duo { display: grid; grid-template-columns: 1fr 1fr; gap: 0 40px; }
  @media (max-width: 760px) { .duo { grid-template-columns: 1fr; } }
  .cols { display: flex; align-items: flex-end; gap: 6px; height: 150px; margin-top: 26px; }
  .col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; height: 100%; position: relative; cursor: default; }
  .col .bar { border-radius: 3px 3px 0 0; min-height: 2px; }
  .col.human .bar { background: var(--human); }
  .col.crawler .bar { background: var(--crawler); }
  .col .bar.owner { background: var(--owner); border-radius: 3px 3px 0 0; }
  .col .bar.under { border-radius: 0; }
  .col .top {
    position: absolute; left: 50%; transform: translateX(-50%);
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 10px; color: var(--ink-soft); white-space: nowrap;
  }
  .xaxis { display: flex; gap: 6px; border-top: 1px solid var(--line); padding-top: 6px; }
  .xaxis span {
    flex: 1; text-align: center; overflow: hidden;
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 9.5px; letter-spacing: 0.04em; color: var(--ink-soft);
  }
  .ranked { margin-top: 8px; }
  .rrow {
    display: grid; grid-template-columns: 26px minmax(120px, 34%) 1fr 84px;
    gap: 12px; align-items: center;
    border-bottom: 1px solid var(--line); padding: 9px 0; cursor: default;
  }
  .rrow .idx { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace; font-size: 10.5px; color: var(--ink-soft); }
  .rrow .name { font-family: Archivo, "Helvetica Neue", Arial, sans-serif; font-weight: 640; font-size: 13.5px; color: var(--ink); line-height: 1.25; overflow-wrap: anywhere; }
  .rrow .name a { color: inherit; text-decoration: none; }
  .rrow .name a:hover { text-decoration: underline; }
  .rrow .name .mono-name { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace; font-weight: 500; }
  .rrow .track { height: 12px; }
  .rrow .fill { height: 100%; border-radius: 2px; min-width: 2px; display: block; }
  .rrow.h .fill { background: var(--human); }
  .rrow.c .fill { background: var(--crawler); }
  .rrow .num {
    text-align: right; font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 12px; color: var(--ink); font-variant-numeric: tabular-nums;
  }
  .rrow .num small { color: var(--ink-soft); font-size: 10px; display: block; }
  .rrow .num small.you { color: var(--owner); }
  .rrow.more { border-bottom: none; }
  .rrow.more .name { color: var(--ink-soft); font-weight: 500; font-size: 12px; }
  .empty {
    padding: 14px 0; font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 11.5px; color: var(--ink-soft);
  }
  .depth { display: grid; grid-template-columns: 64px 1fr 64px; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .depth .lab { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace; font-size: 11px; color: var(--ink-soft); }
  .depth .track { height: 12px; }
  .depth .fill { height: 100%; background: var(--human); border-radius: 2px; display: block; }
  .depth .n { text-align: right; font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace; font-size: 12px; color: var(--ink); font-variant-numeric: tabular-nums; }
  .note {
    border: 1px solid var(--line); border-radius: 6px;
    background: var(--panel); padding: 18px 22px; margin-top: 26px; max-width: 72ch;
  }
  .note .k {
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--ink-soft); display: block; margin-bottom: 8px;
  }
  .note p { margin: 0 0 10px; }
  .note p:last-child { margin-bottom: 0; }
  .note b { color: var(--ink); }
  #tip {
    position: fixed; pointer-events: none; z-index: 10;
    background: var(--ink); color: var(--paper);
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 11px; line-height: 1.5; padding: 6px 10px; border-radius: 4px;
    opacity: 0; transition: opacity 120ms linear; white-space: pre-line; max-width: 320px;
  }
  @media (prefers-reduced-motion: reduce) { #tip { transition: none; } }
  /* Focus ring stays neutral ink. Accent colour never touches a stroke here. */
  [data-tip]:focus-visible { outline: 2px solid var(--line-strong); outline-offset: 2px; }
  footer {
    margin-top: 60px; border-top: 2px solid var(--line-strong); padding-top: 12px;
    font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
    font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-soft);
    display: flex; flex-wrap: wrap; gap: 6px 24px; justify-content: space-between;
  }
</style>
</head><body>
<div class="page">
  <div class="folio">
    <span><b>MindPattern</b> · Site analytics</span>
    <span>__TABS__</span>
    <span>First-party · no IP · no UA · no geo</span>
  </div>

  <h1 class="display" id="headline"></h1>
  <p class="dek" id="dek"></p>

  <div class="tiles" id="tiles"></div>

  <div class="note" id="countingNote">
    <span class="k">How a reader is counted, and why Vercel disagrees</span>
    <div id="countingBody"></div>
  </div>

  <section id="dailySection">
    <div class="kicker"><span>Daily traffic</span><span class="sub">— two populations, two scales, two charts</span></div>
    <div class="duo">
      <div>
        <div class="kicker" style="border-bottom:1px solid var(--line); margin-top:22px;">
          <span class="dot c"></span><span>Crawler hits / day</span><span class="sub" id="botPeak"></span>
        </div>
        <div class="cols" id="botCols"></div>
        <div class="xaxis" id="botAxis"></div>
      </div>
      <div>
        <div class="kicker" style="border-bottom:1px solid var(--line); margin-top:22px;">
          <span class="dot h"></span><span>Readers</span>
          <span class="dot o"></span><span>You</span>
          <span class="sub" id="humanPeak"></span>
        </div>
        <div class="cols" id="humanCols"></div>
        <div class="xaxis" id="humanAxis"></div>
      </div>
    </div>
  </section>

  <section>
    <div class="kicker"><span class="dot c"></span><span>Crawler leaderboard</span><span class="sub" id="botSub">— hits</span></div>
    <div class="ranked" id="botRank"></div>
  </section>

  <section>
    <div class="kicker"><span class="dot h"></span><span>Most-read stories</span><span class="sub">— views · unique readers</span></div>
    <div class="ranked" id="storyRank"></div>
  </section>

  <section>
    <div class="kicker"><span class="dot h"></span><span>What humans did</span><span class="sub">— event mix · reading depth</span></div>
    <div class="duo">
      <div><div class="ranked" id="mixRank"></div></div>
      <div>
        <div class="kicker" style="border-bottom:1px solid var(--line); margin-top:8px; margin-bottom:8px;">
          <span>Scroll depth reached</span><span class="sub" id="depthSub"></span>
        </div>
        <div id="depthRows"></div>
      </div>
    </div>
  </section>

  <section>
    <div class="kicker"><span class="dot h"></span><span>Where readers came from</span><span class="sub">— referrer domain · unique readers · how many were new · searches on site</span></div>
    <div class="duo">
      <div><div class="ranked" id="refRank"></div></div>
      <div><div class="ranked" id="searchRank"></div></div>
    </div>
    <div class="note" id="briefing" hidden>
      <span class="k">Briefing — computed from this window</span>
      <div id="briefingBody"></div>
    </div>
  </section>

  <footer>
    <span>Source: site_events.db on Fly (first-party event store)</span>
    <span>Queried __GENERATED__ · live on every load</span>
  </footer>
</div>

<div id="tip" role="status"></div>

<script>
  const DATA = __DATA__;

  const esc = (s) => String(s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");

  // Tooltip singleton
  const tip = document.getElementById("tip");
  function bindTips(root) {
    root.querySelectorAll("[data-tip]").forEach((el) => {
      el.setAttribute("tabindex", "0");
      const show = (x, y) => {
        tip.textContent = el.dataset.tip;
        tip.style.opacity = "1";
        const r = tip.getBoundingClientRect();
        tip.style.left = Math.min(x + 14, innerWidth - r.width - 8) + "px";
        tip.style.top = Math.min(y + 14, innerHeight - r.height - 8) + "px";
      };
      el.addEventListener("mousemove", (e) => show(e.clientX, e.clientY));
      el.addEventListener("mouseleave", () => (tip.style.opacity = "0"));
      el.addEventListener("focus", () => {
        const r = el.getBoundingClientRect();
        show(r.left, r.bottom);
      });
      el.addEventListener("blur", () => (tip.style.opacity = "0"));
    });
  }

  // Headline + dek
  const t = DATA.totals;
  const share = t.crawler_share;
  document.getElementById("headline").innerHTML =
    t.events === 0 ? 'Nothing yet — <span class="flood">quiet wire.</span>' :
    share >= 50 ? 'The bots found <span class="flood">it first.</span>' :
    'Humans are <span class="flood">reading it.</span>';
  const topBots = (DATA.agents.by_bot || []).slice(0, 2).map((b) => esc(b.target)).join(" and ");
  document.getElementById("dek").innerHTML =
    `<b>${fmt(t.events)} events</b> hit mindpattern.ai in the ${esc(DATA.window_label)}. ` +
    `<b>${share}%</b> were AI crawlers` +
    (topBots ? ` — led by ${topBots}` : "") +
    `. The human side: <b>${fmt(t.readers)} readers</b>` +
    (DATA.new_split ? `, <b>${fmt(t.new_readers)} of them new</b>` : "") + `, ` +
    `<b>${fmt(t.story_views)} story views</b>, ${fmt(t.reader_events)} reader events — ` +
    `plus <b>${fmt(t.owner_events)} of your own</b>, tracked but marked in gold. ` +
    `Live numbers, honestly reported.`;

  // Stat tiles
  document.getElementById("tiles").innerHTML = [
    ["", "Total events", fmt(t.events)],
    ["crawler", "Crawler hits", fmt(t.crawler_hits)],
    ["crawler", "Crawler share", `${share}<span class="unit">%</span>`],
    ["human", "Reader events", fmt(t.reader_events)],
    ["human", "Story views", fmt(t.story_views)],
    ["human", "Unique readers", fmt(t.readers)],
    ...(DATA.new_split
      ? [["human", "New readers", fmt(t.new_readers)],
         ["human", "Returning", fmt(t.returning_readers)]]
      : []),
    ["owner", "Your events", fmt(t.owner_events)],
  ].map(([cls, k, v]) =>
    `<div class="tile ${cls}"><div class="k">${k}</div><div class="v">${v}</div></div>`
  ).join("");

  // Counting note. Every claim here is one somebody can check in the code:
  // the reader predicate is the owner=0 filter on every query above, the
  // owner flag is isOwner() in src/lib/analytics.ts, and the id lifetime is
  // anonId() in the same file. Crawler filing is a definition, not a reason
  // the two totals differ: middleware.ts only POSTs an extra agent_hit row,
  // it suppresses nothing, and a crawler that runs no JS was never in either
  // number to begin with.
  document.getElementById("countingBody").innerHTML = [
    `A reader is one anonymous id that sent at least one non-crawler, non-owner event ` +
    `to this backend. Unique readers counts each id once inside the window. Requests ` +
    `from a known crawler user agent are filed separately and never counted as readers.`,
    DATA.new_split
      ? `<b>New</b> means that id sent nothing at all before <b>${esc(DATA.window_start)}</b>, ` +
        `the moment this window opens. <b>Returning</b> means it did. The two add up to ` +
        `unique readers. The id lives in the browser's local storage, so one person ` +
        `reading in a private window, on a second device, or after clearing site data ` +
        `arrives with a fresh id and counts as new again. ` +
        `A browser that blocks site storage outright ` +
        `gets a fresh id on <em>every</em> page load, so it reads as a new reader each time.`
      : `The all-time window reaches back further than the event store does, so nothing ` +
        `precedes it and the question has no answer. The new and returning split ` +
        `is shown on the today and 7d windows.`,
    `Vercel will report more visitors than this page does, and neither count is wrong. ` +
    `Browsing from this browser with <code>?mp_owner=1</code> set still sends events here, ` +
    `but they arrive tagged as yours and every reader number on this page excludes them. ` +
    `Vercel has no such flag and counts them as visitors. Beyond that, only events that ` +
    `reach this backend are counted, so a blocked beacon, a failed request, or a reader ` +
    `who leaves before it fires lands nowhere. Vercel counts anything that executes its ` +
    `script.`,
  ].filter(Boolean).map((l) => `<p>${l}</p>`).join("");

  // Daily columns. keys: single series, or [base, stackedOnTop] for the
  // reader+owner split — owner rides on top of the reader bar in gold.
  function columns(elId, axisId, keys, cls, tipLabels) {
    const el = document.getElementById(elId);
    const ax = document.getElementById(axisId);
    const totalOf = (r) => keys.reduce((a, k) => a + (r[k] || 0), 0);
    const max = Math.max(...DATA.daily.map(totalOf), 0);
    const peakIdx = DATA.daily.findIndex((r) => totalOf(r) === max);
    const showEvery = Math.ceil(DATA.daily.length / 10);
    DATA.daily.forEach((r, i) => {
      const n = totalOf(r);
      const c = document.createElement("div");
      c.className = "col " + cls;
      c.dataset.tip = `${r.d}\\n` +
        keys.map((k, j) => `${tipLabels[j]} ${fmt(r[k] || 0)}`).join("\\n") +
        (keys.includes("readers") ? `\\nstory views ${fmt(r.views)}` : "");
      const hTotal = max ? Math.round((n / max) * 118) : 0;
      let bars = "";
      if (keys.length === 1) {
        bars = `<div class="bar" style="height:${Math.max(hTotal, 2)}px"></div>`;
      } else {
        const hBase = max ? Math.round(((r[keys[0]] || 0) / max) * 118) : 0;
        const hTop = Math.max(hTotal - hBase, 0);
        bars =
          (hTop ? `<div class="bar owner" style="height:${hTop}px"></div>` : "") +
          `<div class="bar${hTop ? " under" : ""}" style="height:${Math.max(hBase, hTop ? 0 : 2)}px"></div>`;
      }
      c.innerHTML =
        (i === peakIdx && max > 0 ? `<span class="top" style="bottom:${hTotal + 6}px">${fmt(n)}</span>` : "") + bars;
      el.appendChild(c);
      const s = document.createElement("span");
      s.textContent = i % showEvery === 0 ? r.d.slice(5) : "";
      ax.appendChild(s);
    });
    bindTips(el);
    return max;
  }
  if (DATA.daily.length) {
    const botMax = columns("botCols", "botAxis", ["bots"], "crawler", ["crawler hits"]);
    const humanMax = columns("humanCols", "humanAxis", ["readers", "owner"], "human", ["readers", "you"]);
    document.getElementById("botPeak").textContent = `peak ${fmt(botMax)}`;
    document.getElementById("humanPeak").textContent = `peak ${fmt(humanMax)}`;
  } else {
    document.getElementById("dailySection").innerHTML =
      '<div class="empty">no events in this window</div>';
  }

  // Ranked bar lists
  function ranked(elId, rows, cls, opts = {}) {
    const el = document.getElementById(elId);
    if (!rows.length) {
      el.innerHTML = `<div class="empty">${opts.empty || "none in this window"}</div>`;
      return;
    }
    const max = Math.max(...rows.map((r) => r.n), 1);
    rows.forEach((r, i) => {
      const row = document.createElement("div");
      row.className = "rrow " + cls;
      const w = Math.max((r.n / max) * 100, 0.6);
      const readers = (r.readers != null && r.readers > 0 ? `<small>${fmt(r.readers)} rdr</small>` : "") +
        (r.note ? `<small>${esc(r.note)}</small>` : "") +
        (r.you ? `<small class="you">you ${fmt(r.you)}</small>` : "");
      let name = opts.mono ? `<span class="mono-name">${esc(r.name)}</span>` : esc(r.name);
      if (r.href) name = `<a href="${esc(r.href)}" target="_blank" rel="noopener">${name}</a>`;
      row.dataset.tip = `${r.name}\\n${fmt(r.n)} ${opts.unit || ""}`.trim() +
        (r.readers != null && r.readers > 0 ? ` · ${fmt(r.readers)} unique readers` : "") +
        (r.tip ? `\\n${r.tip}` : "") +
        (r.you ? ` · ${fmt(r.you)} by you` : "");
      row.innerHTML =
        `<span class="idx">${String(i + 1).padStart(2, "0")}</span>` +
        `<span class="name">${name}</span>` +
        `<span class="track"><span class="fill" style="width:${w}%"></span></span>` +
        `<span class="num">${fmt(r.n)}${readers}</span>`;
      el.appendChild(row);
    });
    if (opts.more) {
      const row = document.createElement("div");
      row.className = "rrow more " + cls;
      row.innerHTML = `<span class="idx">+${opts.moreCount}</span>` +
        `<span class="name" style="grid-column: 2 / -1">${esc(opts.more)}</span>`;
      el.appendChild(row);
    }
    bindTips(el);
  }

  const botsAll = DATA.agents.by_bot.map((b) => ({ name: b.target, n: b.hits }));
  const botsTop = botsAll.slice(0, 8);
  const botsRest = botsAll.slice(8);
  document.getElementById("botSub").textContent = `— hits, ${DATA.window_label}`;
  ranked("botRank", botsTop, "c", {
    unit: "hits", mono: true, empty: "no crawler hits in this window",
    more: botsRest.length
      ? botsRest.map((b) => b.name).join(" · ") + " — " +
        fmt(botsRest.reduce((a, b) => a + b.n, 0)) + " hits combined"
      : "",
    moreCount: botsRest.length,
  });

  ranked("storyRank",
    DATA.top_stories.slice(0, 12).map((s) => ({
      name: s.title || s.target, n: s.views, readers: s.readers, you: s.owner_views,
      href: "https://mindpattern.ai/s/" + encodeURIComponent(s.target),
    })),
    "h", { unit: "reader views", empty: "no story views in this window" });

  ranked("mixRank",
    DATA.mix.map((m) => ({ name: m.label, n: m.count, you: m.owner_count })),
    "h", { unit: "reader events", empty: "no human events in this window" });

  // Scroll depth
  const dEl = document.getElementById("depthRows");
  const depthTotal = DATA.scroll.reduce((a, r) => a + r.n, 0);
  document.getElementById("depthSub").textContent =
    depthTotal ? `of ${fmt(depthTotal)} depth pings` : "";
  if (!DATA.scroll.length) {
    dEl.innerHTML = '<div class="empty">no scroll tracking in this window</div>';
  } else {
    DATA.scroll.forEach((r) => {
      const row = document.createElement("div");
      row.className = "depth";
      row.dataset.tip = `${fmt(r.n)} reads reached ${r.value}% of the page`;
      row.innerHTML =
        `<span class="lab">≥ ${r.value}%</span>` +
        `<span class="track"><span class="fill" style="width:${(r.n / depthTotal) * 100}%"></span></span>` +
        `<span class="n">${fmt(r.n)}</span>`;
      dEl.appendChild(row);
    });
    bindTips(dEl);
  }

  ranked("refRank",
    DATA.referrers.map((r) => ({
      name: r.ref_domain, n: r.count,
      note: DATA.new_split ? `${fmt(r.new_count)} new` : "",
      tip: DATA.new_split
        ? `${fmt(r.new_count)} new · ${fmt(r.returning_count)} returning`
        : "",
    })),
    "h", {
      unit: "unique readers", mono: true,
      empty: "direct / no identified referrer readers in this window",
    });
  ranked("searchRank",
    DATA.search_terms.map((r) => ({ name: r.target, n: r.count, you: r.owner_count })),
    "h", { unit: "searches", mono: true, empty: "no searches in this window" });

  // Computed briefing: drill-through, subscribes — only when there is signal.
  const clickOf = (type) => (DATA.clicks.find((c) => c.type === type) || {}).count || 0;
  const lines = [];
  if (t.story_views > 0) {
    const related = clickOf("related_click");
    lines.push(`<b>${Math.round((related / t.story_views) * 100)}% drill-through</b> — ` +
      `${fmt(related)} related-story clicks against ${fmt(t.story_views)} views.`);
  }
  const sub = DATA.subscribe;
  lines.push(sub.submitted
    ? `Subscribes: <b>${fmt(sub.success)} confirmed</b> of ${fmt(sub.submitted)} submitted` +
      (sub.conversion != null ? ` (${Math.round(sub.conversion * 100)}%).` : ".")
    : "No subscribes in this window yet.");
  const outbound = clickOf("outbound_source_click");
  if (outbound) lines.push(`${fmt(outbound)} outbound source clicks — readers following the wire to primary sources.`);
  if (lines.length) {
    document.getElementById("briefing").hidden = false;
    document.getElementById("briefingBody").innerHTML =
      lines.map((l) => `<p>${l}</p>`).join("");
  }
</script>
</body></html>"""


@router.get("/site-analytics", response_class=HTMLResponse)
async def site_analytics_page(request: Request, window: str = Query("7d")):
    """Private: the live editorial dashboard — fresh queries on every load."""
    if window not in _WINDOWS:
        window = "7d"
    data = await _summary_with_titles(window)
    token = request.query_params.get("token", "")
    token_qs = f"&token={token}" if token else ""
    active = ' class="active"'
    tabs = " · ".join(
        f'<a href="/site-analytics?window={w}{token_qs}"'
        f'{active if w == window else ""}>{w}</a>'
        for w in _WINDOWS
    )
    generated = time.strftime("%d %b %Y %H:%M UTC", time.gmtime())
    payload = json.dumps(data).replace("<", "\\u003c")
    html = (
        _PAGE
        .replace("__TABS__", tabs)
        .replace("__GENERATED__", generated)
        .replace("__DATA__", payload)
    )
    return HTMLResponse(html)
