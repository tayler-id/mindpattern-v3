"""Fly.io synchronization — replaces sync-to-fly.sh.

Bundles memory.db + today's reports into a tar.gz, uploads via flyctl sftp,
and restarts the app. ONE upload per user instead of 30 separate connections.
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def _flyctl_bin() -> str:
    """Resolve the flyctl binary.

    The pipeline runs under launchd, whose PATH does not include the default
    flyctl install dir (~/.fly/bin), so a bare "flyctl" lookup fails with
    FileNotFoundError. Prefer PATH, then fall back to the standard install
    location before giving up with the bare name (preserves prior behaviour).
    """
    found = shutil.which("flyctl")
    if found:
        return found
    fallback = os.path.expanduser("~/.fly/bin/flyctl")
    if os.path.exists(fallback):
        return fallback
    return "flyctl"


FLYCTL = _flyctl_bin()


def _pipeline_secret() -> str:
    """Shared secret for the HTTPS upload path (env, else local secret file)."""
    secret = os.environ.get("MP_PIPELINE_SECRET", "").strip()
    if secret:
        return secret
    try:
        return (Path.home() / ".mindpattern-pipeline-secret").read_text().strip()
    except OSError:
        return ""


def _refuse_in_sandbox(action: str) -> None:
    """Hard guard for autonomous-routine sandboxes. Checked via env on
    purpose — no harness import, this module stays dependency-free."""
    if os.environ.get("MP_SANDBOX") == "1":
        raise RuntimeError(
            f"MP_SANDBOX=1: refusing {action} (autonomous sandbox active)"
        )


def upload_bundle_http(
    bundle_path: Path,
    *,
    user_id: str,
    app_url: str = "https://mindpattern.fly.dev",
    attempts: int = 3,
) -> dict:
    """POST the bundle to the app's /api/sync/bundle over Fly's HTTP edge.

    No flyctl, no WireGuard: this rides the production anycast path with a
    sha256 the server verifies before extracting. Preferred over sftp since
    the 2026-07-02 tunnel truncation incident.
    """
    _refuse_in_sandbox("HTTP bundle upload to Fly")
    import hashlib
    import http.client
    import ssl
    from urllib.parse import urlparse

    secret = _pipeline_secret()
    if not secret:
        return {"success": False, "error": "no pipeline secret available"}

    digest = hashlib.sha256()
    size = 0
    with open(bundle_path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    sha256 = digest.hexdigest()

    parsed = urlparse(app_url)
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            conn = http.client.HTTPSConnection(
                parsed.netloc, timeout=600, context=ssl.create_default_context()
            )
            with open(bundle_path, "rb") as body:
                conn.request(
                    "POST",
                    f"/api/sync/bundle?user={user_id}",
                    body=body,
                    headers={
                        "X-Pipeline-Secret": secret,
                        "X-Bundle-Sha256": sha256,
                        "Content-Length": str(size),
                        "Content-Type": "application/gzip",
                    },
                )
            response = conn.getresponse()
            payload = response.read().decode("utf-8", "replace")
            conn.close()
            if response.status == 200:
                return {"success": True, "bytes_uploaded": size, "sha256": sha256}
            last_error = f"HTTP {response.status}: {payload[:200]}"
            log.warning("HTTP sync upload attempt %d failed: %s", attempt, last_error)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            log.warning("HTTP sync upload attempt %d failed: %s", attempt, last_error)
    return {"success": False, "error": last_error}


def _fly_env() -> dict:
    """Subprocess env for flyctl with the auth token bridged from config.

    flyctl 0.4.x stopped reading the legacy ``access_token`` field in
    ~/.fly/config.yml (auto-update, 2026-07), which silently broke sync with
    "no access token available" while the stored token remained valid.
    Passing it as FLY_API_TOKEN works on every flyctl version.
    """
    env = dict(os.environ)
    if env.get("FLY_API_TOKEN") or env.get("FLY_ACCESS_TOKEN"):
        return env
    config_path = Path(os.path.expanduser("~/.fly/config.yml"))
    try:
        for line in config_path.read_text().splitlines():
            if line.startswith("access_token:"):
                token = line.split(":", 1)[1].strip().strip('"')
                if token:
                    env["FLY_API_TOKEN"] = token
                break
    except OSError:
        pass
    return env


def sync_to_fly(
    user_id: str,
    data_dir: Path,
    *,
    app_name: str = "mindpattern",
    traces_conn=None,
) -> dict:
    """Bundle memory.db + today's reports into tar.gz, upload via flyctl sftp.

    ONE upload per user (not 30 separate connections).

    Args:
        user_id: User identifier (e.g. 'ramsay').
        data_dir: Base data directory containing {user_id}/memory.db and
                  ../reports/{user_id}/ structure.
        app_name: Fly.io app name (default 'mindpattern').
        traces_conn: Optional traces.db connection for logging.

    Returns:
        Dict with keys: success, bytes_uploaded, files_included, error.
    """
    _refuse_in_sandbox("Fly sync")
    start = time.monotonic()
    # Use LOCAL date — reports are named with local date by the pipeline
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Resolve paths
    db_path = data_dir / user_id / "memory.db"
    reports_dir = data_dir.parent / "reports" / user_id

    if not db_path.exists():
        return {
            "success": False,
            "bytes_uploaded": 0,
            "files_included": 0,
            "error": f"No memory.db found at {db_path}",
        }

    # Step 1: WAL checkpoint to flush writes on both databases
    checkpoint_result = _wal_checkpoint(db_path)
    if not checkpoint_result["success"]:
        log.warning("WAL checkpoint failed for memory.db %s: %s", user_id, checkpoint_result["error"])
        # Continue anyway — the DB is still readable

    traces_path = data_dir / user_id / "traces.db"
    if traces_path.exists():
        traces_ckpt = _wal_checkpoint(traces_path)
        if not traces_ckpt["success"]:
            log.warning("WAL checkpoint failed for traces.db %s: %s", user_id, traces_ckpt["error"])

    # Step 2: Create bundle
    try:
        bundle_path = create_bundle(user_id, data_dir, reports_dir, date_str)
    except Exception as e:
        return {
            "success": False,
            "bytes_uploaded": 0,
            "files_included": 0,
            "error": f"Bundle creation failed: {e}",
        }

    bundle_size = bundle_path.stat().st_size
    # Count files in bundle
    with tarfile.open(bundle_path, "r:gz") as tf:
        files_included = len(tf.getnames())

    # Step 3: Preferred path — HTTPS upload straight to the app (the server
    # verifies sha256 and extracts). Falls back to the sftp path only when
    # the endpoint or secret is unavailable.
    http_result = upload_bundle_http(bundle_path, user_id=user_id)
    if http_result.get("success"):
        bundle_path.unlink(missing_ok=True)
        result = {
            "success": True,
            "bytes_uploaded": http_result["bytes_uploaded"],
            "files_included": files_included,
            "transport": "https",
            "error": None,
        }
        if traces_conn:
            try:
                traces_conn.execute(
                    "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
                    (
                        f"sync-{date_str}",
                        "fly_sync",
                        json.dumps({
                            "user_id": user_id,
                            "bytes_uploaded": result["bytes_uploaded"],
                            "files_included": files_included,
                            "transport": "https",
                        }),
                    ),
                )
                traces_conn.commit()
            except Exception as e:
                log.debug(f"Failed to log sync event: {e}")
        return result
    log.warning("HTTPS sync path unavailable (%s); falling back to sftp", http_result.get("error"))

    remote_base = f"/data/{user_id}"
    _fly_ssh(app_name, f"mkdir -p {remote_base} /data/reports/{user_id}/agents")

    # Step 4: Upload bundle
    remote_bundle = f"{remote_base}/sync-bundle.tar.gz"
    upload_result = upload_bundle(bundle_path, remote_bundle, app_name)

    if not upload_result["success"]:
        log.warning(
            "Single-shot upload failed (%s) — retrying via chunked upload",
            upload_result.get("error"),
        )
        _fly_ssh(app_name, f"rm -f {remote_bundle}")
        upload_result = upload_bundle_chunked(bundle_path, remote_bundle, app_name)
    if not upload_result["success"]:
        bundle_path.unlink(missing_ok=True)
        return {
            "success": False,
            "bytes_uploaded": 0,
            "files_included": files_included,
            "error": f"Upload failed: {upload_result['error']}",
        }

    # Non-zero once an extract leaves empty JSON behind: the run still ships
    # its newsletter, but the public story list is stale and the caller must
    # not record a clean sync.
    artifacts_empty = 0

    # Step 5: Verify the upload arrived intact before extracting. A machine
    # restart (deploy, scale) mid-transfer leaves a truncated bundle that
    # tar fails on with "Unexpected EOF"; retry the upload once.
    size_result = _fly_ssh(app_name, f"wc -c < {remote_bundle}")
    remote_size = int(size_result["output"].split()[0]) if (
        size_result["success"] and size_result["output"].strip().split()
    ) else -1
    if remote_size != bundle_size:
        log.warning(
            "Remote bundle size %s != local %s — retrying via chunked upload",
            remote_size, bundle_size,
        )
        # flyctl 0.4.58 sftp truncates large single puts deterministically;
        # sub-6MB chunks reassembled remotely land intact.
        _fly_ssh(app_name, f"rm -f {remote_bundle}")
        upload_result = upload_bundle_chunked(bundle_path, remote_bundle, app_name)
        size_result = _fly_ssh(app_name, f"wc -c < {remote_bundle}")
        remote_size = int(size_result["output"].split()[0]) if (
            size_result["success"] and size_result["output"].strip().split()
        ) else -1

    if remote_size != bundle_size:
        extract_result = {
            "success": False,
            "error": f"bundle truncated after retry (remote {remote_size}, local {bundle_size})",
        }
        _fly_ssh(app_name, f"rm -f {remote_bundle}")
    else:
        # Step 6: Extract bundle on remote. See _extract_command for why the
        # stale WAL has to go first.
        #
        # tar needs far longer than a status probe: the bundle passed 50 MB in
        # July 2026 and unpacking ~2,300 files on shared-cpu-2x runs past the
        # 60s default. A killed tar does not fail cleanly, it leaves the files
        # it had not reached yet at zero bytes, which is how 2026-07-27 shipped
        # 86 empty story files that the public API then served as nothing.
        extract_result = _fly_ssh(
            app_name,
            _extract_command(remote_bundle, user_id),
            timeout=600,
        )

        # Extraction reporting success is not proof the artifacts survived, so
        # look for the signature of a half-finished unpack before trusting it.
        # The SFTP fallback below only re-sends .md reports and the databases,
        # so a broken unpack of the site-* JSON would otherwise go unnoticed.
        if extract_result["success"] and _count_empty_artifacts(app_name, user_id):
            # A timed-out tar leaves the bundle in place: `rm -f` only runs on
            # tar's success, so re-extracting can still repair it where it sits.
            log.warning("Zero-byte JSON artifacts after extract — re-extracting")
            extract_result = _fly_ssh(
                app_name,
                _extract_command(remote_bundle, user_id),
                timeout=600,
            )
            empty_count = _count_empty_artifacts(app_name, user_id)
            if empty_count:
                artifacts_empty = empty_count
                log.error(
                    "Re-extract still left %d zero-byte JSON artifact(s) on %s; "
                    "the public site will serve a stale story list until this "
                    "syncs cleanly", empty_count, app_name,
                )
                extract_result = {
                    "success": False,
                    "error": f"{empty_count} zero-byte JSON artifacts after re-extract",
                }

    if not extract_result["success"]:
        log.warning(f"Bundle extraction failed: {extract_result['error']}. Falling back to direct SFTP.")
        # Fallback: upload reports directly via SFTP (more reliable)
        for report_file in sorted(reports_dir.glob("????-??-??.md")):
            _fly_sftp_put(app_name, str(report_file), f"/data/reports/{user_id}/{report_file.name}")
        # Upload DBs directly — and VERIFY each landed at the expected size.
        # The databases are what the dashboard reads; before this, a 47 MB file
        # silently dropped mid-transfer by the SFTP fallback over a flaky tunnel
        # still returned "success", leaving the dashboard stale for the whole
        # day (the recurring "didn't sync to Fly" bug). Verify + retry once, and
        # fail loudly if it still won't land so the sync-only retry path kicks in.
        traces_path_local = data_dir / user_id / "traces.db"
        for db_name, db_local in (("memory.db", db_path), ("traces.db", traces_path_local)):
            if not db_local.exists():
                continue
            if not _put_and_verify(app_name, db_local, f"/data/{user_id}/{db_name}"):
                bundle_path.unlink(missing_ok=True)
                return {
                    "success": False,
                    "bytes_uploaded": 0,
                    "files_included": files_included,
                    "error": f"fallback SFTP could not land {db_name} at expected size",
                }
        # Stale sidecars are just as fatal on the fallback path
        _fly_ssh(
            app_name,
            f"cd /data && rm -f {user_id}/memory.db-wal {user_id}/memory.db-shm "
            f"{user_id}/traces.db-wal {user_id}/traces.db-shm",
        )

    # Clean up local bundle
    bundle_path.unlink(missing_ok=True)

    latency_ms = int((time.monotonic() - start) * 1000)

    # Log to traces if available
    if traces_conn:
        try:
            traces_conn.execute(
                "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
                (
                    f"sync-{date_str}",
                    "fly_sync",
                    json.dumps({
                        "user_id": user_id,
                        "bytes_uploaded": bundle_size,
                        "files_included": files_included,
                        "latency_ms": latency_ms,
                    }),
                ),
            )
            traces_conn.commit()
        except Exception as e:
            log.debug(f"Failed to log sync event: {e}")

    if artifacts_empty:
        return {
            "success": False,
            "bytes_uploaded": bundle_size,
            "files_included": files_included,
            "error": (
                f"{artifacts_empty} zero-byte JSON artifacts on {app_name}; "
                "public story list is stale"
            ),
        }

    return {
        "success": True,
        "bytes_uploaded": bundle_size,
        "files_included": files_included,
        "error": None,
    }


def _count_empty_artifacts(app_name: str, user_id: str) -> int:
    """Count zero-byte JSON artifacts under the user's remote reports tree.

    A tar killed by its timeout leaves every file it had not reached yet at
    zero bytes. The public story API skips those silently, so the site drops a
    day of stories while the sync still looks like it worked (2026-07-27).
    """
    result = _fly_ssh(
        app_name,
        f"find /data/reports/{user_id} -name '*.json' -size 0 | wc -l",
    )
    if not result["success"] or not result["output"].strip().split():
        return 0
    try:
        return int(result["output"].split()[0])
    except ValueError:
        return 0


def create_bundle(
    user_id: str,
    data_dir: Path,
    reports_dir: Path,
    date_str: str,
) -> Path:
    """Create tar.gz bundle of memory.db + traces.db + today's report.

    Bundle structure mirrors the remote /data/ layout:
        {user_id}/memory.db
        {user_id}/traces.db
        {user_id}/mindpattern/*.md
        reports/{user_id}/YYYY-MM-DD.md
        reports/{user_id}/agents/*.md
        reports/{user_id}/site-*/**/*.json  (Rabbit Hole artifacts)
        reports/{user_id}/arcs/*.json

    Args:
        user_id: User identifier.
        data_dir: Base data directory containing {user_id}/memory.db.
        reports_dir: Directory containing report .md files for the user.
        date_str: ISO date string for today (e.g. '2026-03-14').

    Returns:
        Path to the created tar.gz file in a temp directory.
    """
    db_path = data_dir / user_id / "memory.db"
    traces_path = data_dir / user_id / "traces.db"
    bundle_path = Path(tempfile.mktemp(suffix=".tar.gz", prefix=f"sync-{user_id}-"))

    # Snapshot the databases via the SQLite backup API instead of taring
    # the live files — a write landing mid-tar produces a torn copy that
    # the dashboard then serves (audit: sync.py live-file tar).
    snap_dir = Path(tempfile.mkdtemp(prefix=f"sync-snap-{user_id}-"))
    try:
        with tarfile.open(bundle_path, "w:gz") as tf:
            # Add memory.db (consistent snapshot)
            if db_path.exists():
                snap = snap_dir / "memory.db"
                _snapshot_db(db_path, snap)
                tf.add(str(snap), arcname=f"{user_id}/memory.db")

            # Add traces.db (pipeline runs, agent runs, events, etc.)
            if traces_path.exists():
                snap = snap_dir / "traces.db"
                _snapshot_db(traces_path, snap)
                tf.add(str(snap), arcname=f"{user_id}/traces.db")

            # Add ALL date-named reports (not just today's — catches missed syncs)
            for report_file in sorted(reports_dir.glob("????-??-??.md")):
                tf.add(str(report_file), arcname=f"reports/{user_id}/{report_file.name}")

            # Add agent sub-reports
            agents_dir = reports_dir / "agents"
            if agents_dir.is_dir():
                for md_file in sorted(agents_dir.glob("*.md")):
                    tf.add(str(md_file), arcname=f"reports/{user_id}/agents/{md_file.name}")

            # Add Rabbit Hole content-machine artifacts (site-stories,
            # site-dossiers, site-issues, arcs, …) — the public site API on
            # Fly serves these JSON files, so each daily run must ship them
            artifact_dirs = sorted(reports_dir.glob("site-*")) + [reports_dir / "arcs"]
            for artifact_dir in artifact_dirs:
                if not artifact_dir.is_dir():
                    continue
                if artifact_dir.name == "site-backfill-claims":
                    continue  # local work-coordination state, never public
                for json_file in sorted(artifact_dir.rglob("*.json")):
                    rel = json_file.relative_to(reports_dir)
                    tf.add(str(json_file), arcname=f"reports/{user_id}/{rel}")

            # Add vault identity files (voice.md, soul.md, …) — the Fly.io Slack
            # bot reads these for tone/persona when drafting posts
            vault_dir = data_dir / user_id / "mindpattern"
            if vault_dir.is_dir():
                for md_file in sorted(vault_dir.glob("*.md")):
                    tf.add(str(md_file), arcname=f"{user_id}/mindpattern/{md_file.name}")
    finally:
        shutil.rmtree(snap_dir, ignore_errors=True)

    return bundle_path


def _snapshot_db(db_path: Path, dest: Path) -> None:
    """Consistent point-in-time copy via the SQLite backup API.

    Safe against concurrent writers (WAL included) — unlike copying or
    taring the live file.
    """
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


CHUNK_BYTES = 1024 * 1024  # small puts survive flyctl 0.4.58; >~2MB truncate


def _extract_command(remote_bundle: str, user_id: str) -> str:
    """Shell to unpack a synced bundle on the remote volume.

    The stale -wal/-shm sidecars are removed BEFORE tar runs, not after.
    Order is the whole point of this function. tar overwrites memory.db in
    place, so a WAL left from the previous database sits beside a fresh main
    file, and SQLite replays those frames into it. That is what produced
    `database disk image is malformed` on 2026-08-23, which took /healthz to
    500, stopped Fly's proxy routing to the machine, and locked the safe HTTP
    sync out of the very volume it needed to repair.

    `sync_upload.receive_sync_bundle` unlinks the sidecars before extractall
    for the same reason, which is why the HTTP path never corrupted anything.

    The bundle itself is still removed after tar and gated on tar succeeding: a
    timed-out extract must leave its source in place so it can be retried where
    it sits.
    """
    sidecars = " ".join(
        f"{user_id}/{db}{suffix}"
        for db in ("memory.db", "traces.db")
        for suffix in ("-wal", "-shm")
    )
    return (
        f"cd /data && rm -f {sidecars} "
        f"&& tar xzf {remote_bundle} "
        f"&& rm -f {remote_bundle}"
    )


def upload_bundle_chunked(bundle_path: Path, remote_path: str, app_name: str) -> dict:
    """Upload a large file as sub-6MB chunks and reassemble remotely.

    Works around flyctl 0.4.58 sftp truncating large single puts at a
    deterministic boundary (observed 2026-07-02).
    """
    import tempfile

    local_size = bundle_path.stat().st_size
    chunk_dir = Path(tempfile.mkdtemp(prefix="fly-chunks-"))
    chunk_paths: list[Path] = []
    try:
        with open(bundle_path, "rb") as source:
            index = 0
            while True:
                blob = source.read(CHUNK_BYTES)
                if not blob:
                    break
                chunk = chunk_dir / f"chunk.{index:04d}"
                chunk.write_bytes(blob)
                chunk_paths.append(chunk)
                index += 1

        remote_dir = f"{remote_path}.chunks"
        _fly_ssh(app_name, f"rm -rf {remote_dir} && mkdir -p {remote_dir}")
        for chunk in chunk_paths:
            remote_chunk = f"{remote_dir}/{chunk.name}"
            landed = False
            for attempt in (1, 2):
                result = upload_bundle(chunk, remote_chunk, app_name)
                if not result.get("success"):
                    continue
                size_result = _fly_ssh(app_name, f"wc -c < {remote_chunk}")
                remote_size = int((size_result.get("output") or "0").strip() or 0)
                if remote_size == chunk.stat().st_size:
                    landed = True
                    break
                _fly_ssh(app_name, f"rm -f {remote_chunk}")
            if not landed:
                return {"success": False, "error": f"chunk {chunk.name} would not land intact"}

        _fly_ssh(app_name, f"cat {remote_dir}/chunk.* > {remote_path} && rm -rf {remote_dir}")
        size_result = _fly_ssh(app_name, f"wc -c < {remote_path}")
        remote_size = int((size_result.get("output") or "0").strip() or 0)
        if remote_size != local_size:
            return {
                "success": False,
                "error": f"reassembled size {remote_size} != local {local_size}",
            }
        return {"success": True, "bytes_uploaded": local_size}
    finally:
        for chunk in chunk_paths:
            chunk.unlink(missing_ok=True)
        chunk_dir.rmdir()


def upload_bundle(bundle_path: Path, remote_path: str, app_name: str) -> dict:
    """Upload via flyctl sftp shell.

    Args:
        bundle_path: Local path to the tar.gz file.
        remote_path: Remote path on the Fly.io volume.
        app_name: Fly.io app name.

    Returns:
        Dict with keys: success, error.
    """
    try:
        result = subprocess.run(
            [FLYCTL, "ssh", "sftp", "shell", "-a", app_name],
            input=f'put "{bundle_path}" {remote_path}\n',
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for large uploads
            env=_fly_env(),
        )

        # flyctl sftp confirms with "bytes written" on success
        if "bytes written" in result.stdout.lower() or result.returncode == 0:
            return {"success": True, "error": None}

        error = result.stderr.strip() or result.stdout.strip() or "Unknown upload error"
        return {"success": False, "error": error}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Upload timed out after 5 minutes"}
    except FileNotFoundError:
        return {"success": False, "error": "flyctl not found. Install with: curl -L https://fly.io/install.sh | sh"}
    except OSError as e:
        return {"success": False, "error": str(e)}


# ── Purge-on-publish (Next.js ISR) ───────────────────────────────────────

SITE_URL = "https://mindpattern.ai"
BACKEND_URL = "https://mindpattern.fly.dev"
# Paths per POST. Must stay at or under the route's own cap
# (MAX_PATHS in src/app/api/revalidate/route.ts, vercel-mindpattern).
REVALIDATE_BATCH = 50
# Entity dossiers are rewritten in place, so "affected" means "named by one of
# today's stories and already published". Bounded because /e/ is the most
# expensive page on the site to render, and every purge costs a re-render.
REVALIDATE_MAX_ENTITIES = 12
# Purge and crawl in waves rather than purging everything and then crawling it.
# revalidatePath expires the entry outright, so the next request is a blocking
# cold render, not stale-while-revalidate. Purging all ~96 paths up front left
# every one of them uncached for the ~10 minutes the serial crawl took, and
# readers got hard 500s the whole time. One wave is uncached for one request.
REVALIDATE_WAVE = 10
# Ceiling on the crawl loop. _get allows 45s per request, so an unbounded loop
# over a site-wide path set could block the SYNC phase for over an hour.
CRAWL_BUDGET_MINUTES = 10.0
# Caps for scope="site". The sitemap carries 7,279 URLs, which no serial crawl
# finishes; these keep the set to roughly 370 pages. See sitemap_site_paths.
SITE_WARM_STORY_LIMIT = 200
SITE_WARM_ARCHIVE_LIMIT = 30
_STORY_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,159}")
# Mirrors dashboard.routes.api._is_public_entity_slug's length floor without
# importing the dashboard into the pipeline.
_ENTITY_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{3,79}")


def _revalidate_secret() -> str:
    """Shared secret for the site's /api/revalidate (env, else local file)."""
    secret = os.environ.get("MP_REVALIDATE_SECRET", "").strip()
    if secret:
        return secret
    try:
        return (Path.home() / ".mindpattern-revalidate-secret").read_text().strip()
    except OSError:
        return ""


def _redact(text: str, secret: str) -> str:
    """Never let the shared secret reach a log line or a return value."""
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def changed_site_paths(
    date: str,
    *,
    user_id: str = "ramsay",
    reports_root: Path | str | None = None,
    max_entities: int = REVALIDATE_MAX_ENTITIES,
) -> list[str]:
    """Site-relative paths the day's publish changed.

    Reads the artifacts the pipeline just wrote (site-stories/<date>/*.json and
    the entity dossiers) instead of asking the backend, because at this point
    the backend has the new data but the CDN still serves the old pages.
    Entity pages are ranked by how many of today's stories name them and
    capped at ``max_entities``.
    """
    root = (
        Path(reports_root)
        if reports_root is not None
        else Path(__file__).resolve().parents[1] / "reports" / user_id
    )
    paths = ["/", "/briefings", f"/briefings/{date}", f"/blog/{date}"]

    entity_counts: dict[str, int] = {}
    story_dir = root / "site-stories" / date
    story_files = sorted(story_dir.glob("*.json")) if story_dir.is_dir() else []
    for story_file in story_files:
        try:
            story = json.loads(story_file.read_text())
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Purge-on-publish: unreadable story %s: %s", story_file.name, exc)
            continue
        if not isinstance(story, dict):
            log.warning("Purge-on-publish: story %s is not an object", story_file.name)
            continue
        slug = str(story.get("slug") or story_file.stem).strip()
        if _STORY_SLUG_RE.fullmatch(slug):
            paths.append(f"/s/{slug}")
        for ref in story.get("entity_refs") or []:
            if not isinstance(ref, dict):
                continue
            entity_slug = str(ref.get("slug") or "").strip()
            if _ENTITY_SLUG_RE.fullmatch(entity_slug):
                entity_counts[entity_slug] = entity_counts.get(entity_slug, 0) + 1

    entities_dir = root / "site-dossiers" / "entities"
    published = (
        {path.stem for path in entities_dir.glob("*.json")} if entities_dir.is_dir() else set()
    )
    ranked = sorted(
        (slug for slug in entity_counts if slug in published),
        key=lambda slug: (-entity_counts[slug], slug),
    )
    paths.extend(f"/e/{slug}" for slug in ranked[: max(0, max_entities)])

    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def revalidate_site_paths(
    paths: list[str],
    *,
    site_url: str = SITE_URL,
    timeout: float = 30.0,
    batch_size: int = REVALIDATE_BATCH,
) -> dict:
    """Tell Next.js to drop its cached copy of exactly these paths.

    Pages carry an hour-long ISR TTL, so without this a publish stays
    invisible to readers until the TTL runs out and the warm crawl only
    re-caches the stale copy. POSTs to /api/revalidate with the shared secret
    in a header; the secret never appears in a log line or in the result.
    Best-effort: never raises.
    """
    import urllib.request

    result: dict = {
        "ok": False,
        "sent": 0,
        "revalidated": 0,
        "rejected": 0,
        "batches": 0,
        "skipped": False,
        "error": None,
    }
    # isinstance first: the docstring promises this never raises, and
    # dict.fromkeys throws on an unhashable element while .startswith throws on
    # a non-string one.
    wanted = list(
        dict.fromkeys(
            path for path in paths if isinstance(path, str) and path.startswith("/")
        )
    )
    if not wanted:
        result["error"] = "no paths to revalidate"
        return result

    # Every other production-mutating call in this module refuses under
    # MP_SANDBOX (upload_bundle_http, sync_to_fly, restart_app, ssh, sftp).
    # This one purges the live mindpattern.ai CDN cache, so it refuses too.
    # Soft skip rather than a raise: warming is best-effort and the callers
    # treat a skip as a degraded publish, not a failed one.
    if os.environ.get("MP_SANDBOX") == "1":
        result["skipped"] = True
        result["error"] = "MP_SANDBOX=1"
        log.warning("Purge-on-publish: MP_SANDBOX=1, refusing to purge the live site")
        return result

    secret = _revalidate_secret()
    if not secret:
        result["skipped"] = True
        result["error"] = "no revalidate secret (set MP_REVALIDATE_SECRET)"
        log.warning("Purge-on-publish: %s; the site falls back to its TTL", result["error"])
        return result

    endpoint = f"{site_url.rstrip('/')}/api/revalidate"
    for start in range(0, len(wanted), max(1, batch_size)):
        batch = wanted[start : start + max(1, batch_size)]
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"paths": batch}).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-revalidate-secret": secret,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read() or b"{}")
        except Exception as exc:
            result["error"] = _redact(f"{type(exc).__name__}: {exc}", secret)
            log.warning("Purge-on-publish: batch %s failed: %s", result["batches"] + 1, result["error"])
            return result
        result["batches"] += 1
        result["sent"] += len(batch)
        result["revalidated"] += len(payload.get("revalidated") or [])
        result["rejected"] += len(payload.get("rejected") or [])

    if result["rejected"]:
        result["error"] = f"{result['rejected']} paths rejected by the site"
        log.warning("Purge-on-publish: %s", result["error"])
    else:
        result["ok"] = True
        log.info("Purge-on-publish: revalidated %s paths", result["revalidated"])
    return result


def _backend_sitemap_graph(*, timeout: float = 45.0,
                           backend_url: str = BACKEND_URL,
                           user_id: str = "ramsay") -> dict | None:
    """The corpus the site renders its sitemap from, straight from the backend.

    Reading the site's own /sitemap.xml looked equivalent and was not. That
    route carries revalidate=3600 and sits behind Vercel's CDN, so on
    2026-08-26 the crawler got `x-vercel-cache: HIT, age: 69` holding the
    previous 187-URL sitemap. The warm run queued 36 blog dates, reported
    "crawled 36, failed 0", and left 6,806 stories and 84 entity pages cold.
    A warm crawl that picks its targets from a cache can warm the wrong thing
    and call it success.
    """
    import urllib.request

    url = f"{backend_url.rstrip('/')}/api/site/sitemap?user={user_id}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - best effort, caller decides
        log.warning("Backend sitemap unavailable (%s): %s", url, exc)
        return None


def _graph_entries(graph: dict) -> list[tuple[str, str]]:
    """(path, lastmod) for every reader-facing route in the corpus graph."""
    entries: list[tuple[str, str]] = [
        ("/", ""), ("/briefings", ""), ("/blog", ""), ("/explore", ""),
    ]
    for story in graph.get("stories") or []:
        if isinstance(story, dict) and story.get("slug"):
            entries.append((f"/s/{story['slug']}", story.get("issue_date") or ""))
    for slug in graph.get("entities") or []:
        if isinstance(slug, str) and slug:
            entries.append((f"/e/{slug}", ""))
    for domain in graph.get("sources") or []:
        if isinstance(domain, str) and domain:
            entries.append((f"/source/{domain}", ""))
    for date in graph.get("briefings") or []:
        if isinstance(date, str) and date:
            entries.append((f"/briefings/{date}", date))
            entries.append((f"/blog/{date}", date))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for path, lastmod in entries:
        if path in seen:
            continue
        seen.add(path)
        out.append((path, lastmod))
    return out


def sitemap_site_paths(
    site_url: str = SITE_URL,
    *,
    timeout: float = 45.0,
    story_limit: int = SITE_WARM_STORY_LIMIT,
    archive_limit: int = SITE_WARM_ARCHIVE_LIMIT,
) -> list[str]:
    """Reader paths from the site's own sitemap, in warm-first order.

    This is what a Vercel deploy needs. A deploy drops the WHOLE ISR cache, so
    warming only the day's date-scoped paths leaves ~6,800 /s/ pages and 84
    /e/ pages cold. Worse, on a day with no publish yet `changed_site_paths`
    returns four entry points and nothing else, so the crawl reported
    "4 warmed, 0 failed" over a site that was entirely cold.

    The whole sitemap is 7,279 URLs, which no serial crawl finishes, so the
    long tail is capped and the order is by who pays for a cold render:

    1. entry points, then every /e/ and /source/ page. The entity pages are the
       ones measured past the site's 10s abort, and the sitemap advertises all
       of them.
    2. the newest ``archive_limit`` briefings and blog dates.
    3. the newest ``story_limit`` stories. The rest of the archive renders in
       0.2-3.4s cold and crawlers re-warm it on their own sweep.

    Raises on a sitemap that cannot be read or that lists nothing: warming the
    wrong thing quietly is the bug this replaces.
    """
    graph = _backend_sitemap_graph(timeout=timeout)
    if not graph or not graph.get("stories"):
        raise RuntimeError(
            "backend sitemap unavailable or empty; refusing to warm a path set "
            "that would silently miss the archive"
        )

    entries = _graph_entries(graph)
    if not entries:
        raise RuntimeError("backend sitemap listed no reader paths")
    def newest(prefix: str, limit: int) -> list[str]:
        matching = [entry for entry in entries if entry[0].startswith(prefix)]
        matching.sort(key=lambda entry: entry[1], reverse=True)
        return [path for path, _ in matching[: max(0, limit)]]

    capped = {"/s/": story_limit, "/blog/": archive_limit, "/briefings/": archive_limit}
    ordered = [
        path
        for path, _ in entries
        if not any(path.startswith(prefix) for prefix in capped)
    ]
    ordered += newest("/briefings/", archive_limit)
    ordered += newest("/blog/", archive_limit)
    ordered += newest("/s/", story_limit)
    return list(dict.fromkeys(ordered))


def warm_public_site(
    *,
    date: str,
    backend_url: str = BACKEND_URL,
    site_url: str = SITE_URL,
    backend_wait_minutes: float = 10.0,
    user_id: str = "ramsay",
    reports_root: Path | str | None = None,
    revalidate: bool = True,
    scope: str = "changed",
    crawl_budget_minutes: float = CRAWL_BUDGET_MINUTES,
    wave_size: int = REVALIDATE_WAVE,
) -> dict:
    """Purge and re-seed the public site's cache after a publish or a deploy.

    Two things wipe or stale the reader-facing cache, and they need different
    treatment:

    * ``scope="changed"`` — after a publish. The backend has new data the CDN
      has not seen, so the day's paths are purged and re-crawled. This is what
      runner.py's SYNC phase calls.
    * ``scope="site"`` — after a Vercel deploy. The ISR cache is already empty,
      so there is nothing to purge; every path the sitemap advertises is
      crawled instead. Purging here would only widen the cold window.

    Purge and crawl are interleaved in waves of ``wave_size``. revalidatePath
    expires an entry outright, so the next request pays a blocking cold render
    rather than getting a stale copy: purging the whole set first left every
    page uncached for the length of the crawl.

    Best-effort throughout: never raises.
    """
    import urllib.request

    def _get(url: str, timeout: float = 45.0) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()

    result: dict = {
        "backend_warm": False,
        "scope": scope,
        "requested": 0,
        "crawled": 0,
        "failed": 0,
        "skipped_pages": 0,
        "purged": 0,
        "error": None,
    }

    # 1. Backend restarted + its cache warm-up finished (best-effort deadline;
    #    a partial warm still beats a fully cold crawl).
    deadline = time.monotonic() + backend_wait_minutes * 60
    while time.monotonic() < deadline:
        try:
            status = json.loads(_get(f"{backend_url}/api/warmup/status", timeout=20))
            phase = status.get("phase")
            if phase == "done":
                result["backend_warm"] = True
                if status.get("incomplete"):
                    result["backend_incomplete"] = list(status["incomplete"])
                    log.warning(
                        "Site warm-up: backend finished with gaps in %s",
                        ", ".join(str(name) for name in status["incomplete"]),
                    )
                break
            if phase in ("failed", "cancelled"):
                log.warning("Site warm-up: backend warm-up phase=%s; crawling anyway", phase)
                break
        except Exception:
            pass  # machine still restarting / old build without the endpoint
        time.sleep(15)

    # 2. The path set, and whether it is purge-worthy.
    if scope == "site":
        try:
            paths = sitemap_site_paths(site_url)
        except Exception as exc:
            result["error"] = f"sitemap unavailable: {type(exc).__name__}: {exc}"
            log.error("Site warm-up: %s", result["error"])
            return result
        # Nothing to drop: the deploy already dropped it.
        revalidate = False
    else:
        paths = list(changed_site_paths(date, user_id=user_id, reports_root=reports_root))
        # The entry points and the day's stories, from the backend's own list.
        try:
            stories = json.loads(
                _get(f"{backend_url}/api/stories?user={user_id}&limit=50", timeout=30)
            )
            paths.extend(
                f"/s/{item['slug']}"
                for item in stories.get("items", [])
                if item.get("issue_date") == date and item.get("slug")
            )
        except Exception as exc:
            log.warning(
                "Site warm-up: story list unavailable, crawling local paths only: %s", exc
            )
        paths = [path for path in dict.fromkeys(paths) if path.startswith("/")]

    result["requested"] = len(paths)

    # 3. Purge one wave, crawl that wave, move on. Serial: each render fans out
    #    to the backend on its own, so this keeps the box calm.
    crawl_deadline = time.monotonic() + max(0.0, crawl_budget_minutes) * 60
    purge_totals = {"ok": True, "sent": 0, "revalidated": 0, "rejected": 0, "skipped": False}
    stride = max(1, wave_size)
    for start in range(0, len(paths), stride):
        if time.monotonic() >= crawl_deadline:
            result["skipped_pages"] = len(paths) - start
            log.warning(
                "Site warm-up: crawl budget of %sm spent, %d pages never crawled",
                crawl_budget_minutes,
                result["skipped_pages"],
            )
            break
        wave = paths[start : start + stride]
        if revalidate:
            purge = revalidate_site_paths(wave, site_url=site_url)
            purge_totals["ok"] = purge_totals["ok"] and bool(purge.get("ok"))
            purge_totals["skipped"] = purge_totals["skipped"] or bool(purge.get("skipped"))
            for key in ("sent", "revalidated", "rejected"):
                purge_totals[key] += int(purge.get(key) or 0)
            if purge.get("error") and not purge.get("skipped"):
                purge_totals["error"] = purge["error"]
        for path in wave:
            try:
                _get(f"{site_url}{path}")
                result["crawled"] += 1
            except Exception as exc:
                result["failed"] += 1
                log.warning("Site warm-up: %s failed: %s", path, exc)

    if revalidate:
        result["revalidate"] = purge_totals
        result["purged"] = purge_totals["revalidated"]
    return result


def warm_cli(argv: list[str] | None = None) -> int:
    """`python3 -m orchestrator.sync warm` — the post-deploy half of deploy/deploy.sh.

    Returns a nonzero exit code when the crawl did not cover what it was asked
    to cover, so a deploy cannot report success over a cold site.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m orchestrator.sync warm",
        description="Purge and re-crawl the site's reader paths.",
    )
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--site-url", default=SITE_URL)
    parser.add_argument("--backend-url", default=BACKEND_URL)
    parser.add_argument("--backend-wait-minutes", type=float, default=10.0)
    parser.add_argument("--reports-root", default=None)
    parser.add_argument(
        "--scope",
        choices=("changed", "site"),
        default="changed",
        help=(
            "changed: the day's published paths, purged then crawled (after a "
            "publish). site: every path in sitemap.xml, crawled without a purge "
            "(after a Vercel deploy, which already dropped the whole ISR cache)."
        ),
    )
    parser.add_argument("--crawl-budget-minutes", type=float, default=CRAWL_BUDGET_MINUTES)
    parser.add_argument(
        "--no-revalidate",
        action="store_true",
        help="crawl only; skip the Next.js purge",
    )
    args = parser.parse_args(argv)

    result = warm_public_site(
        date=args.date,
        backend_url=args.backend_url,
        site_url=args.site_url,
        backend_wait_minutes=args.backend_wait_minutes,
        user_id=args.user,
        reports_root=args.reports_root,
        revalidate=not args.no_revalidate,
        scope=args.scope,
        crawl_budget_minutes=args.crawl_budget_minutes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))

    requested = int(result.get("requested") or 0)
    crawled = int(result.get("crawled") or 0)
    failed = int(result.get("failed") or 0)
    skipped = int(result.get("skipped_pages") or 0)

    # Coverage, not just "did anything answer". The old check passed on
    # "4 crawled, 0 failed" while ~780 story pages and 86 entity pages sat
    # cold, because the four it crawled were the only four it ever asked for.
    if result.get("error"):
        print(f"warm failed: {result['error']}", file=sys.stderr)
        return 1
    if not requested:
        print("warm failed: no paths to warm", file=sys.stderr)
        return 1
    if not crawled:
        print(f"warm failed: 0 of {requested} pages warmed", file=sys.stderr)
        return 1
    if skipped:
        print(
            f"warm failed: budget ran out with {skipped} of {requested} pages never crawled",
            file=sys.stderr,
        )
        return 1
    if failed:
        print(
            f"warm failed: {failed} of {requested} pages errored, {crawled} warmed",
            file=sys.stderr,
        )
        return 1
    purge = result.get("revalidate") or {}
    if purge and not purge.get("ok") and not purge.get("skipped"):
        print(f"purge failed: {purge.get('error')}", file=sys.stderr)
        return 1
    return 0


def restart_app(app_name: str) -> dict:
    """Restart the Fly.io app. Only call ONCE after ALL users synced.

    Uses flyctl machines list to find the machine ID, then restarts it.

    Args:
        app_name: Fly.io app name (e.g. 'mindpattern').

    Returns:
        Dict with keys: success, error.
    """
    _refuse_in_sandbox("Fly app restart")
    try:
        # Get machine ID
        list_result = subprocess.run(
            [FLYCTL, "machines", "list", "-a", app_name, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_fly_env(),
        )

        if list_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to list machines: {list_result.stderr.strip()}",
            }

        machines = json.loads(list_result.stdout)
        if not machines:
            return {"success": False, "error": "No machines found"}

        machine_id = machines[0].get("id")
        if not machine_id:
            return {"success": False, "error": "Machine ID not found in response"}

        # Restart the machine
        restart_result = subprocess.run(
            [FLYCTL, "machine", "restart", machine_id, "-a", app_name],
            capture_output=True,
            text=True,
            timeout=60,
            env=_fly_env(),
        )

        if restart_result.returncode == 0:
            return {"success": True, "error": None}

        return {
            "success": False,
            "error": f"Restart failed: {restart_result.stderr.strip()}",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Machine restart timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "flyctl not found"}
    except (json.JSONDecodeError, OSError) as e:
        return {"success": False, "error": str(e)}


def write_synced_marker(date_str: str) -> None:
    """Mark the day's Fly sync as confirmed-complete.

    Mirrors the deliver-phase ran-marker (``mindpattern-ran-<date>``).
    run-launchd.sh treats *delivered-but-not-synced* as a retry signal, so
    this marker — written only after a verified sync — is what finally stops
    the morning windows from re-running the sync. Keyed by date (single user).
    """
    try:
        marker_dir = os.environ.get("MP_RAN_MARKER_DIR", "/tmp")
        Path(marker_dir, f"mindpattern-synced-{date_str}").touch()
        log.info("Marked %s synced (synced-marker written)", date_str)
    except OSError as e:
        log.warning("Could not write synced-marker: %s", e)


# ── Private helpers ──────────────────────────────────────────────────────


def _wal_checkpoint(db_path: Path) -> dict:
    """Run PRAGMA wal_checkpoint(TRUNCATE) on a SQLite database.

    Returns dict with keys: success, error.
    """
    try:
        result = subprocess.run(
            ["sqlite3", str(db_path), "PRAGMA wal_checkpoint(TRUNCATE);"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_fly_env(),
        )
        if result.returncode == 0:
            return {"success": True, "error": None}
        return {"success": False, "error": result.stderr.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}


def _fly_ssh(app_name: str, command: str, timeout: int = 60) -> dict:
    """Run a command on the Fly.io app via ssh console.

    Wraps the command in ``sh -c '...'`` so shell builtins (cd, etc.) and
    operators (&&, ||, ;) work correctly.  flyctl's ``-C`` flag execs the
    command directly — without a shell — so bare builtins like ``cd`` cause
    ``exec: "cd": executable file not found in $PATH``.

    ``timeout`` is per-call because the default suits status probes but not
    extraction: unpacking the bundle grew past 60s as the archive grew, and a
    killed tar leaves half-written files behind rather than failing cleanly.

    Returns dict with keys: success, output, error.
    """
    _refuse_in_sandbox("Fly ssh command")
    try:
        # Wrap in sh -c so shell builtins and compound commands work.
        # Single quotes inside the command are escaped for the sh -c wrapper.
        wrapped = f"sh -c '{command.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
        result = subprocess.run(
            [FLYCTL, "ssh", "console", "-a", app_name, "-C", wrapped],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_fly_env(),
        )

        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip(), "error": None}

        return {
            "success": False,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() or "Command failed",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "SSH command timed out"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "flyctl not found"}
    except OSError as e:
        return {"success": False, "output": "", "error": str(e)}


def _fly_sftp_put(app_name: str, local_path: str, remote_path: str) -> bool:
    """Upload a single file via flyctl sftp."""
    _refuse_in_sandbox("Fly sftp upload")
    try:
        result = subprocess.run(
            [FLYCTL, "ssh", "sftp", "shell", "-a", app_name],
            input=f'put "{local_path}" {remote_path}\n',
            capture_output=True, text=True, timeout=60,
            env=_fly_env(),
        )
        return result.returncode == 0
    except Exception as e:
        log.warning(f"SFTP put failed for {local_path}: {e}")
        return False


def _remote_size(app_name: str, remote_path: str) -> int:
    """Return the byte size of a remote file, or -1 if it can't be read."""
    res = _fly_ssh(app_name, f"wc -c < {remote_path}")
    parts = res["output"].split() if res.get("success") else []
    try:
        return int(parts[0]) if parts else -1
    except ValueError:
        return -1


def _put_and_verify(app_name: str, local_path: Path, remote_path: str) -> bool:
    """SFTP-upload a file and confirm it landed at the expected byte size.

    Retries the upload once on a size mismatch (a truncated transfer over a
    flaky tunnel). Returns True only when the remote size matches local — so
    a silently-dropped database surfaces as a sync failure instead of a
    stale-but-"successful" dashboard.
    """
    expected = local_path.stat().st_size
    for attempt in (1, 2):
        uploaded = _fly_sftp_put(app_name, str(local_path), remote_path)
        if not uploaded:
            log.warning("SFTP %s failed (attempt %s/2)", remote_path, attempt)
            continue
        actual = _remote_size(app_name, remote_path)
        if actual == expected:
            return True
        log.warning(
            "SFTP %s landed at %s bytes, expected %s (attempt %s/2)",
            remote_path, actual, expected, attempt,
        )
    return False


if __name__ == "__main__":
    import sqlite3
    import shutil

    # `python3 -m orchestrator.sync warm …` is the deploy wrapper's second
    # half; a bare run keeps the original self-check below.
    if sys.argv[1:2] == ["warm"]:
        sys.exit(warm_cli(sys.argv[2:]))

    # --- AC #1: create_bundle with memory.db and reports ---
    tmp = Path(tempfile.mkdtemp(prefix="sync-test-"))
    user_id = "testuser"

    # Create test data structure
    db_dir = tmp / "data" / user_id
    db_dir.mkdir(parents=True)
    reports_dir = tmp / "reports" / user_id / "agents"
    reports_dir.mkdir(parents=True)

    # Create test memory.db
    db_path = db_dir / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO test VALUES (1)")
    conn.commit()
    conn.close()

    # Create test traces.db
    traces_path = db_dir / "traces.db"
    conn = sqlite3.connect(str(traces_path))
    conn.execute("CREATE TABLE pipeline_runs (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    # Create test report files
    (tmp / "reports" / user_id / "2026-03-14.md").write_text("# Report\n\nContent.\n")
    (reports_dir / "agent-1.md").write_text("# Agent 1\n\nFindings.\n")
    (reports_dir / "agent-2.md").write_text("# Agent 2\n\nMore findings.\n")

    bundle = create_bundle(
        user_id,
        tmp / "data",
        tmp / "reports" / user_id,
        "2026-03-14",
    )
    assert bundle.exists(), "Bundle should exist"
    assert bundle.stat().st_size > 0, "Bundle should not be empty"

    # Verify bundle contents
    with tarfile.open(bundle, "r:gz") as tf:
        names = sorted(tf.getnames())
        assert f"{user_id}/memory.db" in names, f"memory.db not in bundle: {names}"
        assert f"{user_id}/traces.db" in names, f"traces.db not in bundle: {names}"
        assert f"reports/{user_id}/2026-03-14.md" in names, f"report not in bundle: {names}"
        assert f"reports/{user_id}/agents/agent-1.md" in names, f"agent-1 not in bundle: {names}"
        assert f"reports/{user_id}/agents/agent-2.md" in names, f"agent-2 not in bundle: {names}"
        assert len(names) == 5, f"Expected 5 files, got {len(names)}: {names}"
    print(f"AC #1: Bundle created with {len(names)} files ({bundle.stat().st_size} bytes)")

    bundle.unlink()

    # --- AC #2: create_bundle with missing reports dir ---
    bundle2 = create_bundle(
        user_id,
        tmp / "data",
        tmp / "nonexistent-reports",
        "2026-03-14",
    )
    with tarfile.open(bundle2, "r:gz") as tf:
        names2 = tf.getnames()
        assert len(names2) == 2, f"Expected 2 files (memory.db + traces.db), got {len(names2)}"
        assert f"{user_id}/memory.db" in names2
        assert f"{user_id}/traces.db" in names2
    print("AC #2: Bundle with missing reports handled gracefully")
    bundle2.unlink()

    # --- AC #3: sync_to_fly with missing db ---
    result = sync_to_fly("nonexistent", tmp / "data")
    assert not result["success"]
    assert "No memory.db" in result["error"]
    print("AC #3: sync_to_fly with missing db returns error")

    # --- AC #4: upload_bundle with missing flyctl ---
    # This tests graceful handling when flyctl is not installed
    fake_bundle = tmp / "fake.tar.gz"
    fake_bundle.write_bytes(b"fake")
    upload_result = upload_bundle(fake_bundle, "/data/test.tar.gz", "nonexistent-app")
    # Will either succeed (flyctl installed) or fail gracefully
    assert "success" in upload_result
    assert "error" in upload_result
    print(f"AC #4: upload_bundle handled ({upload_result.get('error', 'OK')})")

    # --- AC #5: restart_app with missing flyctl ---
    restart_result = restart_app("nonexistent-app")
    assert "success" in restart_result
    assert "error" in restart_result
    print(f"AC #5: restart_app handled ({restart_result.get('error', 'OK')})")

    # --- AC #6: _wal_checkpoint ---
    checkpoint = _wal_checkpoint(db_path)
    assert checkpoint["success"], f"Checkpoint failed: {checkpoint['error']}"
    print("AC #6: WAL checkpoint verified")

    # Clean up
    shutil.rmtree(tmp)
    print("\nAll sync.py checks passed.")
