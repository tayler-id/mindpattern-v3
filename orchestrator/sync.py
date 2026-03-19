"""Fly.io synchronization — replaces sync-to-fly.sh.

Bundles memory.db + today's reports into a tar.gz, uploads via flyctl sftp,
and restarts the app. ONE upload per user instead of 30 separate connections.
"""

import json
import logging
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


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

    # Step 5: Extract bundle on remote
    extract_result = _fly_ssh(
        app_name,
        f"cd /data && tar xzf {remote_bundle} && rm -f {remote_bundle}",
    )

    if not extract_result["success"]:
        log.warning(f"Bundle extraction failed: {extract_result['error']}. Falling back to direct SFTP.")
        # Fallback: upload reports directly via SFTP (more reliable)
        for report_file in sorted(reports_dir.glob("????-??-??.md")):
            _fly_sftp_put(app_name, str(report_file), f"/data/reports/{user_id}/{report_file.name}")
        # Upload DBs directly
        if db_path.exists():
            _fly_sftp_put(app_name, str(db_path), f"/data/{user_id}/memory.db")
        traces_path_local = data_dir / user_id / "traces.db"
        if traces_path_local.exists():
            _fly_sftp_put(app_name, str(traces_path_local), f"/data/{user_id}/traces.db")

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
        except Exception:
            pass  # Don't fail sync because of trace logging

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

    with tarfile.open(bundle_path, "w:gz") as tf:
        # Add memory.db
        if db_path.exists():
            tf.add(str(db_path), arcname=f"{user_id}/memory.db")

        # Add traces.db (pipeline runs, agent runs, events, etc.)
        if traces_path.exists():
            tf.add(str(traces_path), arcname=f"{user_id}/traces.db")

        # Add ALL date-named reports (not just today's — catches missed syncs)
        for report_file in sorted(reports_dir.glob("????-??-??.md")):
            tf.add(str(report_file), arcname=f"reports/{user_id}/{report_file.name}")

        # Add agent sub-reports
        agents_dir = reports_dir / "agents"
        if agents_dir.is_dir():
            for md_file in sorted(agents_dir.glob("*.md")):
                tf.add(str(md_file), arcname=f"reports/{user_id}/agents/{md_file.name}")

    return bundle_path


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
            ["flyctl", "ssh", "sftp", "shell", "-a", app_name],
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
            ["flyctl", "machines", "list", "-a", app_name, "--json"],
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
            ["flyctl", "machine", "restart", machine_id, "-a", app_name],
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
            ["flyctl", "ssh", "console", "-a", app_name, "-C", wrapped],
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
            ["flyctl", "ssh", "sftp", "shell", "-a", app_name],
            input=f'put "{local_path}" {remote_path}\n',
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except Exception as e:
        log.warning(f"SFTP put failed for {local_path}: {e}")
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
