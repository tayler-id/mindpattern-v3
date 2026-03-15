"""Per-platform writing orchestration with the Ralph Loop.

Writer <-> Critic feedback cycle for each platform. Writers get voice exemplars
(RAG) and editorial corrections (DPO) from memory. Critics are BLIND -- they
see only the draft text and platform rules, never the brief or creative
direction. Deterministic policy validation via PolicyEngine runs after the
LLM loop. A final humanizer pass strips residual AI patterns.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.agents import run_claude_prompt

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

PLATFORMS = ["x", "linkedin", "bluesky"]


# ── Public API ───────────────────────────────────────────────────────────


def write_drafts(
    db,
    brief: dict,
    config: dict,
    *,
    platforms: list[str] | None = None,
) -> dict[str, dict]:
    """Write drafts for all platforms in parallel.

    For each platform:
    1. Load voice exemplars from memory (approved posts for this platform)
    2. Load editorial corrections from memory (learn from past edits)
    3. Build writer prompt with: brief, voice guide, exemplars, corrections,
       platform constraints
    4. Run writer (Sonnet)
    5. Run critic BLIND (sees only draft text + platform rules, NOT the brief)
    6. If critic says REVISE and iteration < max_iterations: loop with feedback
    7. Run deterministic policy validation (PolicyEngine)
    8. Run humanizer pass (remove AI patterns)

    Returns: {platform: {content, iterations, critic_verdict, policy_errors,
              humanized}}
    """
    targets = platforms or PLATFORMS
    max_workers = config.get("social", {}).get("max_writer_workers", len(targets))

    # Each thread needs its own DB connection (SQLite thread safety)
    import memory as _memory

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_write_single_platform, None, platform, brief, config): platform
            for platform in targets
        }
        results: dict[str, dict] = {}
        for future in futures:
            platform = futures[future]
            try:
                results[platform] = future.result()
            except Exception as e:
                logger.error(f"Writer failed for {platform}: {e}")
                results[platform] = {
                    "content": "",
                    "iterations": 0,
                    "critic_verdict": "ERROR",
                    "policy_errors": [],
                    "humanized": "",
                    "error": str(e),
                }

    return results


# ── Single-platform Ralph Loop ──────────────────────────────────────────


def _write_single_platform(
    db,
    platform: str,
    brief: dict,
    config: dict,
) -> dict:
    """Write + critique loop for a single platform.

    Returns: {content, iterations, critic_verdict, policy_errors, humanized,
              error}
    """
    from social.critics import deterministic_validate, review_draft

    max_iterations = config.get("social", {}).get("max_iterations", 3)

    # Open a fresh DB connection for this thread (SQLite thread safety)
    import memory as _mem
    thread_db = _mem.get_db()

    # Load voice context from memory
    from memory.social import get_exemplars
    from memory.corrections import recent_corrections

    try:
        exemplars = get_exemplars(thread_db, platform=platform, limit=5)
        corrections = recent_corrections(thread_db, platform=platform, limit=5)
    except Exception:
        exemplars = []
        corrections = []
    finally:
        thread_db.close()

    # Load voice guide once
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    content = ""
    critic_verdict = "REVISE"
    critic_feedback = None
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        # ── Writer ───────────────────────────────────────────────────
        writer_prompt = _build_writer_prompt(
            platform=platform,
            brief=brief,
            exemplars=exemplars,
            corrections=corrections,
            voice_guide=voice_guide,
            iteration=iteration,
            feedback=critic_feedback,
        )

        raw_output, exit_code = run_claude_prompt(
            writer_prompt,
            task_type="writer",
            system_prompt_file=str(PROJECT_ROOT / "agents" / f"{platform}-writer.md"),
        )

        if exit_code != 0:
            logger.warning(f"Writer call failed for {platform} (iteration {iteration})")
            return {
                "content": content,
                "iterations": iteration,
                "critic_verdict": "ERROR",
                "policy_errors": [],
                "humanized": "",
                "error": f"Writer exited {exit_code} on iteration {iteration}",
            }

        content = _extract_draft_text(raw_output)

        # ── Critic (blind) ───────────────────────────────────────────
        review = review_draft(platform, content)
        critic_verdict = review.get("verdict", "REVISE")
        critic_feedback = review.get("feedback", "")

        logger.info(
            f"[{platform}] iteration {iteration}: critic says {critic_verdict} "
            f"(scores: {review.get('scores', {})})"
        )

        if critic_verdict == "APPROVED":
            break

    # ── Deterministic policy validation ──────────────────────────────
    policy_errors = deterministic_validate(platform, content)

    if policy_errors:
        logger.warning(
            f"[{platform}] PolicyEngine found {len(policy_errors)} error(s): "
            f"{policy_errors}"
        )

    # ── Humanizer pass ───────────────────────────────────────────────
    humanized = _humanize(content, platform) if content else ""

    # If humanizer returned empty (call failed), fall back to pre-humanized
    if not humanized and content:
        logger.warning(f"[{platform}] Humanizer returned empty, using raw draft")
        humanized = content

    return {
        "content": content,
        "iterations": iteration,
        "critic_verdict": critic_verdict,
        "policy_errors": policy_errors,
        "humanized": humanized,
        "error": None,
    }


# ── Prompt builders ─────────────────────────────────────────────────────


def _build_writer_prompt(
    platform: str,
    brief: dict,
    exemplars: list[dict],
    corrections: list[dict],
    voice_guide: str,
    iteration: int = 1,
    feedback: str | None = None,
) -> str:
    """Build writer prompt with context.

    Includes: brief, voice exemplars (RAG), editorial corrections (DPO),
    platform constraints. If iteration > 1, includes critic feedback.
    """
    # Brief context
    brief_section = json.dumps(brief, indent=2)

    # Voice exemplars (RAG)
    exemplars_section = ""
    if exemplars:
        exemplars_section = "\n## Voice Exemplars (Real Approved Posts)\n\n"
        exemplars_section += "Study these carefully. Match their rhythm and tone.\n\n"
        for i, ex in enumerate(exemplars, 1):
            exemplars_section += f"### Exemplar {i} ({ex.get('date', 'unknown')})\n"
            exemplars_section += f"{ex.get('content', '')}\n\n"

    # Editorial corrections (DPO)
    corrections_section = ""
    if corrections:
        corrections_section = "\n## Editorial Corrections (Learn From Past Edits)\n\n"
        corrections_section += (
            "These are before/after pairs from past edits. "
            "The 'approved' version is what the human preferred. "
            "Learn from the pattern.\n\n"
        )
        for i, corr in enumerate(corrections, 1):
            corrections_section += f"### Correction {i}\n"
            corrections_section += f"**Original**: {corr.get('original_text', '')}\n"
            corrections_section += f"**Approved**: {corr.get('approved_text', '')}\n"
            if corr.get("reason"):
                corrections_section += f"**Reason**: {corr['reason']}\n"
            corrections_section += "\n"

    # Feedback section (Ralph Loop iteration > 1)
    feedback_section = ""
    if iteration > 1 and feedback:
        feedback_section = f"""
## Critic Feedback (Iteration {iteration - 1})

The critic reviewed your previous draft and said REVISE. Fix these issues:

{feedback}

Do NOT just shuffle the problems around. Fix them directly.
"""

    # Iteration context
    iteration_section = ""
    if iteration > 1:
        iteration_section = (
            f"\n**This is iteration {iteration}.** "
            f"Previous drafts were rejected. Read the feedback above carefully.\n"
        )

    prompt = f"""Write a {platform} post based on the creative brief below.

## Creative Brief

```json
{brief_section}
```

## Voice Guide

{voice_guide}
{exemplars_section}
{corrections_section}
{feedback_section}
{iteration_section}

## Instructions

1. React to the brief's `anchor` + `reaction`. ONE thing, not a synthesis.
2. Follow the voice guide strictly. No banned words, no banned phrases, no em dashes.
3. Match the brief's `confidence` level in your language.
4. Include "https://mindpattern.ai" at the end of the post.
5. Do NOT reference anything in the `do_not_include` list.

Output ONLY the post text. No headers, no metadata, no explanation.
"""
    return prompt


def _humanize(content: str, platform: str) -> str:
    """Remove AI writing patterns via one Sonnet call.

    Patterns to remove: em dashes, rhetorical questions, 'delve', 'landscape',
    'it's worth noting', 'in conclusion', excessive hedging.
    """
    prompt = f"""You are a copy editor removing AI writing artifacts from a {platform} post.

## The Draft

{content}

## Patterns to Fix

Remove or rewrite ANY of these if present:
- Em dashes (--) — replace with periods or commas
- Rhetorical questions used as transitions ("But what does this mean?")
- Words: delve, landscape, tapestry, multifaceted, testament, realm, nuanced, pivotal, robust, seamless, comprehensive, leverage, utilize, foster, embark, illuminate, elucidate, meticulous, unwavering, unprecedented, transformative, groundbreaking, cutting-edge, revolutionary, innovative, intricate, profound, vibrant, whimsical, quintessential
- Phrases: "it's worth noting", "in conclusion", "in summary", "in essence", "furthermore", "moreover", "additionally", "at the forefront of", "harness the power of"
- Excessive hedging ("it should be noted that", "it's important to recognize")
- Throat-clearing openers ("In today's ever-evolving...")
- Snappy triads ("Simple. Powerful. Effective.")
- Summary/conclusion closings

## Rules

- Make minimal changes. Preserve the author's voice and meaning.
- If the draft is clean, return it unchanged.
- Do NOT add new content or expand the post.
- Do NOT change the meaning or angle.
- Keep the same approximate length.
- Preserve "https://mindpattern.ai" at the end.

Output ONLY the cleaned post text. No explanation, no headers.
"""

    output, exit_code = run_claude_prompt(prompt, task_type="humanizer")

    if exit_code != 0:
        logger.warning(f"Humanizer call failed for {platform}, returning original")
        return content

    cleaned = output.strip()
    return cleaned if cleaned else content


# ── Helpers ──────────────────────────────────────────────────────────────


def _extract_draft_text(raw_output: str) -> str:
    """Extract the draft text from writer output.

    Writers are instructed to output only the post text, but may include
    markdown fences or header noise. Strip it down to just the content.
    """
    text = raw_output.strip()

    # If wrapped in markdown code fences, extract inner content
    if text.startswith("```") and text.endswith("```"):
        lines = text.split("\n")
        # Drop first and last fence lines
        inner = "\n".join(lines[1:-1]).strip()
        if inner:
            text = inner

    # If the output has PLATFORM/TYPE header format, extract content between --- markers
    if "PLATFORM:" in text and "---" in text:
        parts = text.split("---")
        if len(parts) >= 3:
            # Content is between the first and second --- markers
            text = parts[1].strip()
        elif len(parts) == 2:
            text = parts[1].strip()

    return text
