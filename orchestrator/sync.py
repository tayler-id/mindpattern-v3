"""Fly.io synchronization — replaces sync-to-fly.sh.

Bundles memory.db + today's reports into a tar.gz, uploads via flyctl sftp,
and restarts the app. ONE upload per user instead of 30 separate connections.
"""

import json
import logging
import os
import shutil
import sqlite3
import subprocess
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
        # Step 6: Extract bundle on remote. Remove stale -wal/-shm in the
        # SAME command — leftover WAL from the replaced database would be
        # replayed into the fresh file and corrupt it.
        stale_sidecars = (
            f"{user_id}/memory.db-wal {user_id}/memory.db-shm "
            f"{user_id}/traces.db-wal {user_id}/traces.db-shm"
        )
        # tar needs far longer than a status probe: the bundle passed 50 MB in
        # July 2026 and unpacking ~2,300 files on shared-cpu-2x runs past the
        # 60s default. A killed tar does not fail cleanly — it leaves the files
        # it had not reached yet at zero bytes, which is how 2026-07-27 shipped
        # 86 empty story files that the public API then served as nothing.
        extract_result = _fly_ssh(
            app_name,
            f"cd /data && tar xzf {remote_bundle} "
            f"&& rm -f {remote_bundle} {stale_sidecars}",
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
                f"cd /data && tar xzf {remote_bundle} "
                f"&& rm -f {remote_bundle} {stale_sidecars}",
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


def warm_public_site(
    *,
    date: str,
    backend_url: str = "https://mindpattern.fly.dev",
    site_url: str = "https://mindpattern.ai",
    backend_wait_minutes: float = 10.0,
) -> dict:
    """Seed the public site's CDN cache right after the post-sync restart.

    The restart wipes the dashboard's in-memory caches, and Vercel's page
    cache only fills per-click — without this, the morning's first readers
    rendered every page against a cold backend. Waits for the backend's own
    warm-up (dashboard/warmup.py) to finish or a deadline, then serially
    requests the day's new pages plus the entry points so the CDN copy exists
    before anyone wakes up. Best-effort throughout: never raises.
    """
    import urllib.request

    def _get(url: str, timeout: float = 45.0) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()

    result: dict = {"backend_warm": False, "crawled": 0, "failed": 0}

    # 1. Backend restarted + its cache warm-up finished (best-effort deadline;
    #    a partial warm still beats a fully cold crawl).
    deadline = time.monotonic() + backend_wait_minutes * 60
    while time.monotonic() < deadline:
        try:
            status = json.loads(_get(f"{backend_url}/api/warmup/status", timeout=20))
            phase = status.get("phase")
            if phase == "done":
                result["backend_warm"] = True
                break
            if phase in ("failed", "cancelled"):
                log.warning("Site warm-up: backend warm-up phase=%s; crawling anyway", phase)
                break
        except Exception:
            pass  # machine still restarting / old build without the endpoint
        time.sleep(15)

    # 2. The day's new pages + the entry points, one at a time — each render
    #    fans out to the backend on its own, so serial keeps the box calm.
    pages = [
        f"{site_url}/briefings/{date}",
        f"{site_url}/blog/{date}",
        f"{site_url}/briefings",
        f"{site_url}/",
    ]
    try:
        stories = json.loads(_get(f"{backend_url}/api/stories?user=ramsay&limit=50", timeout=30))
        pages.extend(
            f"{site_url}/s/{item['slug']}"
            for item in stories.get("items", [])
            if item.get("issue_date") == date and item.get("slug")
        )
    except Exception as exc:
        log.warning("Site warm-up: story list unavailable, crawling entry points only: %s", exc)

    for url in pages:
        try:
            _get(url)
            result["crawled"] += 1
        except Exception as exc:
            result["failed"] += 1
            log.warning("Site warm-up: %s failed: %s", url, exc)

    return result


def restart_app(app_name: str) -> dict:
    """Restart the Fly.io app. Only call ONCE after ALL users synced.

    Uses flyctl machines list to find the machine ID, then restarts it.

    Args:
        app_name: Fly.io app name (e.g. 'mindpattern').

    Returns:
        Dict with keys: success, error.
    """
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
