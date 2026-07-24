"""Preflight: Reddit posts via tools/reddit-fetch.py."""

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = (
    "MachineLearning,LocalLLaMA,artificial,singularity,"
    "ChatGPT,ClaudeAI,SaaS,fintech,startups,programming"
)


def _transform(raw: dict) -> dict:
    created = raw.get("created_utc")
    published = ""
    if created:
        try:
            published = datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass

    return make_entry(
        source="reddit",
        source_name=f"r/{raw.get('subreddit', '')}",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=published,
        content_preview=raw.get("selftext", "")[:500],
        metrics={"score": raw.get("score", 0), "comments": raw.get("comments", 0)},
    )


def _parse_stderr_diagnostics(stderr: str) -> list[dict]:
    diagnostics = []
    for line in stderr.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                diagnostics.append(parsed)
                continue
        except json.JSONDecodeError:
            pass
        diagnostics.append({"error": line, "tool": "reddit-fetch"})
    return diagnostics


def _summarize_errors(errors: list[dict]) -> str:
    if not errors:
        return ""
    parts = []
    for error in errors[:3]:
        message = error.get("error", "reddit error")
        context = error.get("context")
        parts.append(f"{message} ({context})" if context else message)
    if len(errors) > 3:
        parts.append(f"{len(errors) - 3} more")
    return "; ".join(parts)


def _transform_opencli(raw: dict) -> dict:
    """Normalize an OpenCLI reddit post into the shared preflight entry shape.

    OpenCLI differs from the public JSON API in two ways that silently
    corrupt entries if copied straight through: the score field is
    `upvotes`, and `subreddit` already carries its own `r/` prefix.
    """
    created = raw.get("created_utc")
    published = ""
    if created:
        try:
            published = datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass

    subreddit = str(raw.get("subreddit", "")).strip()
    if not subreddit.startswith("r/"):
        subreddit = f"r/{subreddit}"

    return make_entry(
        source="reddit",
        source_name=subreddit,
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=published,
        content_preview=(raw.get("selftext") or "")[:500],
        metrics={
            "score": raw.get("upvotes", raw.get("score", 0)),
            "comments": raw.get("comments", 0),
        },
    )


def _fetch_via_opencli(
    subreddits: str, min_score: int, limit: int = 50
) -> tuple[list[dict], list[dict]]:
    """Fetch each subreddit through OpenCLI, which reuses the browser session.

    Returns (entries, errors). One failing subreddit does not sink the rest.
    """
    entries: list[dict] = []
    errors: list[dict] = []
    for name in [s.strip() for s in subreddits.split(",") if s.strip()]:
        cmd = [
            "opencli", "reddit", "subreddit", name,
            "--sort", "top", "--time", "day", "--limit", str(limit),
            "-f", "json",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError) as e:
            errors.append({"error": str(e), "context": f"r/{name}", "tool": "opencli"})
            continue

        if proc.returncode != 0:
            errors.append({
                "error": (proc.stderr or "").strip()[:200] or f"opencli exited {proc.returncode}",
                "context": f"r/{name}",
                "tool": "opencli",
            })
            continue

        try:
            posts = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as e:
            errors.append({"error": f"unparseable opencli output: {e}",
                           "context": f"r/{name}", "tool": "opencli"})
            continue

        for post in posts if isinstance(posts, list) else []:
            if not isinstance(post, dict):
                continue
            score = post.get("upvotes", post.get("score", 0)) or 0
            try:
                if int(score) < min_score:
                    continue
            except (TypeError, ValueError):
                continue
            entries.append(_transform_opencli(post))

    return entries, errors


def fetch_with_diagnostics(
    subreddits: str | None = None,
    min_score: int = 50,
) -> tuple[list[dict], dict]:
    targets = subreddits or DEFAULT_SUBREDDITS

    # OpenCLI first: the public JSON API path below has returned HTTP 403 on
    # every logged run since 2026-06-26 because Reddit blocks unauthenticated
    # .json requests. OpenCLI reuses the browser session via its extension.
    if shutil.which("opencli"):
        items, errors = _fetch_via_opencli(targets, min_score)
        if items:
            return items, {
                "status": "partial" if errors else "ok",
                "reason": _summarize_errors(errors),
                "subreddits": targets,
                "errors": errors,
            }
        if errors:
            logger.warning("opencli reddit returned nothing: %s", _summarize_errors(errors))
        else:
            return [], {
                "status": "empty",
                "reason": "no reddit items",
                "subreddits": targets,
                "errors": [],
            }
        # errors and no items -> fall through to the legacy tool

    cmd = [
        sys.executable, str(TOOLS_DIR / "reddit-fetch.py"),
        "--subreddits", subreddits or DEFAULT_SUBREDDITS,
        "--min-score", str(min_score),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.error("reddit-fetch.py timed out after 120s")
        return [], {
            "status": "timeout",
            "reason": "reddit-fetch.py timed out after 120s",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [],
        }
    except FileNotFoundError as e:
        logger.error(f"reddit-fetch.py dependency missing: {e}")
        return [], {
            "status": "unavailable",
            "reason": f"reddit-fetch.py unavailable: {e}",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [{"error": str(e), "tool": "reddit-fetch"}],
        }
    except Exception as e:
        logger.error(f"reddit-fetch.py failed: {e}")
        return [], {
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [],
        }

    errors = _parse_stderr_diagnostics(proc.stderr or "")
    items = [_transform(item) for item in parse_ndjson(proc.stdout)]
    reason = _summarize_errors(errors)

    if proc.returncode == 0:
        status = "ok" if items else "empty"
        reason = "" if items else "no reddit items"
    elif proc.returncode == 1:
        status = "partial" if items else "failed"
        reason = reason or "reddit-fetch.py reported partial failure"
    elif proc.returncode == 2 and not items:
        status = "unavailable"
        reason = reason or "reddit backend unavailable"
    else:
        status = "failed"
        reason = reason or f"reddit-fetch.py exited {proc.returncode}"

    return items, {
        "status": status,
        "reason": reason,
        "subreddits": subreddits or DEFAULT_SUBREDDITS,
        "errors": errors,
    }


def fetch(subreddits: str | None = None, min_score: int = 50) -> list[dict]:
    items, _diagnostics = fetch_with_diagnostics(
        subreddits=subreddits,
        min_score=min_score,
    )
    return items
