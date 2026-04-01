"""Research finding storage, semantic search, context generation, and quality evaluation.

Refactored from v2's memory.py (3,800-line CLI monolith) into a pure Python module.
All functions take a `db` (sqlite3.Connection) parameter and return data structures.
No argparse, no print statements, no CLI.

Dependencies:
    embeddings.py: embed_text, embed_texts, serialize_f32, deserialize_f32,
                   cosine_similarity, batch_similarities
    db.py: get_db, open_db
"""

import json
import logging
import re
import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from .embeddings import (
    batch_similarities,
    cosine_similarity,
    deserialize_f32,
    embed_text,
    embed_texts,
    serialize_f32,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

CANONICAL_DOMAINS = [
    "vibe-coding",
    "prompt-engineering",
    "agent-patterns",
    "ai-productivity",
    "ml-ops",
    "agent-security",
]

SECTION_AGENT_MAP = {
    "breaking news & industry": "news-researcher",
    "breaking news": "news-researcher",
    "vibe coding & ai development": "vibe-coding-researcher",
    "vibe coding": "vibe-coding-researcher",
    "what leaders are saying": "thought-leaders-researcher",
    "thought leaders": "thought-leaders-researcher",
    "ai agent ecosystem": "agents-researcher",
    "agent ecosystem": "agents-researcher",
    "hot projects & repos": "projects-researcher",
    "hot projects": "projects-researcher",
    "best content this week": "sources-researcher",
    "best content": "sources-researcher",
}

SKILL_DOMAIN_KEYWORDS = {
    "vibe-coding": [
        "claude code", "cursor", "windsurf", "copilot", "claude.md",
        "hooks", "worktree", "context engineering", "mcp server",
        "coding agent", "code generation", "vibe coding", "vibe-coding",
        "forked context", "skills file", "context window",
    ],
    "prompt-engineering": [
        "prompt", "chain-of-thought", "few-shot", "system prompt",
        "meta-prompt", "self-consistency", "cot", "metaprompt",
        "prompting", "instruction tuning", "zero-shot",
    ],
    "agent-patterns": [
        "multi-agent", "orchestrat", "memory architect", "tool use",
        "human-in-the-loop", "agent pattern", "observational memory",
        "agent framework", "mastra", "langgraph", "crewai",
        "plan-and-execute", "reflection",
    ],
    "ai-productivity": [
        "voice coding", "ci/cd", "code review", "automated test",
        "workflow", "productivity", "wispr", "playwright agent",
        "security review", "devops",
    ],
    "ml-ops": [
        "fine-tun", "dpo", "rlhf", "grpo", "rag", "graphrag",
        "embedding", "deploy", "evaluation", "distillat",
        "model serving", "inference", "training pipeline",
    ],
    "agent-security": [
        "security", "sandbox", "injection", "jailbreak", "audit",
        "owasp", "mcp security", "credential", "identity",
        "access control", "defense-in-depth", "vulnerability",
    ],
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Helpers (internal) ─────────────────────────────────────────────────────


def _validate_date(date_str: str) -> str:
    """Validate and return a YYYY-MM-DD date string. Raises ValueError on bad format."""
    if not _DATE_RE.match(date_str):
        raise ValueError(f"Invalid date format '{date_str}' (expected YYYY-MM-DD)")
    # Also validate it parses as a real date
    datetime.strptime(date_str, "%Y-%m-%d")
    return date_str


def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    """Return current datetime as ISO 8601 string."""
    return datetime.now().isoformat()


def _normalize_domain(raw: str, canonical_domains: list[str] | None = None) -> str:
    """Normalize a domain string to its canonical form.

    Args:
        raw: Raw domain string (e.g. "Vibe Coding", "agent_patterns").
        canonical_domains: Override list of canonical domain names.

    Returns:
        Lowercased, hyphenated canonical domain name.
        Logs a warning if not in the canonical list.
    """
    domains = canonical_domains or CANONICAL_DOMAINS
    normalized = raw.strip().lower().replace(" ", "-").replace("_", "-")
    if normalized not in domains:
        logger.warning(
            "Domain '%s' is not canonical (%s)", raw, ", ".join(domains)
        )
    return normalized


def _normalize_title(raw: str) -> str:
    """Normalize a skill title for dedup comparison."""
    t = raw.strip().strip("*")
    t = re.sub(r"^\d+\.\s*", "", t)
    t = re.sub(r"\s*\(.*?\)\s*$", "", t)
    return t.strip().lower()


def _titles_match(a: str, b: str) -> bool:
    """Fuzzy title matching for dedup between backfilled and LLM-stored skills.

    Returns True if:
    - Normalized titles are identical, OR
    - All significant words (3+ chars) from the shorter title appear in the longer one.
    """
    na, nb = _normalize_title(a), _normalize_title(b)
    if na == nb:
        return True
    words_a = set(w for w in na.split() if len(w) >= 3)
    words_b = set(w for w in nb.split() if len(w) >= 3)
    if not words_a or not words_b:
        return na == nb
    shorter, longer = (words_a, words_b) if len(words_a) <= len(words_b) else (words_b, words_a)
    return shorter.issubset(longer)


def _infer_domain(
    title: str,
    description: str,
    skill_domain_keywords: dict[str, list[str]] | None = None,
) -> str:
    """Infer the skill domain from title and description using keyword matching.

    Returns:
        Best-matching canonical domain, or "general" if no keywords match.
    """
    keywords_map = skill_domain_keywords or SKILL_DOMAIN_KEYWORDS
    text = f"{title} {description}".lower()
    scores = {}
    for domain, keywords in keywords_map.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score

    if not scores:
        return "general"

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best_domain, best_score = ranked[0]

    if len(ranked) >= 2:
        second_score = ranked[1][1]
        if best_score > 0 and second_score / best_score >= 0.8:
            logger.warning(
                "Ambiguous domain for '%s': %s=%d vs %s=%d",
                title[:60], ranked[0][0], best_score, ranked[1][0], second_score,
            )

    return best_domain


def _parse_report(
    content: str,
    date: str,
    section_agent_map: dict[str, str] | None = None,
) -> list[dict]:
    """Parse a newsletter report into individual findings.

    Args:
        content: Full markdown report text.
        date: Run date (YYYY-MM-DD).
        section_agent_map: Override mapping from section titles to agent names.

    Returns:
        List of finding dicts with keys: date, agent, title, summary,
        importance, source_url, source_name.
    """
    agent_map = section_agent_map or SECTION_AGENT_MAP
    findings = []
    lines = content.split("\n")
    current_agent = None
    current_finding = None

    for line in lines:
        stripped = line.strip()

        # Detect ## section headers
        if stripped.startswith("## ") and not stripped.startswith("### "):
            # Save previous finding
            if current_finding and current_finding["summary"]:
                findings.append(current_finding)
                current_finding = None

            section_title = stripped[3:].strip().lower()

            # Skip non-content sections
            if any(
                skip in section_title
                for skip in ["top 5", "source index", "meta:", "research quality"]
            ):
                current_agent = None
                continue

            current_agent = None
            for key, agent in agent_map.items():
                if key in section_title:
                    current_agent = agent
                    break

        # Detect ### finding headers within a mapped section
        elif stripped.startswith("### ") and current_agent:
            if current_finding and current_finding["summary"]:
                findings.append(current_finding)

            title = stripped[4:].strip()
            current_finding = {
                "date": date,
                "agent": current_agent,
                "title": title,
                "summary": "",
                "importance": "medium",
                "source_url": None,
                "source_name": None,
            }

        # Parse metadata and content within a finding
        elif current_finding:
            if stripped.startswith("- **Source**"):
                url_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", stripped)
                if url_match:
                    current_finding["source_name"] = url_match.group(1)
                    current_finding["source_url"] = url_match.group(2)
            elif stripped.startswith("- **Date**"):
                pass  # Already have date from filename
            elif stripped == "---":
                if current_finding and current_finding["summary"]:
                    findings.append(current_finding)
                current_finding = None
            elif stripped and not stripped.startswith("- **"):
                # Summary paragraph
                if current_finding["summary"]:
                    current_finding["summary"] += " " + stripped
                else:
                    current_finding["summary"] = stripped

    # Save last finding
    if current_finding and current_finding["summary"]:
        findings.append(current_finding)

    # Assign importance: first findings per agent are typically most important
    agent_counts: dict[str, int] = {}
    for f in findings:
        agent = f["agent"]
        agent_counts[agent] = agent_counts.get(agent, 0) + 1
        if agent_counts[agent] <= 2:
            f["importance"] = "high"
        elif agent_counts[agent] <= 5:
            f["importance"] = "medium"
        else:
            f["importance"] = "low"

    return findings


def _parse_skills_from_report(
    content: str,
    date: str,
    skill_domain_keywords: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Parse the skills section from a newsletter report.

    Args:
        content: Full markdown report text.
        date: Run date (YYYY-MM-DD).
        skill_domain_keywords: Override keyword mapping for domain inference.

    Returns:
        List of skill dicts with keys: title, description, domain, difficulty,
        date, backfilled, steps, source_url, source_name.
    """
    skills = []
    lines = content.split("\n")

    # Find the skills section header (case-insensitive)
    skill_section_start = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+.*[Ss]kill", line.strip()):
            skill_section_start = i
            break

    if skill_section_start is None:
        return skills

    # Parse skills: **N. Title** + paragraph(s)
    current_skill = None
    for line in lines[skill_section_start + 1 :]:
        stripped = line.strip()

        # Stop at next ## section or ---
        if stripped.startswith("## ") or stripped == "---":
            if current_skill and current_skill["description"]:
                skills.append(current_skill)
            current_skill = None
            break

        # Detect **N. Title** pattern
        m = re.match(r"^\*\*(\d+)\.\s+(.+?)\*\*$", stripped)
        if m:
            if current_skill and current_skill["description"]:
                skills.append(current_skill)
            title = m.group(2).strip()
            current_skill = {
                "title": title,
                "description": "",
                "domain": None,
                "difficulty": "intermediate",
                "date": date,
                "backfilled": 1,
                "steps": None,
                "source_url": None,
                "source_name": None,
            }
            continue

        # Accumulate description paragraphs
        if current_skill and stripped:
            if current_skill["description"]:
                current_skill["description"] += " " + stripped
            else:
                current_skill["description"] = stripped

    # Capture last skill if we hit end of content
    if current_skill and current_skill["description"]:
        skills.append(current_skill)

    # Infer domains
    for skill in skills:
        skill["domain"] = _infer_domain(
            skill["title"], skill["description"], skill_domain_keywords
        )

    return skills


def _parse_patterns(content: str) -> list[dict]:
    """Parse patterns from learnings.md.

    Args:
        content: Full learnings.md text.

    Returns:
        List of pattern dicts with keys: date, theme, description.
    """
    patterns = []
    lines = content.split("\n")
    current_date = None
    in_patterns = False

    for line in lines:
        stripped = line.strip()

        # Detect run date sections
        date_match = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})\s+Run Notes", stripped)
        if date_match:
            current_date = date_match.group(1)
            in_patterns = False
            continue

        # Detect patterns subsection
        if stripped == "### Patterns Observed" or stripped.startswith("### Patterns"):
            in_patterns = True
            continue

        # Exit patterns on next ### section
        if stripped.startswith("### ") and in_patterns:
            in_patterns = False
            continue

        # Skip sub-headers within patterns (e.g., "**Industry Trends:**")
        if in_patterns and stripped.startswith("**") and stripped.endswith(":**"):
            continue

        # Parse pattern entries
        if in_patterns and current_date and stripped:
            # Numbered: "1. **Theme** — Description"
            m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*\s*[—–\-]\s*(.+)", stripped)
            if m:
                patterns.append(
                    {
                        "date": current_date,
                        "theme": m.group(1).strip(),
                        "description": m.group(2).strip(),
                    }
                )
                continue

            # Dashed bold: "- **Theme** — Description"
            m = re.match(r"^-\s+\*\*(.+?)\*\*\s*[—–\-]\s*(.+)", stripped)
            if m:
                patterns.append(
                    {
                        "date": current_date,
                        "theme": m.group(1).strip(),
                        "description": m.group(2).strip(),
                    }
                )
                continue

            # Plain dashed: "- Some pattern text"
            if stripped.startswith("- "):
                text = stripped[2:].strip()
                if text and len(text) > 15:
                    parts = re.split(r"\s*[—–]\s*", text, maxsplit=1)
                    theme = parts[0].strip("*").strip()
                    desc = parts[1] if len(parts) > 1 else text
                    if len(theme) > 100:
                        theme = theme[:100]
                    patterns.append(
                        {
                            "date": current_date,
                            "theme": theme,
                            "description": desc.strip(),
                        }
                    )

    return patterns


# ── Public API ─────────────────────────────────────────────────────────────


def store_finding(
    db: sqlite3.Connection,
    run_date: str,
    agent: str,
    title: str,
    summary: str,
    importance: str = "medium",
    category: str | None = None,
    source_url: str | None = None,
    source_name: str | None = None,
) -> int:
    """Store a research finding with its vector embedding.

    Args:
        db: SQLite connection (with row_factory=sqlite3.Row).
        run_date: Date string (YYYY-MM-DD).
        agent: Agent name that produced the finding.
        title: Finding headline.
        summary: Finding body text.
        importance: "high", "medium", or "low".
        category: Optional category tag.
        source_url: Optional URL of the source.
        source_name: Optional display name of the source.

    Returns:
        The finding_id of the newly inserted row.
    """
    _validate_date(run_date)

    cur = db.execute(
        """INSERT INTO findings
           (run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_date,
            agent,
            title,
            summary,
            importance,
            category,
            source_url,
            source_name,
            _now_iso(),
        ),
    )
    finding_id = cur.lastrowid

    # Generate and store embedding
    text = f"{title}. {summary}"
    vec = embed_text(text)
    db.execute(
        "INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
        (finding_id, serialize_f32(vec)),
    )

    db.commit()
    return finding_id


def search_findings(
    db: sqlite3.Connection,
    query: str,
    limit: int = 10,
    agent: str | None = None,
    days: int | None = None,
) -> list[dict]:
    """Semantic search across all findings using cosine similarity.

    Args:
        db: SQLite connection.
        query: Natural language search query.
        limit: Maximum results to return.
        agent: Optional filter by agent name.
        days: Optional filter to only search the last N days.

    Returns:
        List of finding dicts sorted by similarity descending. Each dict
        contains: id, date, agent, title, summary, importance, source,
        url, similarity.
    """
    conditions = ["1=1"]
    params: list = []

    if agent:
        conditions.append("f.agent = ?")
        params.append(agent)
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conditions.append("f.run_date >= ?")
        params.append(cutoff)

    where = " AND ".join(conditions)

    rows = db.execute(
        f"""SELECT f.id, f.run_date, f.agent, f.title, f.summary,
                   f.importance, f.source_url, f.source_name, e.embedding
            FROM findings f
            JOIN findings_embeddings e ON e.finding_id = f.id
            WHERE {where}""",
        params,
    ).fetchall()

    if not rows:
        return []

    query_vec = np.array(embed_text(query), dtype=np.float32)

    results = []
    for r in rows:
        emb = np.array(deserialize_f32(r["embedding"]), dtype=np.float32)
        similarity = float(np.dot(query_vec, emb))
        results.append(
            {
                "id": r["id"],
                "date": r["run_date"],
                "agent": r["agent"],
                "title": r["title"],
                "summary": r["summary"][:300],
                "importance": r["importance"],
                "source": r["source_name"],
                "url": r["source_url"],
                "similarity": round(max(0, similarity), 3),
            }
        )

    results.sort(key=lambda x: -x["similarity"])
    return results[:limit]


def get_context(
    db: sqlite3.Connection,
    agent: str,
    date: str | None = None,
) -> str:
    """Generate a context block for an agent before dispatch.

    Includes:
    - Recent findings (last 7 days) for this agent.
    - Top sources for this agent.
    - Today's findings across all agents with semantic overlap detection.
    - Self-improvement notes from agent_notes.
    - Validated patterns (cross-agent learnings).
    - Cross-pipeline signals.

    For agent=="orchestrator", returns an orchestrator overview instead.

    Args:
        db: SQLite connection.
        agent: Agent name (or "orchestrator").
        date: Date string (YYYY-MM-DD). Defaults to today.

    Returns:
        Markdown-formatted context string.
    """
    date = date or _today()
    _validate_date(date)

    if agent == "orchestrator":
        return _orchestrator_context(db, date)

    cutoff = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=10)).strftime(
        "%Y-%m-%d"
    )

    # Recent findings for this agent
    recent = db.execute(
        """SELECT title, summary, importance, run_date, source_name
           FROM findings WHERE agent = ? AND run_date >= ?
           ORDER BY run_date DESC, importance DESC LIMIT 20""",
        (agent, cutoff),
    ).fetchall()

    # Top sources for this agent
    top_sources = db.execute(
        """SELECT source_name, COUNT(*) as cnt,
                  SUM(CASE WHEN importance = 'high' THEN 1 ELSE 0 END) as high_cnt
           FROM findings WHERE agent = ? AND source_name IS NOT NULL
           GROUP BY source_name ORDER BY high_cnt DESC, cnt DESC LIMIT 10""",
        (agent,),
    ).fetchall()

    # Today's findings across ALL agents (semantic overlap detection)
    today_rows = db.execute(
        """SELECT f.id, f.title, f.agent, e.embedding
           FROM findings f
           LEFT JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.run_date = ?""",
        (date,),
    ).fetchall()

    # Build context block
    lines = [f"## Memory Context for {agent} -- {date}", ""]

    if recent:
        lines.append(
            f"### Your Recent Findings (last 10 days, {len(recent)} total)"
        )
        lines.append(
            "Avoid re-researching these unless there are major updates:"
        )
        for r in recent:
            lines.append(
                f"- [{r['run_date']}] **{r['title']}** ({r['importance']})"
                f" -- {r['source_name'] or 'unknown'}"
            )
        lines.append("")

    if top_sources:
        lines.append("### Your Top Sources (by quality)")
        lines.append(
            "Prioritize these -- they've delivered high-value findings before:"
        )
        for s in top_sources:
            lines.append(
                f"- **{s['source_name']}** -- {s['cnt']} findings"
                f" ({s['high_cnt']} high-value)"
            )
        lines.append("")

    # Semantic overlap detection using embeddings
    other_today = [t for t in today_rows if t["agent"] != agent]
    if other_today:
        lines.append("### Already Covered Today (by other agents)")
        lines.append(
            "These topics are being handled -- focus elsewhere unless you"
            " have a unique angle:"
        )

        # If this agent has recent findings with embeddings, compute similarity
        my_today = [
            t for t in today_rows if t["agent"] == agent and t["embedding"]
        ]
        if my_today:
            my_embs = [
                np.array(deserialize_f32(t["embedding"]), dtype=np.float32)
                for t in my_today
            ]

            for t in other_today:
                if t["embedding"]:
                    emb = np.array(
                        deserialize_f32(t["embedding"]), dtype=np.float32
                    )
                    max_sim = max(float(np.dot(emb, me)) for me in my_embs)
                    if max_sim >= 0.85:
                        lines.append(
                            f"- {t['title']} (by {t['agent']},"
                            f" {int(max_sim * 100)}% overlap with your work)"
                        )
                    else:
                        lines.append(f"- {t['title']} (by {t['agent']})")
                else:
                    lines.append(f"- {t['title']} (by {t['agent']})")
        else:
            for t in other_today:
                lines.append(f"- {t['title']} (by {t['agent']})")
        lines.append("")

    # Recent self-improvement notes for this agent
    notes = db.execute(
        """SELECT note_type, content, run_date FROM agent_notes
           WHERE agent = ? ORDER BY run_date DESC LIMIT 30""",
        (agent,),
    ).fetchall()
    if notes:
        grouped: OrderedDict[str, list] = OrderedDict()
        for n in notes:
            grouped.setdefault(n["note_type"], []).append(n)
        lines.append("### Self-Improvement Notes")
        for ntype, items in grouped.items():
            label = ntype.replace("_", " ").title()
            lines.append(f"\n**{label}**")
            for item in items:
                lines.append(f"- [{item['run_date']}] {item['content']}")
        lines.append("")

    # Validated patterns (cross-agent learnings)
    try:
        vp_rows = db.execute(
            """SELECT pattern_key, distilled_rule, source_agents,
                      observation_count, status
               FROM validated_patterns WHERE status IN ('active', 'promoted')
               ORDER BY observation_count DESC LIMIT 10"""
        ).fetchall()

        # Filter to relevant patterns: agent is in source_agents OR 3+ agents
        relevant_vp = []
        for vp in vp_rows:
            agents = vp["source_agents"].split(",")
            if agent in agents or len(set(agents)) >= 3:
                relevant_vp.append(vp)

        if relevant_vp:
            lines.append("### Validated Patterns (cross-agent learnings)")
            for vp in relevant_vp[:10]:
                status_tag = (
                    " [PROMOTED]" if vp["status"] == "promoted" else ""
                )
                lines.append(
                    f"- {vp['distilled_rule'][:200]}"
                    f" (seen {vp['observation_count']}x){status_tag}"
                )
            lines.append("")
    except sqlite3.OperationalError:
        pass  # Table may not exist in older DBs

    # Cross-pipeline signals
    try:
        sig_cutoff = (
            datetime.strptime(date, "%Y-%m-%d") - timedelta(days=14)
        ).strftime("%Y-%m-%d")
        sig_rows = db.execute(
            """SELECT topic, signal_type, strength, source_pipeline, run_date
               FROM signals WHERE run_date >= ?
               ORDER BY ABS(strength) DESC LIMIT 5""",
            (sig_cutoff,),
        ).fetchall()

        if sig_rows:
            lines.append("### Cross-Pipeline Signals")
            for s in sig_rows:
                icon = "+" if s["strength"] > 0 else "-"
                lines.append(
                    f"- **{s['topic']}** ({s['signal_type']},"
                    f" {icon}{abs(s['strength']):.1f})"
                    f" from {s['source_pipeline']} [{s['run_date']}]"
                )
            lines.append("")
    except sqlite3.OperationalError:
        pass

    total = db.execute("SELECT COUNT(*) as c FROM findings").fetchone()["c"]
    lines.append(f"### Database: {total} total findings across all runs")

    return "\n".join(lines)


def _orchestrator_context(db: sqlite3.Connection, date: str) -> str:
    """Generate overview context for the orchestrator.

    Args:
        db: SQLite connection.
        date: Date string (YYYY-MM-DD).

    Returns:
        Markdown-formatted overview string.
    """
    total = db.execute("SELECT COUNT(*) as c FROM findings").fetchone()["c"]
    last_run = db.execute(
        "SELECT run_date, COUNT(*) as c FROM findings"
        " GROUP BY run_date ORDER BY run_date DESC LIMIT 1"
    ).fetchone()

    top_patterns = db.execute(
        "SELECT theme, recurrence_count, description FROM patterns"
        " ORDER BY recurrence_count DESC LIMIT 5"
    ).fetchall()

    top_sources = db.execute(
        "SELECT display_name, high_value_count, hit_count FROM sources"
        " ORDER BY high_value_count DESC LIMIT 10"
    ).fetchall()

    agent_stats = db.execute(
        """SELECT agent, COUNT(*) as total,
                  SUM(CASE WHEN importance = 'high' THEN 1 ELSE 0 END) as high
           FROM findings GROUP BY agent ORDER BY high DESC"""
    ).fetchall()

    lines = [f"## Memory Overview -- {date}", ""]
    lines.append(f"**Database**: {total} total findings across all runs")
    if last_run:
        lines.append(
            f"**Last run**: {last_run['run_date']} ({last_run['c']} findings)"
        )
    lines.append("")

    if top_patterns:
        lines.append("### Recurring Themes (watch for developments)")
        for p in top_patterns:
            desc = p["description"][:100] if p["description"] else ""
            lines.append(
                f"- **{p['theme']}** (seen {p['recurrence_count']}x) -- {desc}"
            )
        lines.append("")

    if top_sources:
        lines.append("### Top Sources (by quality)")
        for s in top_sources:
            lines.append(
                f"- **{s['display_name']}** --"
                f" {s['high_value_count']} high-value /"
                f" {s['hit_count']} total"
            )
        lines.append("")

    if agent_stats:
        lines.append("### Agent Productivity")
        for a in agent_stats:
            lines.append(
                f"- **{a['agent']}**: {a['total']} findings"
                f" ({a['high']} high-value)"
            )
        lines.append("")

    return "\n".join(lines)


def store_source(
    db: sqlite3.Connection,
    domain: str,
    name: str | None = None,
    quality: str = "medium",
    date: str | None = None,
    notes: str | None = None,
) -> None:
    """Record or update a source quality entry via UPSERT.

    Args:
        db: SQLite connection.
        domain: URL domain (e.g. "techcrunch.com").
        name: Display name (e.g. "TechCrunch").
        quality: "high", "medium", or "low".
        date: Date last seen (YYYY-MM-DD). Defaults to today.
        notes: Optional notes about the source.
    """
    is_high = 1 if quality == "high" else 0
    today = date or _today()
    if date:
        _validate_date(date)

    db.execute(
        """INSERT INTO sources
           (url_domain, display_name, hit_count, high_value_count, last_seen, notes)
           VALUES (?, ?, 1, ?, ?, ?)
           ON CONFLICT(url_domain) DO UPDATE SET
               hit_count = hit_count + 1,
               high_value_count = high_value_count + ?,
               last_seen = ?,
               display_name = COALESCE(?, display_name),
               notes = COALESCE(?, notes)""",
        (
            domain, name, is_high, today, notes,
            is_high, today, name, notes,
        ),
    )
    db.commit()


def get_top_sources(
    db: sqlite3.Connection,
    limit: int = 10,
) -> list[dict]:
    """Get top sources by quality.

    Args:
        db: SQLite connection.
        limit: Maximum results.

    Returns:
        List of source dicts with keys: domain, name, hits, high_value,
        last_seen.
    """
    rows = db.execute(
        """SELECT url_domain, display_name, hit_count, high_value_count,
                  last_seen, notes
           FROM sources
           ORDER BY high_value_count DESC, hit_count DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    return [
        {
            "domain": r["url_domain"],
            "name": r["display_name"],
            "hits": r["hit_count"],
            "high_value": r["high_value_count"],
            "last_seen": r["last_seen"],
        }
        for r in rows
    ]


def store_skill(
    db: sqlite3.Connection,
    run_date: str,
    domain: str,
    title: str,
    description: str,
    steps: str | None = None,
    difficulty: str = "intermediate",
    source_url: str | None = None,
    source_name: str | None = None,
    vertical_config: dict | None = None,
) -> int:
    """Store an actionable skill with its vector embedding.

    Args:
        db: SQLite connection.
        run_date: Date string (YYYY-MM-DD).
        domain: Skill domain (e.g. "vibe-coding"). Will be normalized.
        title: Skill title.
        description: Skill description.
        steps: Optional step-by-step instructions.
        difficulty: "beginner", "intermediate", or "advanced".
        source_url: Optional URL of the source.
        source_name: Optional display name of the source.
        vertical_config: Optional vertical configuration dict with
            "canonical_domains" key.

    Returns:
        The skill_id of the newly inserted row.
    """
    _validate_date(run_date)
    canonical_domains = (
        vertical_config.get("canonical_domains") if vertical_config else None
    )
    domain = _normalize_domain(domain, canonical_domains)

    cur = db.execute(
        """INSERT INTO skills
           (run_date, domain, title, description, steps, difficulty,
            source_url, source_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_date, domain, title, description,
            steps, difficulty, source_url, source_name,
        ),
    )
    skill_id = cur.lastrowid

    text = f"{title}. {description}"
    vec = embed_text(text)
    db.execute(
        "INSERT INTO skills_embeddings (skill_id, embedding) VALUES (?, ?)",
        (skill_id, serialize_f32(vec)),
    )

    db.commit()
    return skill_id


def search_skills(
    db: sqlite3.Connection,
    query: str,
    limit: int = 10,
    domain: str | None = None,
) -> list[dict]:
    """Semantic search across skills.

    Args:
        db: SQLite connection.
        query: Natural language search query.
        limit: Maximum results.
        domain: Optional filter by skill domain.

    Returns:
        List of skill dicts sorted by similarity descending. Each dict
        contains: id, date, domain, title, description, steps, difficulty,
        source_url, source_name, similarity.
    """
    conditions = ["1=1"]
    params: list = []

    if domain:
        conditions.append("s.domain = ?")
        params.append(domain)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT s.id, s.run_date, s.domain, s.title, s.description,
                   s.steps, s.difficulty, s.source_url, s.source_name,
                   e.embedding
            FROM skills s
            JOIN skills_embeddings e ON e.skill_id = s.id
            WHERE {where}""",
        params,
    ).fetchall()

    if not rows:
        return []

    query_vec = np.array(embed_text(query), dtype=np.float32)
    results = []
    for r in rows:
        emb = np.array(deserialize_f32(r["embedding"]), dtype=np.float32)
        sim = float(np.dot(query_vec, emb))
        results.append(
            {
                "id": r["id"],
                "date": r["run_date"],
                "domain": r["domain"],
                "title": r["title"],
                "description": r["description"],
                "steps": r["steps"],
                "difficulty": r["difficulty"],
                "source_url": r["source_url"],
                "source_name": r["source_name"],
                "similarity": round(max(0, sim), 3),
            }
        )

    results.sort(key=lambda x: -x["similarity"])
    return results[:limit]


def list_skills(
    db: sqlite3.Connection,
    domain: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List skills, optionally filtered by domain.

    Args:
        db: SQLite connection.
        domain: Optional filter by skill domain.
        limit: Maximum results.

    Returns:
        List of skill dicts ordered by date descending.
    """
    conditions = ["1=1"]
    params: list = []

    if domain:
        conditions.append("domain = ?")
        params.append(domain)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT id, run_date, domain, title, description, steps,
                   difficulty, source_url, source_name
            FROM skills WHERE {where}
            ORDER BY run_date DESC, id DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    return [dict(r) for r in rows]


def evaluate_run(
    db: sqlite3.Connection,
    date: str | None = None,
    trending_topics: list[str] | None = None,
    total_agents: int = 13,
) -> dict:
    """Compute and store per-run quality metrics.

    Evaluates a day's research output on multiple dimensions:
    - Agent utilization: fraction of agents that produced findings.
    - Source diversity: unique sources / total findings.
    - High value ratio: fraction of high-importance findings.
    - Dedup rate: fraction of pairwise finding-pairs above 0.85 similarity.
    - Trending coverage: fraction of trending topics semantically covered.

    Compares to the 7-day rolling average and flags quality drops.

    Args:
        db: SQLite connection.
        date: Date string (YYYY-MM-DD). Defaults to today.
        trending_topics: Optional list of trending topic strings to check
            coverage against.
        total_agents: Expected number of agents for utilization calculation.

    Returns:
        Dict with all metric scores. Returns {"error": "..."} if no findings.
    """
    date = date or _today()
    _validate_date(date)

    # Total findings for this run
    findings = db.execute(
        """SELECT id, agent, title, summary, importance, source_name
           FROM findings WHERE run_date = ?""",
        (date,),
    ).fetchall()

    if not findings:
        return {"error": f"No findings for {date}"}

    total = len(findings)
    high_value = sum(1 for f in findings if f["importance"] == "high")

    # Agent utilization
    agents_with_findings = len(set(f["agent"] for f in findings))
    agent_utilization = min(1.0, agents_with_findings / float(total_agents))

    # Source diversity
    sources = set(f["source_name"] for f in findings if f["source_name"])
    unique_sources = len(sources)
    source_diversity = min(1.0, unique_sources / max(total, 1))

    # High value ratio
    high_value_ratio = high_value / max(total, 1)

    # Dedup rate: pairwise similarity among findings
    dedup_rate = 0.0
    dup_pairs = 0
    total_pairs = 0
    emb_rows = db.execute(
        """SELECT e.embedding FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.run_date = ?""",
        (date,),
    ).fetchall()

    embeddings = []
    if len(emb_rows) >= 2:
        embeddings = [
            np.array(deserialize_f32(r["embedding"]), dtype=np.float32)
            for r in emb_rows
        ]
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                total_pairs += 1
                sim = float(np.dot(embeddings[i], embeddings[j]))
                if sim > 0.85:
                    dup_pairs += 1
        dedup_rate = dup_pairs / max(total_pairs, 1)

    # Trending coverage
    trending_coverage = 0.0
    if trending_topics and embeddings:
        topic_vecs = embed_texts(trending_topics)
        covered = 0
        for tvec in topic_vecs:
            tvec_np = np.array(tvec, dtype=np.float32)
            max_sim = max(float(np.dot(tvec_np, emb)) for emb in embeddings)
            if max_sim >= 0.60:
                covered += 1
        trending_coverage = covered / len(trending_topics)

    # Overall score (weighted average)
    overall = (
        0.3 * agent_utilization
        + 0.3 * source_diversity
        + 0.2 * high_value_ratio
        + 0.2 * trending_coverage
    )

    # Store in run_quality
    details = {
        "agents_active": agents_with_findings,
        "dup_pairs": dup_pairs if len(emb_rows) >= 2 else 0,
        "total_pairs": total_pairs if len(emb_rows) >= 2 else 0,
    }

    db.execute(
        """INSERT OR REPLACE INTO run_quality
           (run_date, total_findings, unique_sources, high_value_count,
            trending_coverage, dedup_rate, agent_utilization, source_diversity,
            overall_score, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            date, total, unique_sources, high_value,
            trending_coverage, dedup_rate, agent_utilization,
            source_diversity, overall, json.dumps(details), _now_iso(),
        ),
    )
    db.commit()

    # Compare to 7-day rolling average
    avg_cutoff = (
        datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)
    ).strftime("%Y-%m-%d")
    avg_row = db.execute(
        """SELECT AVG(overall_score) as avg_score FROM run_quality
           WHERE run_date >= ? AND run_date < ?""",
        (avg_cutoff, date),
    ).fetchone()
    avg_score = (
        avg_row["avg_score"]
        if avg_row and avg_row["avg_score"] is not None
        else None
    )

    result = {
        "date": date,
        "total_findings": total,
        "unique_sources": unique_sources,
        "high_value_count": high_value,
        "agent_utilization": round(agent_utilization, 3),
        "source_diversity": round(source_diversity, 3),
        "high_value_ratio": round(high_value_ratio, 3),
        "trending_coverage": round(trending_coverage, 3),
        "dedup_rate": round(dedup_rate, 3),
        "overall_score": round(overall, 3),
    }

    if avg_score is not None:
        result["7day_avg"] = round(avg_score, 3)
        delta = overall - avg_score
        result["delta"] = round(delta, 3)
        if delta < -0.1:
            result["warning"] = (
                f"Quality dropped {abs(delta):.2f} below 7-day average"
            )

    return result


def log_agent_run(
    db: sqlite3.Connection,
    agent: str,
    run_date: str,
    findings_count: int = 0,
) -> None:
    """Upsert an agent run log entry.

    Tracks whether an agent ran on a given date and how many findings it
    produced. Enables zero-output detection even when agents produce no
    findings rows.

    Args:
        db: SQLite connection.
        agent: Agent name.
        run_date: Date string (YYYY-MM-DD).
        findings_count: Number of findings produced.
    """
    _validate_date(run_date)

    db.execute(
        """INSERT INTO run_log (agent, run_date, findings_count)
           VALUES (?, ?, ?)
           ON CONFLICT(agent, run_date) DO UPDATE SET
               findings_count = ?,
               created_at = datetime('now')""",
        (agent, run_date, findings_count, findings_count),
    )
    db.commit()


def get_stats(db: sqlite3.Connection) -> dict:
    """Compute and return database statistics.

    Args:
        db: SQLite connection.

    Returns:
        Dict with counts for all major tables and breakdowns by agent,
        date, importance, domain, platform, etc.
    """
    findings_count = db.execute(
        "SELECT COUNT(*) as c FROM findings"
    ).fetchone()["c"]
    vec_count = db.execute(
        "SELECT COUNT(*) as c FROM findings_embeddings"
    ).fetchone()["c"]
    sources_count = db.execute(
        "SELECT COUNT(*) as c FROM sources"
    ).fetchone()["c"]
    patterns_count = db.execute(
        "SELECT COUNT(*) as c FROM patterns"
    ).fetchone()["c"]

    findings_by_agent = db.execute(
        "SELECT agent, COUNT(*) as c FROM findings"
        " GROUP BY agent ORDER BY c DESC"
    ).fetchall()
    findings_by_date = db.execute(
        "SELECT run_date, COUNT(*) as c FROM findings"
        " GROUP BY run_date ORDER BY run_date DESC LIMIT 10"
    ).fetchall()
    importance_dist = db.execute(
        "SELECT importance, COUNT(*) as c FROM findings"
        " GROUP BY importance ORDER BY c DESC"
    ).fetchall()

    skills_count = db.execute(
        "SELECT COUNT(*) as c FROM skills"
    ).fetchone()["c"]
    skills_by_domain = db.execute(
        "SELECT domain, COUNT(*) as c FROM skills"
        " GROUP BY domain ORDER BY c DESC"
    ).fetchall()

    feedback_total = db.execute(
        "SELECT COUNT(*) as c FROM user_feedback"
    ).fetchone()["c"]
    feedback_pending = db.execute(
        "SELECT COUNT(*) as c FROM user_feedback WHERE processed = 0"
    ).fetchone()["c"]
    prefs_count = db.execute(
        "SELECT COUNT(*) as c FROM user_preferences"
    ).fetchone()["c"]

    social_posts_count = db.execute(
        "SELECT COUNT(*) as c FROM social_posts"
    ).fetchone()["c"]
    social_posted = db.execute(
        "SELECT COUNT(*) as c FROM social_posts WHERE posted = 1"
    ).fetchone()["c"]
    social_by_platform = db.execute(
        "SELECT platform, COUNT(*) as c FROM social_posts"
        " GROUP BY platform ORDER BY c DESC"
    ).fetchall()
    social_feedback_count = db.execute(
        "SELECT COUNT(*) as c FROM social_feedback"
    ).fetchone()["c"]
    social_fb_by_action = db.execute(
        "SELECT action, COUNT(*) as c FROM social_feedback"
        " GROUP BY action ORDER BY c DESC"
    ).fetchall()

    # Newer tables -- safe counts with try/except for older DBs
    agent_notes_count = db.execute(
        "SELECT COUNT(*) as c FROM agent_notes"
    ).fetchone()["c"]
    notes_emb_count = 0
    vp_count = 0
    signals_count = 0
    rq_count = 0
    try:
        notes_emb_count = db.execute(
            "SELECT COUNT(*) as c FROM agent_notes_embeddings"
        ).fetchone()["c"]
        vp_count = db.execute(
            "SELECT COUNT(*) as c FROM validated_patterns"
        ).fetchone()["c"]
        signals_count = db.execute(
            "SELECT COUNT(*) as c FROM signals"
        ).fetchone()["c"]
        rq_count = db.execute(
            "SELECT COUNT(*) as c FROM run_quality"
        ).fetchone()["c"]
    except sqlite3.OperationalError:
        pass

    return {
        "findings": findings_count,
        "embeddings": vec_count,
        "sources": sources_count,
        "patterns": patterns_count,
        "skills": skills_count,
        "feedback_total": feedback_total,
        "feedback_pending": feedback_pending,
        "preferences": prefs_count,
        "social_posts": social_posts_count,
        "social_posted": social_posted,
        "social_by_platform": {r["platform"]: r["c"] for r in social_by_platform},
        "social_feedback": social_feedback_count,
        "social_feedback_by_action": {
            r["action"]: r["c"] for r in social_fb_by_action
        },
        "agent_notes": agent_notes_count,
        "agent_notes_embeddings": notes_emb_count,
        "validated_patterns": vp_count,
        "signals": signals_count,
        "run_quality_entries": rq_count,
        "by_agent": {r["agent"]: r["c"] for r in findings_by_agent},
        "by_date": {r["run_date"]: r["c"] for r in findings_by_date},
        "by_importance": {r["importance"]: r["c"] for r in importance_dist},
        "skills_by_domain": {r["domain"]: r["c"] for r in skills_by_domain},
    }


def backfill_from_reports(
    db: sqlite3.Connection,
    reports_dir: str | Path,
    learnings_file: str | Path | None = None,
    date: str | None = None,
    vertical_config: dict | None = None,
) -> dict:
    """Backfill findings, skills, and patterns from report files.

    Can operate in two modes:
    1. Single-date (fast path): If `date` is specified, only backfill skills
       from that date's report.
    2. Full backfill: Process all reports in the directory, plus patterns
       from learnings.md.

    Args:
        db: SQLite connection.
        reports_dir: Path to directory containing YYYY-MM-DD.md report files.
        learnings_file: Optional path to learnings.md for pattern extraction.
        date: Optional single date to backfill (fast path, skills only).
        vertical_config: Optional vertical config dict with keys:
            section_agent_map, skill_domain_keywords, canonical_domains.

    Returns:
        Dict with counts: total_findings, total_sources, total_patterns,
        total_skills, and per-date details.
    """
    reports_dir = Path(reports_dir)
    section_agent_map = (
        vertical_config.get("section_agent_map") if vertical_config else None
    )
    skill_domain_keywords = (
        vertical_config.get("skill_domain_keywords") if vertical_config else None
    )

    result = {
        "total_findings": 0,
        "total_sources": 0,
        "total_patterns": 0,
        "total_skills": 0,
        "dates": {},
    }

    # ── Fast path: single-date skills backfill ────────────────────────
    if date:
        _validate_date(date)
        report_file = reports_dir / f"{date}.md"
        if not report_file.exists():
            result["error"] = f"No report found for {date}"
            return result

        added, already = _backfill_skills_for_date(
            db, report_file, date, skill_domain_keywords
        )
        result["total_skills"] = added
        result["dates"][date] = {"skills_added": added, "skills_existing": already}
        return result

    # ── Full backfill from reports ────────────────────────────────────
    if reports_dir.exists():
        for report_file in sorted(reports_dir.glob("*.md")):
            rdate = report_file.stem
            if not re.match(r"\d{4}-\d{2}-\d{2}", rdate):
                continue

            date_info: dict = {"findings": 0, "sources": 0, "skills_added": 0}

            existing = db.execute(
                "SELECT COUNT(*) as c FROM findings WHERE run_date = ?",
                (rdate,),
            ).fetchone()["c"]

            if existing > 0:
                date_info["skipped"] = True
                date_info["existing_findings"] = existing
            else:
                content = report_file.read_text()
                findings = _parse_report(content, rdate, section_agent_map)

                texts = [f"{f['title']}. {f['summary'][:500]}" for f in findings]
                if texts:
                    vectors = embed_texts(texts)

                    for f, vec in zip(findings, vectors):
                        cur = db.execute(
                            """INSERT INTO findings
                               (run_date, agent, title, summary, importance,
                                source_url, source_name)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                f["date"], f["agent"], f["title"],
                                f["summary"], f["importance"],
                                f.get("source_url"), f.get("source_name"),
                            ),
                        )
                        db.execute(
                            "INSERT INTO findings_embeddings"
                            " (finding_id, embedding) VALUES (?, ?)",
                            (cur.lastrowid, serialize_f32(vec)),
                        )
                        result["total_findings"] += 1
                        date_info["findings"] += 1

                        # Track source
                        if f.get("source_url"):
                            source_domain = urlparse(f["source_url"]).netloc
                            if source_domain:
                                is_high = (
                                    1 if f["importance"] == "high" else 0
                                )
                                db.execute(
                                    """INSERT INTO sources
                                       (url_domain, display_name, hit_count,
                                        high_value_count, last_seen)
                                       VALUES (?, ?, 1, ?, ?)
                                       ON CONFLICT(url_domain) DO UPDATE SET
                                           hit_count = hit_count + 1,
                                           high_value_count =
                                               high_value_count + ?,
                                           last_seen = ?""",
                                    (
                                        source_domain,
                                        f.get("source_name"),
                                        is_high, rdate,
                                        is_high, rdate,
                                    ),
                                )
                                result["total_sources"] += 1
                                date_info["sources"] += 1

                    db.commit()

            # Backfill skills for every report (regardless of findings)
            added, already = _backfill_skills_for_date(
                db, report_file, rdate, skill_domain_keywords
            )
            date_info["skills_added"] = added
            date_info["skills_existing"] = already
            result["total_skills"] += added

            result["dates"][rdate] = date_info

    # ── Backfill patterns from learnings ──────────────────────────────
    if learnings_file:
        learnings_path = Path(learnings_file)
        if learnings_path.exists():
            content = learnings_path.read_text()
            patterns = _parse_patterns(content)

            SIMILARITY_THRESHOLD = 0.75

            for p in patterns:
                new_vec = np.array(embed_text(p["theme"]), dtype=np.float32)

                # Check for semantically similar existing pattern
                rows = db.execute(
                    """SELECT p2.id, p2.recurrence_count, e.embedding
                       FROM patterns p2
                       JOIN patterns_embeddings e ON e.pattern_id = p2.id"""
                ).fetchall()

                best_id = None
                best_sim = 0.0

                for row in rows:
                    emb = np.array(
                        deserialize_f32(row["embedding"]), dtype=np.float32
                    )
                    sim = float(np.dot(new_vec, emb))
                    if sim > best_sim:
                        best_sim = sim
                        best_id = row["id"]

                if best_id and best_sim >= SIMILARITY_THRESHOLD:
                    db.execute(
                        """UPDATE patterns
                           SET recurrence_count = recurrence_count + 1,
                               last_seen = ?
                           WHERE id = ?""",
                        (p["date"], best_id),
                    )
                else:
                    cur = db.execute(
                        """INSERT INTO patterns
                           (run_date, theme, description, first_seen,
                            last_seen, recurrence_count)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            p["date"], p["theme"], p["description"],
                            p["date"], p["date"], 1,
                        ),
                    )
                    pattern_id = cur.lastrowid
                    db.execute(
                        "INSERT INTO patterns_embeddings"
                        " (pattern_id, embedding) VALUES (?, ?)",
                        (pattern_id, serialize_f32(new_vec.tolist())),
                    )
                    result["total_patterns"] += 1

            db.commit()

    return result


def _backfill_skills_for_date(
    db: sqlite3.Connection,
    report_file: Path,
    date: str,
    skill_domain_keywords: dict[str, list[str]] | None = None,
) -> tuple[int, int]:
    """Backfill skills from a single report.

    Args:
        db: SQLite connection.
        report_file: Path to the report markdown file.
        date: Run date (YYYY-MM-DD).
        skill_domain_keywords: Override keyword mapping for domain inference.

    Returns:
        Tuple of (added_count, already_stored_count).
    """
    content = report_file.read_text()
    parsed = _parse_skills_from_report(content, date, skill_domain_keywords)
    if not parsed:
        return 0, 0

    # Fetch existing skill titles for this date
    existing_rows = db.execute(
        "SELECT title FROM skills WHERE run_date = ?", (date,)
    ).fetchall()
    existing_titles = [r["title"] for r in existing_rows]

    added = 0
    already = 0
    new_skills = []
    for skill in parsed:
        if any(_titles_match(skill["title"], et) for et in existing_titles):
            already += 1
            continue
        new_skills.append(skill)

    if new_skills:
        texts = [f"{s['title']}. {s['description'][:500]}" for s in new_skills]
        vectors = embed_texts(texts)

        for skill, vec in zip(new_skills, vectors):
            cur = db.execute(
                """INSERT INTO skills
                   (run_date, domain, title, description, steps, difficulty,
                    source_url, source_name, backfilled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill["date"], skill["domain"], skill["title"],
                    skill["description"], skill["steps"],
                    skill["difficulty"], skill["source_url"],
                    skill["source_name"], 1,
                ),
            )
            db.execute(
                "INSERT INTO skills_embeddings"
                " (skill_id, embedding) VALUES (?, ?)",
                (cur.lastrowid, serialize_f32(vec)),
            )
            added += 1

        db.commit()

    return added, already
