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

    # Step 3: Create remote directories
    remote_base = f"/data/{user_id}"
    _fly_ssh(app_name, f"mkdir -p {remote_base} /data/reports/{user_id}/agents")

    # Step 4: Upload bundle
    remote_bundle = f"{remote_base}/sync-bundle.tar.gz"
    upload_result = upload_bundle(bundle_path, remote_bundle, app_name)

    if not upload_result["success"]:
        bundle_path.unlink(missing_ok=True)
        return {
            "success": False,
            "bytes_uploaded": 0,
            "files_included": files_included,
            "error": f"Upload failed: {upload_result['error']}",
        }

    # Step 5: Verify the upload arrived intact before extracting. A machine
    # restart (deploy, scale) mid-transfer leaves a truncated bundle that
    # tar fails on with "Unexpected EOF"; retry the upload once.
    size_result = _fly_ssh(app_name, f"wc -c < {remote_bundle}")
    remote_size = int(size_result["output"].split()[0]) if (
        size_result["success"] and size_result["output"].strip().split()
    ) else -1
    if remote_size != bundle_size:
        log.warning(
            "Remote bundle size %s != local %s — retrying upload once",
            remote_size, bundle_size,
        )
        upload_result = upload_bundle(bundle_path, remote_bundle, app_name)
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
        extract_result = _fly_ssh(
            app_name,
            f"cd /data && tar xzf {remote_bundle} "
            f"&& rm -f {remote_bundle} {stale_sidecars}",
        )

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

    return {
        "success": True,
        "bytes_uploaded": bundle_size,
        "files_included": files_included,
        "error": None,
    }


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
        )
        if result.returncode == 0:
            return {"success": True, "error": None}
        return {"success": False, "error": result.stderr.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return {"success": False, "error": str(e)}


def _fly_ssh(app_name: str, command: str) -> dict:
    """Run a command on the Fly.io app via ssh console.

    Wraps the command in ``sh -c '...'`` so shell builtins (cd, etc.) and
    operators (&&, ||, ;) work correctly.  flyctl's ``-C`` flag execs the
    command directly — without a shell — so bare builtins like ``cd`` cause
    ``exec: "cd": executable file not found in $PATH``.

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
            timeout=60,
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
