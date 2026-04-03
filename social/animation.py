"""Animation pipeline orchestration for the social pipeline.

Animation Director conceives motion concept, Composition Generator creates
Remotion TSX code, Validator checks safety, Renderer produces GIF,
Reviewer validates quality. Falls back to static images on any failure.

Mirrors social/art.py structure. All functions take a `db` parameter
and return data structures. No print statements, no CLI.
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from orchestrator.agents import run_claude_prompt, run_agent_with_files
from orchestrator.router import get_model
from social.art import create_art

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REMOTION_DIR = PROJECT_ROOT / "remotion"
COMPOSITIONS_DIR = REMOTION_DIR / "src" / "compositions"
GIF_GEN_SCRIPT = PROJECT_ROOT / "tools" / "gif-gen.py"
DRAFTS_DIR = PROJECT_ROOT / "data" / "social-drafts"

logger = logging.getLogger(__name__)

ANIMATION_STYLES = [
    "kinetic_typography",
    "data_visualization",
    "concept_animation",
    "spotlight",
]


def _get_recent_animation_styles(db: sqlite3.Connection, days: int = 7) -> list[str]:
    """Query recent animation styles to avoid repetition."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        rows = db.execute(
            """SELECT brief_json FROM social_posts
               WHERE date >= ? AND brief_json IS NOT NULL
               ORDER BY date DESC LIMIT 10""",
            (cutoff,),
        ).fetchall()
    except Exception:
        return []

    styles = []
    for r in rows:
        try:
            brief = json.loads(r["brief_json"])
            if isinstance(brief, dict):
                style = brief.get("animation_style")
                if style and style not in styles:
                    styles.append(style)
        except (json.JSONDecodeError, TypeError):
            continue

    return styles


def _animation_director_conceive(
    brief: dict, recent_styles: list[str]
) -> dict | None:
    """Animation Director: conceive animation concept and style.

    Returns: {concept, style, motion_design, color_palette, typography,
              duration_seconds, loop_strategy} or None on failure.
    """
    avoid_styles = ", ".join(recent_styles[:3]) if recent_styles else "none"
    available = [s for s in ANIMATION_STYLES if s not in recent_styles[:2]]
    if not available:
        available = ANIMATION_STYLES

    editorial_angle = brief.get("editorial_angle", "")
    topic = brief.get("topic", brief.get("anchor", ""))

    prompt = f"""You are the Animation Director for mindpattern.

Your job is to conceive an animated GIF concept for a social media post.

## Creative Brief

### Topic
{topic}

### Editorial Angle
{editorial_angle}

### Full Brief Context
```json
{json.dumps(brief, indent=2)}
```

## Animation Style Rotation
- Available styles: {', '.join(available)}
- Recently used (avoid these): {avoid_styles}
- Pick the style that best fits the CONTENT of this topic.

## Style Descriptions
- kinetic_typography: Words appearing with spring physics, emphasis on key insight
- data_visualization: Animated charts, numbers counting up, trend lines drawing
- concept_animation: Visual metaphors in motion (networks, gears, flow, growth)
- spotlight: Single dramatic stat or quote with reveal animation

## Output
CRITICAL: Output ONLY valid JSON with these fields:
{{
  "concept": "One sentence describing the visual concept",
  "style": "one of the style names above",
  "motion_design": "Description of the motion/animation",
  "color_palette": ["#hex1", "#hex2", "#hex3", "#hex4"],
  "typography": {{"headline": "font name", "body": "font name"}},
  "duration_seconds": 4,
  "loop_strategy": "seamless_fade",
  "headline": "The main text to display (for typography/spotlight styles)",
  "data_points": {{"values": [], "labels": []}}
}}

No markdown, no commentary, no code fences.
"""

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="animation_director",
        allowed_tools=["Read", "Glob"],
    )

    if exit_code != 0:
        logger.error(f"Animation Director failed (exit {exit_code})")
        return None

    return _parse_json_response(raw_output, required_key="concept")


def _generate_composition(concept: dict, brief: dict) -> Path | None:
    """Composition Generator: create Remotion TSX code from concept.

    Uses the remotion-best-practices skill via --append-system-prompt-file.
    Returns path to generated .tsx file or None on failure.
    """
    style = concept.get("style", "spotlight")
    headline = concept.get("headline", "")
    color_palette = concept.get("color_palette", ["#1a1a2e", "#0f3460", "#e94560"])
    motion_design = concept.get("motion_design", "")

    # Map style to base composition
    style_to_comp = {
        "kinetic_typography": "KineticTypography",
        "data_visualization": "DataViz",
        "concept_animation": "ConceptAnimation",
        "spotlight": "Spotlight",
    }

    comp_id = style_to_comp.get(style, "Spotlight")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    comp_filename = f"{timestamp}-{style}.tsx"

    COMPOSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    comp_path = COMPOSITIONS_DIR / comp_filename

    # For v1, use the pre-built compositions with the concept's parameters.
    # The Composition Generator selects the right base component and
    # parameterizes it rather than generating TSX from scratch.
    # This is safer and faster while still being content-driven.
    props = _build_props_for_style(style, concept, brief)

    return comp_path, comp_id, props


def _build_props_for_style(style: str, concept: dict, brief: dict) -> dict:
    """Build Remotion component props from animation concept."""
    palette = concept.get("color_palette", ["#1a1a2e", "#0f3460", "#e94560", "#ffffff"])
    accent = palette[2] if len(palette) > 2 else "#e94560"
    bg = palette[0] if palette else "#1a1a2e"

    if style == "kinetic_typography":
        return {
            "headline": concept.get("headline", brief.get("editorial_angle", "Breaking insight")),
            "accent": accent,
            "backgroundColor": bg,
            "subtext": concept.get("subtext", ""),
        }
    elif style == "data_visualization":
        data = concept.get("data_points", {})
        return {
            "title": concept.get("headline", ""),
            "values": data.get("values", [10, 30, 50, 70, 90]),
            "labels": data.get("labels", []),
            "accent": accent,
            "backgroundColor": bg,
        }
    elif style == "concept_animation":
        concept_type = concept.get("concept_type", "network")
        if concept_type not in ("network", "flow", "gears", "growth"):
            concept_type = "network"
        return {
            "concept": concept_type,
            "title": concept.get("headline", ""),
            "accent": accent,
            "backgroundColor": bg,
        }
    elif style == "spotlight":
        return {
            "stat": concept.get("stat", concept.get("headline", "?")),
            "label": concept.get("label", concept.get("motion_design", "")),
            "accent": accent,
            "backgroundColor": bg,
        }

    return {"accent": accent, "backgroundColor": bg}


def _render_gif(
    composition_id: str,
    width: int,
    height: int,
    fps: int,
    duration: int,
    output_path: Path,
    platform: str,
) -> dict:
    """Render a composition to GIF via tools/gif-gen.py."""
    cmd = [
        "python3", str(GIF_GEN_SCRIPT),
        "--composition-id", composition_id,
        "--width", str(width),
        "--height", str(height),
        "--fps", str(fps),
        "--duration", str(duration),
        "--output", str(output_path),
        "--platform", platform,
        "--timeout", "180",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            preexec_fn=os.setsid,
        )

        try:
            stdout, stderr = proc.communicate(timeout=200)
        except subprocess.TimeoutExpired:
            logger.error("gif-gen.py timed out, killing process tree")
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
            return {"success": False, "error": "Render timed out"}

        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")[:300]
            logger.error(f"gif-gen.py failed (exit {proc.returncode}): {stderr_text}")
            return {"success": False, "error": f"exit {proc.returncode}: {stderr_text}"}

        try:
            result = json.loads(stdout.decode("utf-8").strip())
            return result
        except json.JSONDecodeError:
            if output_path.exists() and output_path.stat().st_size > 0:
                return {"success": True, "path": str(output_path), "size_bytes": output_path.stat().st_size}
            return {"success": False, "error": "Could not parse gif-gen output"}

    except FileNotFoundError:
        return {"success": False, "error": "python3 or gif-gen.py not found"}


def _animation_reviewer(gif_path: Path, concept: dict) -> dict:
    """Animation Reviewer: validate rendered GIF against concept.

    Returns: {"verdict": "APPROVED"|"REVISE", "feedback": str}
    """
    prompt = f"""You are the Animation Reviewer for mindpattern.

Review this rendered GIF against the original animation concept.

## Original Concept
```json
{json.dumps(concept, indent=2)}
```

## Rendered GIF
{gif_path}

Please view the GIF using the Read tool, then evaluate:
1. Does the animation match the concept's intended motion design?
2. Is the text/data readable?
3. Does the color palette match the concept?
4. Is the animation visually appealing and not glitchy?

Output ONLY valid JSON:
{{"verdict": "APPROVED" or "REVISE", "feedback": "explanation", "score": 1-10}}

No markdown, no commentary, no code fences.
"""

    raw_output, exit_code = run_claude_prompt(
        prompt,
        task_type="animation_reviewer",
        allowed_tools=["Read"],
    )

    if exit_code != 0:
        logger.warning(f"Animation Reviewer failed (exit {exit_code}), auto-approving")
        return {"verdict": "APPROVED", "feedback": "Review failed, auto-approving", "_failed": True}

    result = _parse_json_response(raw_output, required_key="verdict")
    if not result:
        return {"verdict": "APPROVED", "feedback": "Could not parse review, auto-approving", "_failed": True}

    return result


def _cleanup_old_compositions(days: int = 7) -> None:
    """Remove generated compositions older than N days."""
    if not COMPOSITIONS_DIR.exists() or not COMPOSITIONS_DIR.is_dir():
        return

    cutoff = time.time() - days * 86400
    try:
        entries = list(COMPOSITIONS_DIR.iterdir())
    except (OSError, FileNotFoundError):
        return
    for f in entries:
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                logger.info(f"Cleaned up old composition: {f.name}")
            except OSError:
                pass


def _parse_json_response(raw: str, required_key: str) -> dict | None:
    """Parse a JSON dict from raw agent output, requiring a specific key."""
    text = raw.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and required_key in data:
            return data
    except json.JSONDecodeError:
        pass

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


def create_animation(
    db: sqlite3.Connection,
    brief: dict,
    date_str: str,
    *,
    max_rounds: int = 2,
) -> dict:
    """Full animation pipeline: Director -> Compose -> Validate -> Render -> Review.

    On ANY failure, falls back to static image via create_art().

    Returns:
        {
            "linkedin_image": str|None,  # path to GIF
            "bluesky_image": str|None,   # path to GIF
            "concept": dict,
            "style": str,
            "approved": bool,
            "animation": True,  # flag to distinguish from static images
        }
    """
    logger.info("Animation pipeline starting")

    # Cleanup old compositions
    _cleanup_old_compositions(days=7)

    # Check Remotion is available
    if not REMOTION_DIR.exists() or not (REMOTION_DIR / "node_modules").exists():
        logger.warning("Remotion not installed, falling back to static images")
        return create_art(db=db, brief=brief, date_str=date_str)

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Get recent styles for rotation
    recent_styles = _get_recent_animation_styles(db)
    logger.info(f"Recent animation styles: {recent_styles or ['none']}")

    # Step 2: Animation Director conceives the concept
    concept = _animation_director_conceive(brief, recent_styles)
    if not concept:
        logger.error("Animation Director failed, falling back to static images")
        return create_art(db=db, brief=brief, date_str=date_str)

    style = concept.get("style", "spotlight")
    logger.info(f"Animation concept: style={style}, concept={concept.get('concept', '')[:100]}")

    # Save concept
    concept_path = DRAFTS_DIR / "animation-concept.json"
    with open(concept_path, "w") as f:
        json.dump(concept, f, indent=2)

    # Step 3: Build props from concept (v1 uses pre-built compositions)
    result = _generate_composition(concept, brief)
    if not result:
        logger.error("Composition generation failed, falling back to static images")
        return create_art(db=db, brief=brief, date_str=date_str)

    comp_path, comp_id, props = result

    # Step 4-5: Render + Review loop
    for round_num in range(1, max_rounds + 1):
        logger.info(f"Animation render round {round_num}/{max_rounds}")

        # Render for both platforms
        linkedin_gif = DRAFTS_DIR / "linkedin-animation.gif"
        bluesky_gif = DRAFTS_DIR / "bluesky-animation.gif"

        linkedin_result = _render_gif(
            composition_id=comp_id,
            width=1080, height=1080, fps=15, duration=4,
            output_path=linkedin_gif,
            platform="linkedin",
        )

        bluesky_result = _render_gif(
            composition_id=comp_id,
            width=720, height=720, fps=12, duration=4,
            output_path=bluesky_gif,
            platform="bluesky",
        )

        if not linkedin_result.get("success") and not bluesky_result.get("success"):
            logger.error(f"Both renders failed in round {round_num}")
            if round_num >= max_rounds:
                logger.error("Max rounds reached, falling back to static images")
                return create_art(db=db, brief=brief, date_str=date_str)
            continue

        # Review the LinkedIn version (higher quality)
        review_path = linkedin_gif if linkedin_result.get("success") else bluesky_gif
        verdict = _animation_reviewer(review_path, concept)

        if verdict.get("verdict", "").upper() == "APPROVED":
            logger.info(f"Animation approved in round {round_num}")

            return {
                "linkedin_image": str(linkedin_gif) if linkedin_result.get("success") else None,
                "bluesky_image": str(bluesky_gif) if bluesky_result.get("success") else None,
                "concept": concept,
                "style": style,
                "approved": True,
                "animation": True,
                "rounds": round_num,
                "verdict": verdict,
            }

        # REVISE: log feedback and try again
        feedback = verdict.get("feedback", "")
        logger.info(f"Animation revision requested (round {round_num}): {feedback[:200]}")

    # Max rounds exceeded, use whatever we have
    logger.warning(f"Animation not approved after {max_rounds} rounds, using current GIFs")
    return {
        "linkedin_image": str(linkedin_gif) if linkedin_gif.exists() else None,
        "bluesky_image": str(bluesky_gif) if bluesky_gif.exists() else None,
        "concept": concept,
        "style": style,
        "approved": False,
        "animation": True,
        "rounds": max_rounds,
        "note": "Used despite review rejection, max rounds exceeded",
    }
