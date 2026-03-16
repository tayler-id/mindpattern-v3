"""Generate Obsidian markdown mirror files from SQLite data.

Reads from the memory database (findings, social_posts, editorial_corrections,
engagements) and renders Jinja2 templates into the Obsidian vault. All writes
go through vault.atomic_write() so Obsidian never sees partial files.

Main entry point: generate_mirrors(db, vault_dir, date_str)
"""

import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from memory.vault import archive_old_entries, atomic_write

# ── Helpers ─────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _slugify(text: str) -> str:
    """Convert a string to a filesystem-safe slug.

    Lower-cases, replaces non-alphanumeric characters with hyphens, and
    collapses multiple hyphens into one.
    """
    slug = text.lower()
    # Strip apostrophes so "what's" -> "whats" (not "what-s")
    slug = slug.replace("'", "").replace("\u2019", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _topic_from_agent(agent: str) -> str:
    """Extract topic name from an agent name.

    Strips the trailing '-researcher' or similar suffix.
    E.g. 'security-researcher' -> 'security',
         'general-news-researcher' -> 'general-news',
         'news' -> 'news'.
    """
    suffixes = ["-researcher", "-agent", "-scraper", "-analyst"]
    name = agent
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _domain_from_url(url: str | None) -> str | None:
    """Extract domain from a URL, or None if missing/invalid."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


# ── Template environment ────────────────────────────────────────────────────


def _get_env() -> Environment:
    """Create Jinja2 environment with FileSystemLoader for templates."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ── Data queries ────────────────────────────────────────────────────────────


def _query_findings(db: sqlite3.Connection, date_str: str) -> list[dict]:
    """Fetch all findings for a given date."""
    rows = db.execute(
        "SELECT * FROM findings WHERE run_date = ? ORDER BY importance DESC, id",
        (date_str,),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_all_findings_for_agent(db: sqlite3.Connection, agent: str) -> list[dict]:
    """Fetch all findings ever recorded for an agent."""
    rows = db.execute(
        "SELECT * FROM findings WHERE agent = ? ORDER BY run_date DESC, id",
        (agent,),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_findings_for_source_domain(
    db: sqlite3.Connection, domain: str
) -> list[dict]:
    """Fetch findings whose source_url contains a given domain."""
    pattern = f"%{domain}%"
    rows = db.execute(
        "SELECT * FROM findings WHERE source_url LIKE ? ORDER BY run_date DESC, id",
        (pattern,),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_social_posts(db: sqlite3.Connection, date_str: str) -> list[dict]:
    """Fetch social posts for a given date."""
    rows = db.execute(
        "SELECT * FROM social_posts WHERE date = ? ORDER BY id",
        (date_str,),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_all_social_posts(db: sqlite3.Connection) -> list[dict]:
    """Fetch all social posts."""
    rows = db.execute(
        "SELECT * FROM social_posts ORDER BY date DESC, id"
    ).fetchall()
    return [dict(r) for r in rows]


def _query_corrections(db: sqlite3.Connection) -> list[dict]:
    """Fetch all editorial corrections."""
    rows = db.execute(
        "SELECT * FROM editorial_corrections ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def _query_engagements(db: sqlite3.Connection, date_str: str) -> list[dict]:
    """Fetch engagements whose created_at starts with date_str."""
    pattern = f"{date_str}%"
    rows = db.execute(
        "SELECT * FROM engagements WHERE created_at LIKE ? ORDER BY created_at",
        (pattern,),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_all_engagements(db: sqlite3.Connection) -> list[dict]:
    """Fetch all engagements."""
    rows = db.execute(
        "SELECT * FROM engagements ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ── Data transformation ─────────────────────────────────────────────────────


def _build_agents_data(findings: list[dict]) -> list[dict]:
    """Group findings by agent and attach topic/source slugs."""
    agents: dict[str, list[dict]] = {}
    for f in findings:
        agent = f["agent"]
        agents.setdefault(agent, [])
        topic = _topic_from_agent(agent)
        domain = _domain_from_url(f.get("source_url"))
        agents[agent].append(
            {
                "title": f["title"],
                "importance": f.get("importance", "medium"),
                "summary": f.get("summary", ""),
                "topic_slug": _slugify(topic),
                "source_slug": _slugify(domain) if domain else "unknown",
                "run_date": f["run_date"],
            }
        )

    return [
        {"name": agent_name, "findings": agent_findings}
        for agent_name, agent_findings in sorted(agents.items())
    ]


def _build_posts_data(posts: list[dict]) -> list[dict]:
    """Transform social_posts rows for templates."""
    result = []
    for p in posts:
        result.append(
            {
                "date": p["date"],
                "platform": p["platform"],
                "content": p["content"],
                "gate1_outcome": p.get("anchor_text", "n/a"),
                "gate2_outcome": p.get("gate2_action", "n/a"),
                "gate_outcome": p.get("gate2_action", "n/a"),
                "posted": bool(p.get("posted", 0)),
            }
        )
    return result


def _build_corrections_data(corrections: list[dict]) -> list[dict]:
    """Transform editorial_corrections rows for templates."""
    result = []
    for c in corrections:
        # Extract date from created_at (YYYY-MM-DD HH:MM:SS -> YYYY-MM-DD)
        created = c.get("created_at", "")
        date_part = created[:10] if created else None
        result.append(
            {
                "date": date_part,
                "platform": c["platform"],
                "original_text": c["original_text"],
                "approved_text": c["approved_text"],
                "reason": c.get("reason"),
            }
        )
    return result


def _build_engagement_replies(engagements: list[dict]) -> list[dict]:
    """Extract reply-type engagements."""
    replies = []
    for e in engagements:
        if e.get("engagement_type") == "reply":
            created = e.get("created_at", "")
            date_part = created[:10] if created else ""
            replies.append(
                {
                    "platform": e["platform"],
                    "date": date_part,
                    "target_author": e.get("target_author"),
                    "target_content": e.get("target_content") or "",
                    "our_reply": e.get("our_reply") or "",
                    "status": e.get("status", "unknown"),
                }
            )
    return replies


def _build_engagement_follows(engagements: list[dict]) -> list[dict]:
    """Extract follow-type engagements."""
    follows = []
    for e in engagements:
        if e.get("engagement_type") == "follow":
            created = e.get("created_at", "")
            date_part = created[:10] if created else ""
            follows.append(
                {
                    "platform": e["platform"],
                    "date": date_part,
                    "target_author": e.get("target_author"),
                }
            )
    return follows


def _build_engaged_authors_data(engagements: list[dict]) -> list[dict]:
    """Group engagements by platform and author for the engaged-authors template."""
    platforms: dict[str, dict[str, dict]] = {}

    for e in engagements:
        platform = e["platform"]
        author = e.get("target_author") or "unknown"
        author_id = e.get("target_author_id")
        created = e.get("created_at", "")
        date_part = created[:10] if created else ""

        platforms.setdefault(platform, {})
        if author not in platforms[platform]:
            platforms[platform][author] = {
                "name": author,
                "id": author_id,
                "interaction_count": 0,
                "first_seen": date_part,
                "last_seen": date_part,
                "interactions": [],
            }

        author_data = platforms[platform][author]
        author_data["interaction_count"] += 1
        if date_part and date_part < author_data["first_seen"]:
            author_data["first_seen"] = date_part
        if date_part and date_part > author_data["last_seen"]:
            author_data["last_seen"] = date_part

        author_data["interactions"].append(
            {
                "date": date_part,
                "type": e.get("engagement_type", "reply"),
                "content": e.get("our_reply") or e.get("target_content") or "",
            }
        )

    result = []
    for platform_name in sorted(platforms.keys()):
        authors = list(platforms[platform_name].values())
        authors.sort(key=lambda a: a["interaction_count"], reverse=True)
        result.append({"name": platform_name, "authors": authors})
    return result


def _collect_topic_data(
    db: sqlite3.Connection, agent: str, all_findings: list[dict], posts: list[dict]
) -> dict:
    """Build the context dict for a single topic template."""
    topic_name = _topic_from_agent(agent)
    topic_slug = _slugify(topic_name)

    # All findings for this agent (across all dates)
    topic_findings = _query_all_findings_for_agent(db, agent)

    # Build findings with run_date for template
    tpl_findings = []
    for f in topic_findings:
        tpl_findings.append(
            {
                "title": f["title"],
                "importance": f.get("importance", "medium"),
                "summary": f.get("summary", ""),
                "run_date": f["run_date"],
            }
        )

    # Sources used in this topic
    source_counts: dict[str, int] = {}
    for f in topic_findings:
        domain = _domain_from_url(f.get("source_url"))
        if domain:
            source_counts[domain] = source_counts.get(domain, 0) + 1
    tpl_sources = [
        {"slug": _slugify(domain), "count": count}
        for domain, count in sorted(source_counts.items(), key=lambda x: -x[1])
    ]

    # First seen date
    first_seen = ""
    if topic_findings:
        first_seen = min(f["run_date"] for f in topic_findings)

    # Posts that mention this topic (check anchor_text)
    topic_posts = []
    for p in posts:
        # Simple heuristic: include posts from agents of this topic
        topic_posts.append(
            {
                "platform": p["platform"],
                "date": p["date"],
                "content": p["content"],
            }
        )

    return {
        "name": topic_name.replace("-", " ").title(),
        "slug": topic_slug,
        "description": f"Research findings from the {topic_name} research agent.",
        "findings": tpl_findings,
        "sources": tpl_sources,
        "first_seen": first_seen,
        "related_topics": [],  # Could be expanded with cross-topic analysis
        "posts": topic_posts,
        "tags": [topic_name, "research"],
    }


def _collect_source_data(
    db: sqlite3.Connection, domain: str, source_name: str | None
) -> dict:
    """Build context dict for a single source template."""
    findings = _query_findings_for_source_domain(db, domain)

    tpl_findings = []
    for f in findings:
        tpl_findings.append(
            {
                "title": f["title"],
                "importance": f.get("importance", "medium"),
                "summary": f.get("summary", ""),
                "run_date": f["run_date"],
            }
        )

    # Topics covered by findings from this source
    topic_counts: dict[str, int] = {}
    for f in findings:
        topic = _topic_from_agent(f["agent"])
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
    tpl_topics = [
        {"slug": _slugify(t), "count": c}
        for t, c in sorted(topic_counts.items(), key=lambda x: -x[1])
    ]

    # Recent findings (last 10)
    recent = tpl_findings[:10]

    return {
        "name": source_name or domain,
        "url": f"https://{domain}",
        "slug": _slugify(domain),
        "findings": tpl_findings,
        "topics": tpl_topics,
        "recent_findings": recent,
        "tags": ["source", _slugify(domain)],
    }


# ── Index builder ───────────────────────────────────────────────────────────


def _write_index(
    env: Environment,
    vault_dir: Path,
    folder: str,
    title: str,
    date_str: str,
    description: str = "",
) -> None:
    """Write _index.md for a subfolder, linking to all .md files in it."""
    folder_path = vault_dir / folder
    folder_path.mkdir(parents=True, exist_ok=True)

    files = []
    for md_file in sorted(folder_path.glob("*.md")):
        if md_file.name == "_index.md":
            continue
        files.append(
            {
                "slug": md_file.stem,
                "name": md_file.stem.replace("-", " ").title(),
            }
        )

    template = env.get_template("index.md.j2")
    content = template.render(
        title=title,
        description=description,
        date=date_str,
        tags=["index", folder],
        folder=folder,
        files=files,
    )
    atomic_write(folder_path / "_index.md", content)


# ── Main entry point ────────────────────────────────────────────────────────


def generate_mirrors(
    db: sqlite3.Connection,
    vault_dir: Path,
    date_str: str,
) -> None:
    """Generate Obsidian mirror files from SQLite data.

    Loads Jinja2 templates, queries the database for findings/posts/corrections/
    engagements, renders templates, and writes atomically via vault.atomic_write().

    Args:
        db: Open sqlite3.Connection with row_factory=sqlite3.Row.
        vault_dir: Root of the Obsidian vault (e.g. data/ramsay/mindpattern/).
        date_str: Date string like "2026-03-15".
    """
    vault_dir = Path(vault_dir)
    env = _get_env()

    # ── Query data ────────────────────────────────────────────────────────
    findings = _query_findings(db, date_str)
    all_posts = _query_all_social_posts(db)
    today_posts = _query_social_posts(db, date_str)
    corrections = _query_corrections(db)
    today_engagements = _query_engagements(db, date_str)
    all_engagements = _query_all_engagements(db)

    # ── Transform data ────────────────────────────────────────────────────
    agents_data = _build_agents_data(findings)
    posts_data = _build_posts_data(all_posts)
    today_posts_data = _build_posts_data(today_posts)
    corrections_data = _build_corrections_data(corrections)
    replies = _build_engagement_replies(all_engagements)
    follows = _build_engagement_follows(all_engagements)
    today_engagements_data = []
    for e in today_engagements:
        created = e.get("created_at", "")
        date_part = created[:10] if created else ""
        today_engagements_data.append(
            {
                "platform": e["platform"],
                "type": e.get("engagement_type", "reply"),
                "target_author": e.get("target_author"),
                "date": date_part,
            }
        )
    authors_data = _build_engaged_authors_data(all_engagements)

    # ── Collect tags ──────────────────────────────────────────────────────
    topic_names = list({_topic_from_agent(f["agent"]) for f in findings})

    # ── Render: daily (all dates with findings, not just today) ──────────
    all_dates = db.execute(
        "SELECT DISTINCT run_date FROM findings ORDER BY run_date"
    ).fetchall()
    daily_tpl = env.get_template("daily.md.j2")

    for date_row in all_dates:
        d = date_row[0] if not hasattr(date_row, "keys") else date_row["run_date"]
        if not d:
            continue

        day_findings = _query_findings(db, d)
        day_posts = _query_social_posts(db, d)
        day_engagements = _query_engagements(db, d)

        day_agents = _build_agents_data(day_findings)
        day_posts_data = _build_posts_data(day_posts)
        day_topic_names = list({_topic_from_agent(f["agent"]) for f in day_findings})

        day_eng_data = []
        for e in day_engagements:
            created = e.get("created_at", "")
            dp = created[:10] if created else ""
            day_eng_data.append({
                "platform": e["platform"],
                "type": e.get("engagement_type", "reply"),
                "target_author": e.get("target_author"),
                "date": dp,
            })

        daily_content = daily_tpl.render(
            date=d,
            tags=["daily"] + day_topic_names,
            agents=day_agents,
            findings=day_findings,
            posts=day_posts_data,
            engagements=day_eng_data,
            evolution_actions=[],
        )
        atomic_write(vault_dir / "daily" / f"{d}.md", daily_content)

    # ── Render: topics ────────────────────────────────────────────────────
    seen_agents = {f["agent"] for f in findings}
    for agent in seen_agents:
        topic_data = _collect_topic_data(db, agent, findings, today_posts)
        topic_tpl = env.get_template("topic.md.j2")
        topic_content = topic_tpl.render(
            date=date_str,
            **topic_data,
        )
        slug = topic_data["slug"]
        atomic_write(vault_dir / "topics" / f"{slug}.md", topic_content)

    # ── Render: sources ───────────────────────────────────────────────────
    # Collect unique source domains from findings
    source_domains: dict[str, str | None] = {}
    for f in findings:
        domain = _domain_from_url(f.get("source_url"))
        if domain:
            source_domains.setdefault(domain, f.get("source_name"))

    for domain, source_name in source_domains.items():
        source_data = _collect_source_data(db, domain, source_name)
        source_tpl = env.get_template("source.md.j2")
        source_content = source_tpl.render(
            date=date_str,
            eic_selection_rate=0.0,
            **source_data,
        )
        slug = _slugify(domain)
        atomic_write(vault_dir / "sources" / f"{slug}.md", source_content)

    # ── Render: social/posts.md ───────────────────────────────────────────
    posts_tpl = env.get_template("posts.md.j2")
    posts_content = posts_tpl.render(
        date=date_str,
        tags=["social", "posts"],
        posts=posts_data,
    )
    atomic_write(vault_dir / "social" / "posts.md", posts_content)

    # ── Render: social/corrections.md ─────────────────────────────────────
    corrections_tpl = env.get_template("corrections.md.j2")
    corrections_content = corrections_tpl.render(
        date=date_str,
        tags=["social", "corrections"],
        corrections=corrections_data,
    )
    atomic_write(vault_dir / "social" / "corrections.md", corrections_content)

    # ── Render: social/engagement-log.md ──────────────────────────────────
    engagement_tpl = env.get_template("engagement-log.md.j2")
    engagement_content = engagement_tpl.render(
        date=date_str,
        tags=["social", "engagement"],
        replies=replies,
        follows=follows,
        outcomes=[],
    )
    atomic_write(vault_dir / "social" / "engagement-log.md", engagement_content)

    # ── Render: people/engaged-authors.md ─────────────────────────────────
    authors_tpl = env.get_template("engaged-authors.md.j2")
    authors_content = authors_tpl.render(
        date=date_str,
        tags=["people", "engagement"],
        platforms=authors_data,
    )
    atomic_write(vault_dir / "people" / "engaged-authors.md", authors_content)

    # ── Write index files ─────────────────────────────────────────────────
    _write_index(env, vault_dir, "daily", "Daily Logs", date_str, "Daily activity and research logs.")
    _write_index(env, vault_dir, "topics", "Topics", date_str, "Research topics tracked by agent.")
    _write_index(env, vault_dir, "sources", "Sources", date_str, "Information sources and their finding history.")
    _write_index(env, vault_dir, "social", "Social", date_str, "Social media posts, corrections, and engagement logs.")
    _write_index(env, vault_dir, "people", "People", date_str, "People and authors we engage with.")

    # ── Mirror: newsletters ──────────────────────────────────────────────
    _mirror_newsletters(vault_dir, date_str)

    # ── Render: social/feedback.md (Gate 2 outcomes) ─────────────────────
    _mirror_feedback(db, vault_dir, date_str, env)

    # ── Write newsletter index ─────────────────────────────────────────
    _write_index(env, vault_dir, "newsletters", "Newsletters", date_str, "Daily research newsletters sent via email.")

    # ── Archival: decisions.md ────────────────────────────────────────────
    decisions_path = vault_dir / "decisions.md"
    archive_path = vault_dir / "decisions-archive.md"
    if decisions_path.exists():
        archive_old_entries(decisions_path, archive_path, max_age_days=90)


def _mirror_newsletters(vault_dir: Path, date_str: str) -> None:
    """Copy newsletter .md files from reports/ramsay/ into the vault.

    Each newsletter gets YAML frontmatter added and wiki-links to the
    matching daily log.
    """
    project_root = vault_dir.parent.parent.parent  # data/ramsay/mindpattern -> project root
    reports_dir = project_root / "reports" / "ramsay"

    if not reports_dir.exists():
        return

    newsletters_dir = vault_dir / "newsletters"
    newsletters_dir.mkdir(parents=True, exist_ok=True)

    for report_file in sorted(reports_dir.glob("*.md")):
        # Skip non-date files
        name = report_file.stem
        if not (len(name) >= 10 and name[:4].isdigit()):
            continue

        content = report_file.read_text(encoding="utf-8")

        # Add frontmatter if not present
        if not content.startswith("---"):
            date_part = name[:10]
            frontmatter = (
                f"---\n"
                f"type: newsletter\n"
                f"date: {date_part}\n"
                f"tags:\n"
                f"  - newsletter\n"
                f"---\n\n"
                f"See also: [[daily/{date_part}|Daily Log]]\n\n"
            )
            content = frontmatter + content

        atomic_write(newsletters_dir / f"{name}.md", content)


def _mirror_feedback(
    db: sqlite3.Connection,
    vault_dir: Path,
    date_str: str,
    env: Environment,
) -> None:
    """Generate social/feedback.md from social_feedback table.

    Shows Gate 2 outcomes: which posts were approved/rejected/edited,
    by platform and date.
    """
    rows = db.execute(
        """
        SELECT date, platform, action, edit_type, user_feedback
        FROM social_feedback
        ORDER BY date DESC
        """
    ).fetchall()

    entries = []
    for r in rows:
        entries.append({
            "date": r["date"] if hasattr(r, "keys") else r[0],
            "platform": r["platform"] if hasattr(r, "keys") else r[1],
            "action": r["action"] if hasattr(r, "keys") else r[2],
            "edit_type": r["edit_type"] if hasattr(r, "keys") else r[3],
            "feedback": (r["user_feedback"] if hasattr(r, "keys") else r[4]) or "",
        })

    content = (
        "---\n"
        "type: social\n"
        f"date: {date_str}\n"
        "tags:\n"
        "  - social\n"
        "  - feedback\n"
        "---\n\n"
        "# Gate 2 Feedback Log\n\n"
        "Editorial feedback from Gate 2 approvals. Shows which posts were "
        "approved, rejected, or edited.\n\n"
    )

    if not entries:
        content += "*No feedback recorded yet.*\n"
    else:
        # Summary stats
        approved = sum(1 for e in entries if e["action"] == "approved")
        skipped = sum(1 for e in entries if e["action"] == "skip")
        total = len(entries)
        content += (
            f"**Total**: {total} decisions | "
            f"**Approved**: {approved} | "
            f"**Skipped**: {skipped}\n\n"
        )

        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for e in entries:
            by_date[e["date"]].append(e)

        for date in sorted(by_date.keys(), reverse=True)[:30]:
            content += f"## {date}\n\n"
            for e in by_date[date]:
                status = "approved" if e["action"] == "approved" else e["action"]
                edit = f" ({e['edit_type']})" if e["edit_type"] and e["edit_type"] != "none" else ""
                content += f"- **{e['platform']}**: {status}{edit}"
                if e["feedback"]:
                    content += f" — {e['feedback']}"
                content += f" → [[daily/{date}|Daily Log]]\n"
            content += "\n"

    atomic_write(vault_dir / "social" / "feedback.md", content)
