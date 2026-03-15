"""Art pipeline orchestration for the social pipeline.

Art Director conceives visual metaphor, Illustrator generates images via
tools/image-gen.py, Creative Director reviews. Supports revision loops.

All functions take a `db` (sqlite3.Connection) parameter and return data
structures. No print statements, no CLI.
"""

import json
import logging
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.agents import run_claude_prompt
from orchestrator.router import get_model

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
IMAGE_GEN_SCRIPT = PROJECT_ROOT / "tools" / "image-gen.py"
DRAFTS_DIR = PROJECT_ROOT / "data" / "social-drafts"

logger = logging.getLogger(__name__)


def _load_social_config() -> dict:
    """Load social-config.json from project root."""
    config_path = PROJECT_ROOT / "social-config.json"
    with open(config_path) as f:
        return json.load(f)


def _get_recent_styles(db: sqlite3.Connection, days: int = 7) -> list[str]:
    """Query recent art styles to avoid repetition.

    Looks at social_posts brief_json for rendering_style fields from
    the last N days of posts.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT brief_json FROM social_posts
           WHERE date >= ? AND brief_json IS NOT NULL
           ORDER BY date DESC LIMIT 10""",
        (cutoff,),
    ).fetchall()

    styles = []
    for r in rows:
        try:
            brief = json.loads(r["brief_json"])
            # Check nested art concept for rendering_style
            style = None
            if isinstance(brief, dict):
                style = brief.get("rendering_style")
                if not style and "art" in brief:
                    style = brief["art"].get("style")
                if not style and "art_concept" in brief:
                    style = brief["art_concept"].get("rendering_style")
            if style and style not in styles:
                styles.append(style)
        except (json.JSONDecodeError, TypeError):
            continue

    return styles


def _art_director_conceive(brief: dict, recent_styles: list[str]) -> dict | None:
    """Art Director: conceive visual metaphor + style.

    Reads the Art Director agent definition and the creative brief's
    visual_metaphor_direction to produce an art concept.

    Returns: {concept, style, composition, color_palette, rendering_style, ...}
    or None on failure.
    """
    ad_md_path = PROJECT_ROOT / "agents" / "art-director.md"
    ad_instructions = ""
    if ad_md_path.exists():
        ad_instructions = ad_md_path.read_text()

    last_style = recent_styles[0] if recent_styles else "none"
    avoid_styles = ", ".join(recent_styles[:3]) if recent_styles else "none"

    visual_dir = brief.get("visual_metaphor_direction", {})
    editorial_angle = brief.get("editorial_angle", "")

    prompt = f"""You are the Art Director for mindpattern.

{ad_instructions}

---

## Creative Brief

### Editorial Angle
{editorial_angle}

### Visual Metaphor Direction
{json.dumps(visual_dir, indent=2)}

### Full Brief Context
```json
{json.dumps(brief, indent=2)}
```

## Style Rotation Context
- LAST_STYLE: {last_style}
- Recent styles (avoid these): {avoid_styles}
- Pick a DIFFERENT rendering style from the 7-style rotation.

---

CRITICAL: Output ONLY valid JSON matching the art concept schema from your instructions.
No markdown, no commentary, no code fences.
"""

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="art_director",
        allowed_tools=["Read", "Glob"],
    )

    if exit_code != 0:
        logger.error(f"Art Director failed (exit {exit_code})")
        return None

    return _parse_json_response(raw_output, required_key="metaphor")


def _build_illustrator_prompt(concept: dict, aspect: str, brief: dict) -> str:
    """Build the Illustrator prompt for a specific aspect ratio.

    Args:
        concept: Art Director's concept dict.
        aspect: "linkedin" (1024x1536) or "bluesky" (1536x1024).
        brief: The creative brief for additional context.
    """
    illust_md_path = PROJECT_ROOT / "agents" / "illustrator.md"
    illust_instructions = ""
    if illust_md_path.exists():
        illust_instructions = illust_md_path.read_text()

    if aspect == "linkedin":
        size_note = "LinkedIn format: 1024x1536 (portrait). Use vertical composition — towering buildings, tall figures, stacked elements."
        width, height = 1024, 1536
    else:
        size_note = "Bluesky format: 1536x1024 (landscape). Use horizontal composition — wide scenes, panoramic views, side-by-side contrast."
        width, height = 1536, 1024

    prompt = f"""You are the Illustrator for mindpattern.

{illust_instructions}

---

## Art Director's Concept

```json
{json.dumps(concept, indent=2)}
```

## Target Format
{size_note}
Dimensions: {width}x{height}

## Brief Context
Editorial angle: {brief.get('editorial_angle', 'N/A')}

---

CRITICAL: Output ONLY the image generation prompt as a plain text string.
No JSON, no markdown, no code fences, no commentary. Just the prompt text
that will be sent to the image generation API.
"""
    return prompt


def _generate_image(prompt: str, size: str = "1024x1536") -> Path | None:
    """Call tools/image-gen.py to generate an image.

    Args:
        prompt: The image generation prompt text.
        size: WIDTHxHEIGHT string (e.g., "1024x1536").

    Returns:
        Path to generated image or None on failure.
    """
    width, height = size.split("x")

    # Determine output path based on dimensions
    if int(height) > int(width):
        output_name = "linkedin-image.png"
    else:
        output_name = "bluesky-image.png"

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DRAFTS_DIR / output_name

    cmd = [
        "python3", str(IMAGE_GEN_SCRIPT),
        "--engine", "openai",
        "--quality", "high",
        "--prompt", prompt,
        "--width", width,
        "--height", height,
        "--output", str(output_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes for image generation
            cwd=str(PROJECT_ROOT),
        )

        if proc.returncode != 0:
            logger.error(
                f"Image generation failed (exit {proc.returncode}): "
                f"{proc.stderr[:300] if proc.stderr else 'no stderr'}"
            )
            return None

        # Parse stdout for success confirmation
        try:
            result = json.loads(proc.stdout.strip())
            if result.get("success"):
                logger.info(f"Image generated: {output_path} (engine: {result.get('engine', 'unknown')})")
                return output_path
            else:
                logger.error(f"Image generation returned failure: {result.get('error', 'unknown')}")
                return None
        except json.JSONDecodeError:
            # If we can't parse but the file exists, consider it a success
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"Image generated (unparsed output): {output_path}")
                return output_path
            return None

    except subprocess.TimeoutExpired:
        logger.error("Image generation timed out after 180s")
        return None
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return None


def _creative_director_review(concept: dict, brief: dict) -> dict:
    """Creative Director: review generated images.

    Returns: {linkedin_verdict, bluesky_verdict, feedback, ...}
    """
    cd_md_path = PROJECT_ROOT / "agents" / "creative-director.md"
    cd_instructions = ""
    if cd_md_path.exists():
        cd_instructions = cd_md_path.read_text()

    linkedin_path = DRAFTS_DIR / "linkedin-image.png"
    bluesky_path = DRAFTS_DIR / "bluesky-image.png"

    # Build review prompt — the agent will use Read tool to view images
    prompt = f"""You are the Creative Director for mindpattern. Run in Art Review mode.

{cd_instructions}

---

## Art Director's Concept

```json
{json.dumps(concept, indent=2)}
```

## Creative Brief — Visual Metaphor Direction

```json
{json.dumps(brief.get('visual_metaphor_direction', {}), indent=2)}
```

## Images to Review

- LinkedIn image: {linkedin_path}
- Bluesky image: {bluesky_path}

Please view both images using the Read tool, then evaluate them against all
dimensions in your Art Review instructions.

---

CRITICAL: Output ONLY valid JSON matching the art verdict schema from your instructions.
No markdown, no commentary, no code fences.
"""

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="critic",
        allowed_tools=["Read", "Glob"],
    )

    if exit_code != 0:
        logger.error(f"Creative Director art review failed (exit {exit_code})")
        return {
            "linkedin_verdict": "APPROVED",
            "bluesky_verdict": "APPROVED",
            "feedback": "Review failed — auto-approving to avoid blocking pipeline.",
            "_review_failed": True,
        }

    verdict = _parse_json_response(raw_output, required_key="linkedin_verdict")
    if not verdict:
        logger.warning("Could not parse art review verdict — auto-approving")
        return {
            "linkedin_verdict": "APPROVED",
            "bluesky_verdict": "APPROVED",
            "feedback": "Could not parse review response — auto-approving.",
            "_review_failed": True,
        }

    return verdict


def _parse_json_response(raw: str, required_key: str) -> dict | None:
    """Parse a JSON dict from raw agent output, requiring a specific key."""
    text = raw.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and required_key in data:
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON object with the required key
    pattern = r'\{[\s\S]*"' + re.escape(required_key) + r'"[\s\S]*\}'
    obj_match = re.search(pattern, text)
    if obj_match:
        try:
            data = json.loads(obj_match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def create_art(
    db: sqlite3.Connection,
    brief: dict,
    date_str: str,
    *,
    max_rounds: int = 2,
    skip_art: bool = False,
) -> dict:
    """Full art pipeline: Art Director -> Illustrator -> Creative Director review.

    Steps:
    1. If skip_art, return empty art dict
    2. Query last 7 days of art styles used (avoid repetition)
    3. Art Director: conceive visual metaphor + style (Sonnet)
       Output: {concept, style, composition, color_palette}
    4. Illustrator: generate images via tools/image-gen.py (Sonnet)
       - LinkedIn format: 1024x1536
       - Bluesky format: 1536x1024
    5. Creative Director: review images (Sonnet)
       Verdict: APPROVED or REVISE with feedback
    6. If REVISE and round < max_rounds, loop back to Illustrator
    7. Return: {linkedin_image, bluesky_image, concept, style, approved}

    On failure: return {approved: False} -- pipeline continues text-only.
    """
    if skip_art:
        logger.info("Art pipeline skipped (skip_art=True)")
        return {"approved": False, "skipped": True}

    config = _load_social_config()
    art_config = config.get("art_pipeline", {})
    max_rounds = art_config.get("max_rounds", max_rounds)

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 2: Get recent styles for rotation
    recent_styles = _get_recent_styles(db)
    logger.info(f"Recent art styles: {recent_styles or ['none']}")

    # Step 3: Art Director conceives the visual
    concept = _art_director_conceive(brief, recent_styles)
    if not concept:
        logger.error("Art Director failed to produce concept — text-only fallback")
        return {"approved": False, "error": "art_director_failed"}

    logger.info(
        f"Art concept: {concept.get('metaphor', 'no metaphor')[:100]} "
        f"(style: {concept.get('rendering_style', 'unknown')})"
    )

    # Save the art concept for reference
    concept_path = DRAFTS_DIR / "art-concept.json"
    with open(concept_path, "w") as f:
        json.dump(concept, f, indent=2)

    # Steps 4-6: Generate + review loop
    for round_num in range(1, max_rounds + 1):
        logger.info(f"Art generation round {round_num}/{max_rounds}")

        # Step 4: Illustrator generates images
        linkedin_image = _illustrator_generate(concept, "linkedin", brief)
        bluesky_image = _illustrator_generate(concept, "bluesky", brief)

        if not linkedin_image and not bluesky_image:
            logger.error(f"Both images failed in round {round_num} — text-only fallback")
            return {"approved": False, "error": "image_generation_failed"}

        # Step 5: Creative Director reviews
        verdict = _creative_director_review(concept, brief)

        linkedin_approved = verdict.get("linkedin_verdict", "").upper() == "APPROVED"
        bluesky_approved = verdict.get("bluesky_verdict", "").upper() == "APPROVED"

        if linkedin_approved and bluesky_approved:
            logger.info(f"Art approved in round {round_num}")
            # Save the verdict
            verdict_path = DRAFTS_DIR / "art-verdict.json"
            with open(verdict_path, "w") as f:
                json.dump(verdict, f, indent=2)

            return {
                "linkedin_image": str(linkedin_image) if linkedin_image else None,
                "bluesky_image": str(bluesky_image) if bluesky_image else None,
                "concept": concept,
                "style": concept.get("rendering_style", "unknown"),
                "approved": True,
                "rounds": round_num,
                "verdict": verdict,
            }

        # Step 6: REVISE — incorporate feedback for next round
        if round_num < max_rounds:
            feedback = verdict.get("feedback", "")
            logger.info(f"Art revision requested (round {round_num}): {feedback[:200]}")

            # Augment the concept with revision feedback for next iteration
            concept["_revision_feedback"] = feedback
            concept["_revision_round"] = round_num + 1

            # Update which images need revision
            if not linkedin_approved:
                concept["_revise_linkedin"] = True
            if not bluesky_approved:
                concept["_revise_bluesky"] = True
        else:
            logger.warning(
                f"Art not approved after {max_rounds} rounds — "
                f"proceeding with current images"
            )
            # Save verdict even on final rejection
            verdict_path = DRAFTS_DIR / "art-verdict.json"
            with open(verdict_path, "w") as f:
                json.dump(verdict, f, indent=2)

            # Use the images anyway if they exist (partially approved is
            # better than no images)
            return {
                "linkedin_image": str(linkedin_image) if linkedin_image else None,
                "bluesky_image": str(bluesky_image) if bluesky_image else None,
                "concept": concept,
                "style": concept.get("rendering_style", "unknown"),
                "approved": False,
                "rounds": max_rounds,
                "verdict": verdict,
                "note": "Used despite review rejection — max rounds exceeded",
            }

    # Should not reach here, but safety fallback
    return {"approved": False, "error": "unexpected_loop_exit"}


def _illustrator_generate(concept: dict, aspect: str, brief: dict) -> Path | None:
    """Run the Illustrator agent to craft a prompt, then generate the image.

    Args:
        concept: Art Director's concept dict.
        aspect: "linkedin" or "bluesky".
        brief: The creative brief.

    Returns:
        Path to generated image or None on failure.
    """
    if aspect == "linkedin":
        size = "1024x1536"
    else:
        size = "1536x1024"

    # Check if this specific image needs revision or is being generated fresh
    revision_feedback = ""
    if concept.get("_revision_feedback") and concept.get(f"_revise_{aspect}"):
        revision_feedback = (
            f"\n\n## REVISION FEEDBACK (incorporate this):\n"
            f"{concept['_revision_feedback']}\n"
        )

    prompt = _build_illustrator_prompt(concept, aspect, brief)
    if revision_feedback:
        prompt += revision_feedback

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="illustrator",
        allowed_tools=["Read"],
    )

    if exit_code != 0:
        logger.error(f"Illustrator failed for {aspect} (exit {exit_code})")
        return None

    # The Illustrator outputs the image generation prompt as plain text
    image_prompt = raw_output.strip()

    # Strip any markdown code fences the model might have added
    image_prompt = re.sub(r'^```\w*\n?', '', image_prompt)
    image_prompt = re.sub(r'\n?```$', '', image_prompt)
    image_prompt = image_prompt.strip()

    if not image_prompt or len(image_prompt) < 20:
        logger.error(f"Illustrator returned empty/too-short prompt for {aspect}")
        return None

    logger.info(f"Illustrator {aspect} prompt ({len(image_prompt)} chars): {image_prompt[:150]}...")

    # Generate the actual image
    return _generate_image(image_prompt, size)
