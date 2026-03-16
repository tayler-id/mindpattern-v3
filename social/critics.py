"""Blind validation + deterministic policy checks for social drafts.

The critic is BLIND -- it sees only the draft text and platform rules, never
the brief, writer reasoning, or creative direction. This is the Zeroshot
pattern: judge the output on its own merits.

Deterministic validation uses PolicyEngine (code-enforced, not LLM judgment).
The expeditor is the final quality gate across all platforms.
"""

import json
import logging
from pathlib import Path

from orchestrator.agents import run_agent_with_files
from policies.engine import PolicyEngine

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


# ── Blind critic review ─────────────────────────────────────────────────


def review_draft(platform: str, draft_text: str) -> dict:
    """Blind critic review -- sees ONLY the text and platform rules.

    Does NOT see the brief, writer reasoning, or creative direction.

    Returns: {verdict: 'APPROVED'|'REVISE', feedback: str, scores: dict}

    Scores: voice_authenticity, platform_fit, engagement_potential (each 1-10)
    """
    # Load voice guide for inline inclusion
    voice_guide_path = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    # Platform-specific rules
    platform_rules = _get_platform_rules(platform)

    output_file = str(
        PROJECT_ROOT / "data" / "social-drafts" / f"{platform}-verdict.json"
    )

    prompt = f"""You are a blind critic. You have NEVER seen the creative brief, the writer's
reasoning, or the editorial direction. You see ONLY the draft text below and
must judge it purely on quality.

## The Draft

{draft_text}

## Platform Rules ({platform})

{platform_rules}

## Voice Guide

{voice_guide}

## Your Task

Evaluate this draft on three dimensions (1-10 each):

1. **voice_authenticity**: Does this sound like a real person? Check for:
   - Banned words/phrases from the voice guide
   - Em dashes (instant fail)
   - At least 2 first-person references (I, my, me, I'm, I've)
   - At least 1 sentence fragment
   - Mixed sentence lengths (burstiness)
   - No snappy triads, no broetry, no throat-clearing openers

2. **platform_fit**: Is this native to {platform}? Check for:
   - Correct length for the platform
   - Appropriate tone and style
   - Required elements (URLs where needed)
   - Would this blend in naturally with real posts on this platform?

3. **engagement_potential**: Would someone care about this post?
   - Is there a genuine reaction or take (not just information)?
   - Does it invite response without engagement-farming?
   - Is it specific enough to be interesting?

## Verdict Rules

- If ANY banned word or banned phrase is present: REVISE
- If em dash character is present: REVISE
- If post exceeds platform character/grapheme limit: REVISE
- If mindpattern is the grammatical subject of any main clause: REVISE
- If any dimension scores below 5: REVISE
- Otherwise: APPROVED

## Output

Write your verdict as a JSON file to: {output_file}

The JSON must have this exact structure:

{{
  "verdict": "APPROVED" or "REVISE",
  "feedback": "If REVISE: specific fixes with exact quotes of what failed. If APPROVED: brief positive note.",
  "scores": {{
    "voice_authenticity": <1-10>,
    "platform_fit": <1-10>,
    "engagement_potential": <1-10>
  }}
}}

Write ONLY the JSON file. No other files, no other output.
"""

    result = run_agent_with_files(
        system_prompt_file=f"agents/{platform}-critic.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Glob", "Grep"],
        task_type="critic",
    )

    # Agent may return None (no output), a raw string (malformed JSON file),
    # or a non-dict JSON value. Normalise to dict or treat as failure.
    if result is not None and not isinstance(result, dict):
        logger.warning(
            f"Critic agent returned non-dict for {platform} "
            f"(type={type(result).__name__}). Attempting JSON parse."
        )
        try:
            parsed = json.loads(result) if isinstance(result, str) else None
            result = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            result = None

    if result is None:
        logger.warning(f"Critic agent failed for {platform} (no output file)")
        return {
            "verdict": "REVISE",
            "feedback": "Critic agent failed to produce output. "
                        "Cannot validate draft quality.",
            "scores": {
                "voice_authenticity": 0,
                "platform_fit": 0,
                "engagement_potential": 0,
            },
        }

    # Validate the result has expected keys
    return {
        "verdict": result.get("verdict", "REVISE"),
        "feedback": result.get("feedback", ""),
        "scores": result.get("scores", {
            "voice_authenticity": 0,
            "platform_fit": 0,
            "engagement_potential": 0,
        }),
    }


# ── Deterministic policy validation ─────────────────────────────────────


def deterministic_validate(platform: str, content: str) -> list[str]:
    """Policy checks that cannot be gamed by prompt injection.

    Uses PolicyEngine with social.json rules.

    Returns list of error strings (empty = valid).

    Checks:
    - Character/grapheme limits per platform
    - Banned words from voice guide
    - Banned patterns (em dashes, rhetorical questions)
    - Required elements (URL for X/Bluesky)
    """
    policy = PolicyEngine.load_social(PROJECT_ROOT / "policies")
    return policy.validate_social_post(platform, content)


# ── Expeditor (final quality gate) ──────────────────────────────────────


def expedite(
    drafts: dict[str, dict],
    brief: dict,
    images: dict,
) -> dict:
    """Expeditor -- final quality gate before approval.

    Consolidates all platform drafts + images into a proof package.
    Runs one agent call to verify coherence across platforms.

    IMPORTANT: If agent call fails, return FAIL (not auto-pass).

    Returns: {verdict: 'PASS'|'FAIL', feedback: str, scores: dict,
              platform_verdicts: dict, proof_package: dict}
    """
    # Build the proof package
    proof_package = {
        "brief": brief,
        "drafts": {},
        "images": images or {},
    }

    for platform, draft_data in drafts.items():
        # draft_data may be a string (after humanization) or a dict (before)
        if isinstance(draft_data, str):
            proof_package["drafts"][platform] = {
                "content": draft_data,
                "iterations": 0,
                "critic_verdict": "APPROVED",
                "policy_errors": [],
            }
        else:
            proof_package["drafts"][platform] = {
                "content": draft_data.get("humanized") or draft_data.get("content", ""),
                "iterations": draft_data.get("iterations", 0),
                "critic_verdict": draft_data.get("critic_verdict", "UNKNOWN"),
                "policy_errors": draft_data.get("policy_errors", []),
            }

    # Load voice guide for inline inclusion
    voice_guide_path = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    # Format proof package sections for the prompt
    brief_json = json.dumps(proof_package.get("brief", {}), indent=2)

    drafts_section = ""
    for platform, data in proof_package.get("drafts", {}).items():
        content = data.get("content", "(empty)")
        iterations = data.get("iterations", 0)
        critic = data.get("critic_verdict", "UNKNOWN")
        errors = data.get("policy_errors", [])

        drafts_section += f"\n### {platform.upper()} Draft\n"
        drafts_section += f"Iterations: {iterations} | Critic: {critic}\n"
        if errors:
            drafts_section += f"Policy errors: {', '.join(errors)}\n"
        drafts_section += f"\n{content}\n"

    images_section = ""
    images_data = proof_package.get("images", {})
    if images_data:
        images_section = "\n## Editorial Art\n"
        for key, path in images_data.items():
            images_section += f"- {key}: {path}\n"
    else:
        images_section = "\n## Editorial Art\nNo images provided.\n"

    # Platform list for per-platform verdicts
    platform_list = list(proof_package.get("drafts", {}).keys())
    platform_verdicts_template = ", ".join(
        f'"{p}": "PASS" or "FAIL"' for p in platform_list
    )

    output_file = str(
        PROJECT_ROOT / "data" / "social-drafts" / "expedite-verdict.json"
    )

    prompt = f"""You are the Expeditor, the last quality gate before content reaches a human.

## Creative Brief

```json
{brief_json}
```

## Platform Drafts
{drafts_section}
{images_section}

## Voice Guide

{voice_guide}

## Your Task

Evaluate the COMPLETE proof package for cross-platform coherence:

1. **Anchor alignment**: All drafts are about the SAME topic from the brief.
2. **No conflicting claims**: Numbers, facts, and sources are consistent across platforms.
3. **Source consistency**: All platforms reference the same primary source(s).
4. **Voice compliance**: Check ALL drafts for banned words, em dashes, banned phrases.
5. **Any draft with policy errors**: Auto-FAIL.

## Verdict Rules

- Any kill switch violation in any draft: FAIL
- Any draft with non-empty policy_errors: FAIL
- Conflicting claims across platforms: FAIL
- All drafts empty or missing: FAIL
- Otherwise: PASS

## Output

Write your verdict as a JSON file to: {output_file}

The JSON must have this exact structure:

{{
  "verdict": "PASS" or "FAIL",
  "feedback": "Brief summary of evaluation.",
  "platform_verdicts": {{ {platform_verdicts_template} }},
  "scores": {{
    "voice_match": <0-10>,
    "framing_authenticity": <0-10>,
    "platform_genre_fit": <0-10>,
    "epistemic_calibration": <0-10>,
    "structural_variation": <0-10>,
    "rhetorical_framework": <0-10>
  }}
}}

Write ONLY the JSON file. No other files, no other output.
"""

    result = run_agent_with_files(
        system_prompt_file="agents/expeditor.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Glob", "Grep"],
        task_type="expeditor",
    )

    # Agent may return None (no output), a raw string (malformed JSON file),
    # or a non-dict JSON value. Normalise to dict or treat as failure.
    if result is not None and not isinstance(result, dict):
        logger.warning(
            f"Expeditor returned non-dict (type={type(result).__name__}). "
            f"Attempting JSON parse."
        )
        try:
            parsed = json.loads(result) if isinstance(result, str) else None
            result = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            result = None

    # CRITICAL: failure = FAIL, not auto-pass
    if result is None:
        logger.error("Expeditor agent failed (no output file). Returning FAIL.")
        return {
            "verdict": "FAIL",
            "feedback": "Expeditor agent failed to produce output. "
                        "Cannot verify cross-platform coherence. "
                        "Failing safe -- do not auto-pass.",
            "platform_verdicts": {p: "FAIL" for p in platform_list},
            "scores": {
                "voice_match": 0,
                "framing_authenticity": 0,
                "platform_genre_fit": 0,
                "epistemic_calibration": 0,
                "structural_variation": 0,
                "rhetorical_framework": 0,
            },
            "proof_package": proof_package,
        }

    return {
        "verdict": result.get("verdict", "FAIL"),
        "feedback": result.get("feedback", ""),
        "platform_verdicts": result.get("platform_verdicts", {}),
        "scores": result.get("scores", {}),
        "proof_package": proof_package,
        # Preserve legacy keys consumed by pipeline.py
        "notes": result.get("feedback", ""),
    }


# ── Platform rules reference ────────────────────────────────────────────


def _get_platform_rules(platform: str) -> str:
    """Return a human-readable summary of platform constraints."""
    rules = {
        "linkedin": (
            "- Sweet spot: 1200-1500 characters\n"
            "- First 2 lines are the hook (truncated after ~210 chars)\n"
            "- No broetry (one sentence per line, double-spaced)\n"
            "- No emoji bullet points, no numbered lists as structure\n"
            "- Must include https://mindpattern.ai at end\n"
            "- Tone: story-shaped lesson, like a coffee chat with a peer\n"
            "- End with a genuine, specific question\n"
            "- Audience: professional/enterprise engineers and leaders"
        ),
        "bluesky": (
            "- HARD LIMIT: 300 characters total (including URLs)\n"
            "- URLs count toward the 300 limit\n"
            "- SINGLE POST ONLY. Never a thread.\n"
            "- Must include https://mindpattern.ai at end\n"
            "- Most technical depth of the 3 platforms\n"
            "- No viral-bait tactics\n"
            "- Conversational, community-oriented, lowercase fine\n"
            "- Tone: delightfully specific micro-take, like posting in a Discord\n"
            "- Audience: technical, skeptical of hype, values substance"
        ),
    }
    return rules.get(platform, f"Unknown platform: {platform}")
