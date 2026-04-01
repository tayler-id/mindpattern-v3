"""EIC topic selection and creative brief generation for the social pipeline.

Merged Editor-in-Chief + Social Curator roles. Selects the best topic from
today's research findings, deduplicates against recent posts, and expands
the chosen topic into a creative brief via the Creative Director agent.

Uses file-based I/O: agents write structured JSON to output files via
run_agent_with_files(). Python reads the files back and handles the
retry/dedup loop.

All functions take a `db` (sqlite3.Connection) parameter and return data
structures. No print statements, no CLI.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.agents import run_agent_with_files

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


def _build_eic_agent_prompt(
    date_str: str,
    quality_threshold: float,
    max_topics: int,
    rejected_anchors: list[str] | None = None,
) -> str:
    """Build prompt for the EIC agent that uses memory_cli.py via Bash tool.

    Instead of inlining all findings/posts in the prompt, the agent is
    instructed to query them itself using memory_cli.py.
    """
    rejected_section = ""
    if rejected_anchors:
        rejected_lines = "\n".join(f"- {a}" for a in rejected_anchors)
        rejected_section = f"""
## Rejected Anchors (DO NOT select these or closely related angles)

{rejected_lines}
"""

    output_file = "data/social-drafts/eic-topic.json"

    prompt = f"""You are the Editor-in-Chief for mindpattern. Today is {date_str}.

## Step 1: Load context using memory_cli.py

Run these commands to gather today's findings and recent posts:

```bash
python3 memory_cli.py search-findings --days 1 --limit 50
```

```bash
python3 memory_cli.py search-findings --days 7 --min-importance high --limit 20
```

```bash
python3 memory_cli.py recent-posts --days 30
```

## Step 2: Score and select topics

Quality threshold: {quality_threshold}. Max topics: {max_topics}.

Score on: Novelty (0-10), Broad Appeal (0-10), Thread Potential (0-10).
Composite = (Novelty x 0.35) + (Broad Appeal x 0.40) + (Thread Potential x 0.25).
Only topics with composite >= {quality_threshold} qualify.
{rejected_section}
## Step 3: Write output

Write your output as valid JSON to `{output_file}` using the Write tool.

### Normal output (1+ topics passed threshold):

Write a JSON array:
```json
[
  {{
    "rank": 1,
    "anchor": "The thread, one coherent thought with real numbers and sources",
    "anchor_source": "Primary source name + URL",
    "connection": "Supporting context from a different angle, or null",
    "connection_source": "Source name + URL, or null",
    "reaction": "First-person honest reaction",
    "open_questions": ["What I genuinely don't know"],
    "do_not_include": ["Other findings to explicitly keep out"],
    "confidence": "HIGH | MEDIUM | LOW | SPECULATIVE",
    "emotional_register": "curious | surprised | skeptical | frustrated | amused | worried",
    "mindpattern_context": "How mindpattern relates, or 'none today'",
    "mindpattern_link": "https://mindpattern.ai",
    "editorial_scores": {{
      "novelty": 8,
      "broad_appeal": 7,
      "thread_potential": 6,
      "composite": 7.2
    }},
    "source_urls": ["url1", "url2"]
  }}
]
```

### Zero-topic output (nothing passed threshold):

```json
{{
  "topics": [],
  "kill_explanation": "Why nothing qualified today"
}}
```
"""
    return prompt


def select_topic(
    db: sqlite3.Connection,
    user_id: str,
    date_str: str,
    *,
    max_retries: int = 3,
) -> dict | None:
    """Select a topic for today's social posts.

    Steps:
    1. Check for any findings (early exit if none)
    2. Build EIC prompt that tells agent to query memory_cli.py
    3. Run agent via run_agent_with_files() with agents/eic.md system prompt
    4. Read JSON output from data/social-drafts/eic-topic.json
    5. Validate: composite score >= quality_threshold
    6. Dedup check against recent posts (memory.social.check_duplicate)
    7. Retry up to max_retries if topic is duplicate or below threshold
    8. Return topic dict or None if no good topic found (kill day)
    """
    from memory.social import check_duplicate

    config = _load_social_config()
    quality_threshold = config.get("eic", {}).get("quality_threshold", 5.0)
    max_topics = config.get("eic", {}).get("max_topics", 3)

    findings = _get_recent_findings(db, date_str)

    if not findings:
        logger.warning("No findings available for EIC — kill day")
        return None

    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / "eic-topic.json")
    rejected_anchors: list[str] = []

    for attempt in range(max_retries):
        logger.info(f"EIC topic selection attempt {attempt + 1}/{max_retries}")

        prompt = _build_eic_agent_prompt(
            date_str=date_str,
            quality_threshold=quality_threshold,
            max_topics=max_topics,
            rejected_anchors=rejected_anchors or None,
        )

        parsed = run_agent_with_files(
            system_prompt_file="agents/eic.md",
            prompt=prompt,
            output_file=output_file,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            task_type="eic",
        )

        if parsed is None:
            logger.error(f"EIC agent returned no output, attempt {attempt + 1}")
            continue

        # Handle kill-day response (dict with "topics" key)
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
                rejected_anchors.append(anchor_text)
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
    """Expand EIC topic into a creative brief via Creative Director agent.

    Uses run_agent_with_files() with agents/creative-director.md as the
    system prompt. The voice guide content is inlined in the prompt so
    the agent has full context. The agent writes its output to
    data/social-drafts/creative-brief.json.

    Returns: {
        editorial_angle, key_message, emotional_register, tone,
        source_attribution, visual_metaphor_direction, platform_hooks,
        do_not_include, mindpattern_link, _eic_topic, source_urls, date
    }
    """
    config = _load_social_config()

    # Read voice guide content to inline in prompt
    voice_guide_path = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"
    voice_guide = ""
    if voice_guide_path.exists():
        voice_guide = voice_guide_path.read_text()

    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / "creative-brief.json")

    prompt = f"""You are the Creative Director for mindpattern. Run in Brief Generation mode.

---

## Voice Guide

{voice_guide}

---

## EIC Approved Topic

```json
{json.dumps(topic, indent=2)}
```

## Date: {date_str}

---

Write the unified creative brief as valid JSON to `data/social-drafts/creative-brief.json` using the Write tool.
Follow the Unified Brief Output Schema from your system prompt (agents/creative-director.md).
"""

    brief = run_agent_with_files(
        system_prompt_file="agents/creative-director.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
        task_type="creative_brief",
    )

    if not brief or not isinstance(brief, dict):
        logger.warning("Creative Director agent returned no output, using fallback")
        return _fallback_brief(topic, date_str, config)

    # Merge EIC topic data into the brief for downstream consumers
    brief["_eic_topic"] = topic
    brief["source_urls"] = topic.get("source_urls", [])
    brief["date"] = date_str

    logger.info(
        f"Creative brief generated: {brief.get('editorial_angle', 'no angle')[:100]}"
    )
    return brief


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
