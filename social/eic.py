"""EIC topic selection and creative brief generation for the social pipeline.

Merged Editor-in-Chief + Social Curator roles. Selects the best topic from
today's research findings, deduplicates against recent posts, and expands
the chosen topic into a creative brief via the Creative Director agent.

All functions take a `db` (sqlite3.Connection) parameter and return data
structures. No print statements, no CLI.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.agents import run_claude_prompt
from orchestrator.router import get_model

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

logger = logging.getLogger(__name__)


def _load_social_config() -> dict:
    """Load social-config.json from project root."""
    config_path = PROJECT_ROOT / "social-config.json"
    with open(config_path) as f:
        return json.load(f)


def _get_recent_findings(
    db: sqlite3.Connection, date_str: str, days: int = 7,
) -> list[dict]:
    """Load today's findings plus high-importance findings from the last N days."""
    cutoff = (
        datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=days)
    ).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT id, run_date, agent, title, summary, importance,
                  source_url, source_name
           FROM findings
           WHERE run_date >= ?
             AND (run_date = ? OR importance = 'high')
           ORDER BY
             CASE WHEN run_date = ? THEN 0 ELSE 1 END,
             CASE importance WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
             run_date DESC
           LIMIT 50""",
        (cutoff, date_str, date_str),
    ).fetchall()

    return [dict(r) for r in rows]


def _get_recent_post_anchors(db: sqlite3.Connection, days: int = 14) -> list[dict]:
    """Load recent post anchors for dedup context."""
    from memory.social import recent_posts

    posts = recent_posts(db, days=days, limit=30)
    return [
        {"date": p["date"], "platform": p["platform"], "anchor_text": p.get("anchor_text", "")}
        for p in posts
        if p.get("anchor_text")
    ]


def _get_user_preferences(db: sqlite3.Connection) -> list[dict]:
    """Load active user preferences for topic weighting."""
    from memory.feedback import list_preferences

    return list_preferences(db, effective=True)


def _build_eic_prompt(
    findings: list[dict],
    recent_posts: list[dict],
    preferences: list[dict],
    date_str: str,
) -> str:
    """Build the EIC prompt with context.

    Includes: today's findings summaries, recent post anchors (for dedup),
    user preferences.
    Output schema: {topic, anchor_text, angle, importance_score, source_urls, reasoning}
    """
    # Format findings into a readable block
    findings_block = []
    for f in findings:
        tag = "[TODAY]" if f["run_date"] == date_str else f"[{f['run_date']}]"
        findings_block.append(
            f"- {tag} [{f['importance'].upper()}] **{f['title']}** ({f['agent']})\n"
            f"  {f['summary']}\n"
            f"  Source: {f.get('source_name', 'unknown')} | {f.get('source_url', 'N/A')}"
        )

    # Format recent anchors for dedup
    dedup_block = []
    for p in recent_posts:
        dedup_block.append(f"- [{p['date']}] {p['platform']}: {p['anchor_text']}")

    # Format preferences
    pref_block = []
    for p in preferences:
        weight = p.get("effective_weight", p.get("weight", 1.0))
        pref_block.append(f"- {p['topic']} (weight: {weight:.1f})")

    # Load the EIC agent definition for the scoring rubric
    eic_md_path = PROJECT_ROOT / "agents" / "eic.md"
    eic_instructions = ""
    if eic_md_path.exists():
        eic_instructions = eic_md_path.read_text()

    config = _load_social_config()
    quality_threshold = config.get("eic", {}).get("quality_threshold", 5.0)
    max_topics = config.get("eic", {}).get("max_topics", 3)

    prompt = f"""Pick the best topic from today's research findings for social media posts.
Date: {date_str}. Quality threshold: {quality_threshold}. Max topics: {max_topics}.

Score on: Novelty (0-10), Broad Appeal (0-10), Thread Potential (0-10).
Composite = (Novelty × 0.35) + (Broad Appeal × 0.40) + (Thread Potential × 0.25).
Only topics with composite >= {quality_threshold} qualify.

## Today's Findings ({len(findings)} total)

{chr(10).join(findings_block[:20]) if findings_block else "No findings."}

## Recent Posts (DO NOT repeat)

{chr(10).join(dedup_block[:10]) if dedup_block else "None."}

## User Preferences

{chr(10).join(pref_block) if pref_block else "None."}

---

Output ONLY a JSON array. No markdown, no explanation, no code fences.
Each element: {{"anchor": "topic name", "angle": "specific angle", "editorial_scores": {{"novelty": N, "broad_appeal": N, "thread_potential": N, "composite": N}}, "source_urls": ["url1"], "key_points": ["p1", "p2", "p3"]}}

If nothing qualifies: {{"topics": [], "kill_explanation": "why"}}
"""
    return prompt


def _parse_eic_response(raw: str) -> list[dict] | dict:
    """Parse JSON from the EIC agent response.

    Returns either a list of topic dicts (normal output) or a dict with
    'topics' key (kill-day output).
    """
    text = raw.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON array
    array_match = re.search(r'\[[\s\S]*\]', text)
    if array_match:
        try:
            data = json.loads(array_match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # Try to find JSON object with "topics" key
    obj_match = re.search(r'\{[\s\S]*"topics"[\s\S]*\}', text)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Check if the text response is an intentional kill (no JSON, just explanation)
    lower = text.lower()
    kill_phrases = ["no topics", "kill", "threshold", "none of", "no candidate", "no finding"]
    if any(phrase in lower for phrase in kill_phrases):
        logger.info(f"EIC kill day (text response, {len(text)} chars)")
        return {"topics": [], "kill_explanation": text[:500]}

    logger.warning(f"Could not parse EIC response ({len(text)} chars)")
    return {"topics": [], "kill_explanation": "Failed to parse EIC response."}


def select_topic(
    db: sqlite3.Connection,
    user_id: str,
    date_str: str,
    *,
    max_retries: int = 3,
) -> dict | None:
    """Select a topic for today's social posts.

    Steps:
    1. Load recent findings from memory (today + last 7 days high-importance)
    2. Check recent social posts for dedup (memory.check_duplicate)
    3. Build EIC prompt with context
    4. Run claude -p with Opus model
    5. Parse JSON response: {topic, anchor_text, angle, importance_score, source_urls}
    6. Validate: importance_score >= quality_threshold (from config)
    7. Dedup check against recent posts
    8. Retry up to max_retries if topic is duplicate or below threshold
    9. Return topic dict or None if no good topic found (kill day)
    """
    from memory.social import check_duplicate

    config = _load_social_config()
    quality_threshold = config.get("eic", {}).get("quality_threshold", 5.0)

    findings = _get_recent_findings(db, date_str)
    recent_posts = _get_recent_post_anchors(db)
    preferences = _get_user_preferences(db)

    if not findings:
        logger.warning("No findings available for EIC — kill day")
        return None

    for attempt in range(max_retries):
        logger.info(f"EIC topic selection attempt {attempt + 1}/{max_retries}")

        prompt = _build_eic_prompt(findings, recent_posts, preferences, date_str)

        raw_output, exit_code = run_claude_prompt(
            prompt,
            task_type="eic",
            allowed_tools=[],  # No tools needed — all context is in the prompt
        )

        if exit_code != 0:
            logger.error(f"EIC claude call failed (exit {exit_code}), attempt {attempt + 1}")
            continue

        parsed = _parse_eic_response(raw_output)

        # Handle kill-day response
        if isinstance(parsed, dict):
            topics = parsed.get("topics", [])
            if not topics:
                kill_reason = parsed.get("kill_explanation", "No topics passed threshold")
                logger.info(f"EIC kill day: {kill_reason}")
                return None
            # Shouldn't normally get here, but handle it
            parsed = topics

        if not isinstance(parsed, list) or not parsed:
            logger.warning("EIC returned empty or invalid response")
            continue

        # Take the highest-ranked topic
        topic = parsed[0]

        # Validate composite score
        scores = topic.get("editorial_scores", {})
        composite = scores.get("composite", 0)
        if composite < quality_threshold:
            logger.info(
                f"EIC topic below threshold: {composite:.1f} < {quality_threshold} "
                f"(anchor: {topic.get('anchor', 'unknown')[:80]})"
            )
            continue

        # Dedup check
        anchor_text = topic.get("anchor", "")
        if anchor_text:
            dedup_result = check_duplicate(db, anchor_text)
            if dedup_result["is_duplicate"]:
                top_dup = dedup_result["duplicates"][0]
                logger.info(
                    f"EIC topic is duplicate (similarity {top_dup['similarity']:.2f} "
                    f"to post from {top_dup['date']}), retrying"
                )
                # Add the rejected anchor to recent_posts for next attempt
                recent_posts.append({
                    "date": date_str,
                    "platform": "rejected",
                    "anchor_text": anchor_text,
                })
                continue

        # Normalize the topic dict to a consistent shape
        selected = {
            "rank": topic.get("rank", 1),
            "anchor": topic.get("anchor", ""),
            "anchor_source": topic.get("anchor_source", ""),
            "connection": topic.get("connection"),
            "connection_source": topic.get("connection_source"),
            "reaction": topic.get("reaction", ""),
            "open_questions": topic.get("open_questions", []),
            "do_not_include": topic.get("do_not_include", []),
            "confidence": topic.get("confidence", "MEDIUM"),
            "emotional_register": topic.get("emotional_register", "curious"),
            "mindpattern_context": topic.get("mindpattern_context", "none today"),
            "mindpattern_link": topic.get("mindpattern_link", config.get("mindpattern_link", "https://mindpattern.ai")),
            "editorial_scores": scores,
            "source_urls": _extract_source_urls(topic),
        }

        logger.info(
            f"EIC selected topic (composite {composite:.1f}): "
            f"{selected['anchor'][:100]}"
        )
        return selected

    logger.warning(f"EIC exhausted {max_retries} retries — kill day")
    return None


def _extract_source_urls(topic: dict) -> list[str]:
    """Extract all source URLs from a topic dict."""
    urls = []

    # From anchor_source (may contain URL inline)
    anchor_src = topic.get("anchor_source", "")
    if anchor_src:
        url_match = re.search(r'https?://\S+', anchor_src)
        if url_match:
            urls.append(url_match.group().rstrip('.,)'))

    # From connection_source
    conn_src = topic.get("connection_source", "")
    if conn_src:
        url_match = re.search(r'https?://\S+', conn_src)
        if url_match:
            urls.append(url_match.group().rstrip('.,)'))

    # From explicit source_urls field
    if isinstance(topic.get("source_urls"), list):
        urls.extend(topic["source_urls"])

    return list(dict.fromkeys(urls))  # dedupe preserving order


def create_brief(
    db: sqlite3.Connection,
    topic: dict,
    date_str: str,
) -> dict:
    """Expand EIC topic into a creative brief via Creative Director (Sonnet).

    Reads the Creative Director agent definition (Mode 1: Brief Generation)
    and sends the approved topic for expansion into a unified creative brief.

    Returns: {
        topic, anchor_text, angle, editorial_angle,
        visual_metaphor_direction, key_points, source_urls,
        platform_hooks: {x, linkedin, bluesky}
    }
    """
    # Load agent definitions
    cd_md_path = PROJECT_ROOT / "agents" / "creative-director.md"
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"

    cd_instructions = ""
    if cd_md_path.exists():
        cd_instructions = cd_md_path.read_text()

    voice_guide = ""
    if voice_guide_path.exists():
        voice_guide = voice_guide_path.read_text()

    config = _load_social_config()

    prompt = f"""You are the Creative Director for mindpattern. Run in Brief Generation mode.

{cd_instructions}

---

{voice_guide}

---

## EIC Approved Topic

```json
{json.dumps(topic, indent=2)}
```

## Date: {date_str}

---

CRITICAL: Output ONLY valid JSON matching the Unified Brief Output Schema from your instructions.
No markdown, no commentary, no code fences.
"""

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="creative_brief",
        allowed_tools=["Read", "Glob"],
    )

    if exit_code != 0:
        logger.error(f"Creative Director brief generation failed (exit {exit_code})")
        return _fallback_brief(topic, date_str, config)

    # Parse the creative brief
    brief = _parse_brief_response(raw_output)

    if not brief:
        logger.warning("Failed to parse Creative Director response, using fallback")
        return _fallback_brief(topic, date_str, config)

    # Merge EIC topic data into the brief for downstream consumers
    brief["_eic_topic"] = topic
    brief["source_urls"] = topic.get("source_urls", [])
    brief["date"] = date_str

    logger.info(
        f"Creative brief generated: {brief.get('editorial_angle', 'no angle')[:100]}"
    )
    return brief


def _parse_brief_response(raw: str) -> dict | None:
    """Parse JSON from the Creative Director response."""
    text = raw.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "editorial_angle" in data:
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object with editorial_angle
    obj_match = re.search(r'\{[\s\S]*"editorial_angle"[\s\S]*\}', text)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _fallback_brief(topic: dict, date_str: str, config: dict) -> dict:
    """Generate a minimal creative brief when the CD agent fails.

    Uses the EIC topic data directly — no visual direction, basic hooks.
    """
    anchor = topic.get("anchor", "")
    source = topic.get("anchor_source", "")

    return {
        "editorial_angle": anchor,
        "key_message": anchor[:200],
        "emotional_register": topic.get("emotional_register", "curious"),
        "tone": "conversational-authoritative",
        "source_attribution": {
            "primary": {"name": source, "url": ""},
            "supporting": [],
        },
        "visual_metaphor_direction": {
            "core_tension": "Fallback — no visual direction generated",
            "suggested_approach": "symbolic",
            "mood": "stark",
            "key_elements": [],
            "avoid": [],
        },
        "platform_hooks": {
            "x": {"hook": anchor[:50], "angle": anchor[:100]},
            "linkedin": {"hook": anchor[:80], "angle": anchor[:150]},
            "bluesky": {"hook": anchor[:60], "angle": anchor[:120]},
        },
        "do_not_include": topic.get("do_not_include", []),
        "mindpattern_link": config.get("mindpattern_link", "https://mindpattern.ai"),
        "_eic_topic": topic,
        "source_urls": topic.get("source_urls", []),
        "date": date_str,
        "_fallback": True,
    }
