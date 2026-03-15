"""Per-platform writing orchestration with the Ralph Loop.

Writer <-> Critic feedback cycle for each platform. Writers get voice exemplars
(RAG) and editorial corrections (DPO) from memory via the Bash tool
(memory_cli.py). Critics are BLIND -- they see only the draft text and platform
rules, never the brief or creative direction. Deterministic policy validation
via PolicyEngine runs after the LLM loop. A final humanizer pass strips
residual AI patterns.

Agents use file-based I/O: run_agent_with_files() writes drafts to
data/social-drafts/{platform}-draft.md; Python reads the result back.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.agents import run_agent_with_files, run_claude_prompt

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

PLATFORMS = ["bluesky"]

# Voice guide is loaded once at module level (immutable reference text)
_VOICE_GUIDE_PATH = PROJECT_ROOT / "agents" / "voice-guide.md"
_VOICE_GUIDE: str | None = None


def _load_voice_guide() -> str:
    """Lazy-load the voice guide (cached after first call)."""
    global _VOICE_GUIDE
    if _VOICE_GUIDE is None:
        _VOICE_GUIDE = (
            _VOICE_GUIDE_PATH.read_text() if _VOICE_GUIDE_PATH.exists() else ""
        )
    return _VOICE_GUIDE


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
    1. Build agent prompt with brief, voice guide, memory-CLI instructions
    2. Run writer agent via run_agent_with_files() (writes to .md file)
    3. Run blind critic (sees only draft text + platform rules)
    4. If critic says REVISE and iteration < max_iterations: loop with feedback
    5. Run deterministic policy validation (PolicyEngine)
    6. Run humanizer pass (remove AI patterns, include editorial corrections)

    Returns: {platform: {content, iterations, critic_verdict, policy_errors,
              humanized, error}}
    """
    targets = platforms or PLATFORMS
    max_workers = config.get("social", {}).get("max_writer_workers", len(targets))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _write_single_platform, platform, brief, config
            ): platform
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

    content = ""
    critic_verdict = "REVISE"
    critic_feedback = None
    iteration = 0

    output_file = str(
        PROJECT_ROOT / "data" / "social-drafts" / f"{platform}-draft.md"
    )

    for iteration in range(1, max_iterations + 1):
        # ── Writer (agent with file I/O) ──────────────────────────
        writer_prompt = _build_writer_agent_prompt(
            platform=platform,
            brief=brief,
            iteration=iteration,
            feedback=critic_feedback,
        )

        result = run_agent_with_files(
            system_prompt_file=f"agents/{platform}-writer.md",
            prompt=writer_prompt,
            output_file=output_file,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            task_type="writer",
        )

        if result is None:
            logger.warning(
                f"Writer call failed for {platform} (iteration {iteration})"
            )
            return {
                "content": content,
                "iterations": iteration,
                "critic_verdict": "ERROR",
                "policy_errors": [],
                "humanized": "",
                "error": f"Writer returned no output on iteration {iteration}",
            }

        content = result.get("text", "").strip()

        # ── Critic (blind) ────────────────────────────────────────
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
    # Open a fresh DB connection for this thread (SQLite thread safety)
    import memory as _mem

    thread_db = _mem.get_db()
    try:
        humanized = _humanize(content, platform, thread_db) if content else ""
    finally:
        thread_db.close()

    # If humanizer returned empty (call failed), fall back to pre-humanized
    if not humanized and content:
        logger.warning(f"[{platform}] Humanizer returned empty, using raw draft")
        humanized = content

    return {
        "content": humanized,
        "iterations": iteration,
        "critic_verdict": critic_verdict,
        "policy_errors": policy_errors,
        "humanized": True,
        "error": None,
    }


# ── Prompt builders ─────────────────────────────────────────────────────


def _build_writer_agent_prompt(
    platform: str,
    brief: dict,
    iteration: int = 1,
    feedback: str | None = None,
) -> str:
    """Build writer agent prompt with memory-CLI instructions.

    The agent is told to:
    1. Use Bash to call memory_cli.py for exemplars and corrections
    2. Read the voice guide (inlined)
    3. Write the draft to the output file via the Write tool

    On iteration > 1, critic feedback is included in the prompt.
    """
    brief_json = json.dumps(brief, indent=2)
    voice_guide = _load_voice_guide()

    output_file = str(
        PROJECT_ROOT / "data" / "social-drafts" / f"{platform}-draft.md"
    )

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

    prompt = f"""You are a social media writer for the mindpattern brand. Write a {platform} post.

## Step 1: Gather Context from Memory

Run these commands with the Bash tool to get voice exemplars and editorial corrections:

```
python3 memory_cli.py get-exemplars --platform {platform} --limit 5
```

```
python3 memory_cli.py recent-corrections --platform {platform}
```

Study the exemplars carefully. Match their rhythm and tone.
Learn from the corrections — the "approved" version is what the human preferred.

## Step 2: Creative Brief

```json
{brief_json}
```

## Step 3: Voice Guide

{voice_guide}
{feedback_section}
{iteration_section}

## Step 4: Write the Post

Follow these instructions exactly:

1. React to the brief's `anchor` + `reaction`. ONE thing, not a synthesis.
2. Follow the voice guide strictly. No banned words, no banned phrases, no em dashes.
3. Match the brief's `confidence` level in your language.
4. Include "https://mindpattern.ai" at the end of the post.
5. Do NOT reference anything in the `do_not_include` list.

## Step 5: Save Your Draft

Use the Write tool to save ONLY the post text (no headers, no metadata, no
explanation) to this file:

{output_file}
"""
    return prompt


def _humanize(content: str, platform: str, db=None) -> str:
    """Remove AI writing patterns via one Sonnet call.

    Patterns to remove: em dashes, rhetorical questions, 'delve', 'landscape',
    'it's worth noting', 'in conclusion', excessive hedging.

    If a db connection is provided, editorial corrections from memory are
    included in the prompt so the humanizer can learn from past edits.
    """
    # Build corrections section from memory (if db available)
    corrections_section = ""
    if db is not None:
        try:
            from memory.corrections import recent_corrections

            corrections = recent_corrections(db, platform=platform, limit=5)
            if corrections:
                examples = []
                for c in corrections:
                    entry = (
                        f"BEFORE: {c['original_text'][:200]}\n"
                        f"AFTER: {c['approved_text'][:200]}"
                    )
                    if c.get("reason"):
                        entry += f"\nREASON: {c['reason']}"
                    examples.append(entry)
                corrections_section = (
                    "\n\n## Recent Editorial Corrections (learn from these)\n\n"
                    + "\n---\n".join(examples)
                )
        except Exception as e:
            logger.warning(f"Failed to load corrections for humanizer: {e}")

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
{corrections_section}

Output ONLY the cleaned post text. No explanation, no headers.
"""

    output, exit_code = run_claude_prompt(prompt, task_type="humanizer")

    if exit_code != 0:
        logger.warning(f"Humanizer call failed for {platform}, returning original")
        return content

    cleaned = output.strip()
    return cleaned if cleaned else content
