"""Disk layer for the public story and entity response caches.

Every response cache in dashboard/routes/api.py is an in-memory dict, so a
restart or deploy used to empty them all, and the first request then paid the
full corpus rebuild. _all_public_stories reads every story JSON on the volume,
measured 5,471ms cold against 1ms warm, and dashboard/warmup.py takes minutes
to refill everything after boot. This module keeps finished response bodies on
the persistent volume, one JSON file per slug under
DATA_DIR/<user>/site-cache/{stories,entities}/, so a restart costs one small
file read instead.

Every file carries an envelope, {"v": schema version, "key": invalidation
key, "body": the exact response dict}. Serving code checks v and key. Any
mismatch, truncation or parse error reads as a miss, falls through to live
compute, and the fresh write overwrites the bad file. A corrupt file is never
served and never raises past this module.

Writes are atomic. The bytes go to a tempfile in the same directory, then
os.replace moves it over the old file, so a process killed mid-write leaves
the previous file intact. Zero-byte artifacts have shipped twice before
(2026-07-27, 2026-08-04) and a reader must never see one from here.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from orchestrator.site_content import normalize_slug

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Nothing on the site should be near 2 MB. A body over the guard is a bug in
# the producer, not a caching problem, so refuse it loudly instead of letting
# one entry dominate the volume.
MAX_BODY_BYTES = 2 * 1024 * 1024

KINDS = ("stories", "entities")


def file_key(source: Path) -> str | None:
    """Invalidation key derived from one source file: its mtime_ns and size.

    Per-item on purpose, not the global data fingerprint. A story whose source
    JSON has not changed keeps its cached response across publishes, so the
    archive stays warm through a nightly sync. The tradeoff: related_paths
    inside an archive story were computed against the corpus as of that
    story's last write and can go stale relative to newer stories. The spec
    accepts that for the archive, and today's stories always have fresh files,
    so they are always fresh.
    """
    try:
        stat = source.stat()
    except OSError:
        return None
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def cache_path(root: Path, kind: str, slug: str) -> Path | None:
    """The file for one cache entry, confined to root/kind.

    The slug goes through normalize_slug before it touches a path, and the
    resolved result must stay inside the cache root. Anything else gets None.
    """
    if kind not in KINDS:
        return None
    try:
        safe_slug = normalize_slug(slug)
    except ValueError:
        return None
    base = (root / kind).resolve()
    candidate = (base / f"{safe_slug}.json").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def read_body(path: Path, key: str) -> dict | None:
    """The cached response body, or None on any miss, mismatch or damage."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    if envelope.get("v") != SCHEMA_VERSION or envelope.get("key") != key:
        return None
    body = envelope.get("body")
    if not isinstance(body, dict):
        return None
    return body


def write_body(path: Path, key: str, body: dict) -> bool:
    """Persist one response body atomically. Returns False instead of raising.

    tempfile.mkstemp in the destination directory, fsync, then os.replace. A
    kill at any point leaves either the old file or the new one, never a
    truncated hybrid the serving path could read.
    """
    try:
        blob = json.dumps({"v": SCHEMA_VERSION, "key": key, "body": body}).encode("utf-8")
    except (TypeError, ValueError):
        logger.warning("site-cache: %s is not JSON serializable, not cached", path.stem)
        return False
    if len(blob) > MAX_BODY_BYTES:
        logger.warning(
            "site-cache: refusing to cache %s, %d bytes is over the %d byte guard",
            path.stem,
            len(blob),
            MAX_BODY_BYTES,
        )
        return False
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    except OSError as exc:
        logger.warning("site-cache: write failed for %s: %s", path.stem, exc)
        return False
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
