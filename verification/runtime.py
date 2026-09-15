"""Create and operate a disposable current-source verification snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verification.fixtures import create_fixture

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "data",
    "reports",
    "tests",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "graphify-out",
    "node_modules",
    "research",
}


@dataclass
class RuntimeSnapshot:
    temporary: tempfile.TemporaryDirectory[str]
    source_root: Path
    scratch_root: Path
    token: str
    environment: dict[str, str]
    source_hashes: dict[str, str]
    fixture: dict[str, str]

    def cleanup(self) -> None:
        self.temporary.cleanup()


def _included(relative: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if relative.name == "users.json" or relative.name.startswith(".env"):
        return False
    return relative.suffix == ".py" or relative.parts[:2] == ("dashboard", "templates")


def _copy_source(destination: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for directory, subdirectories, filenames in os.walk(PROJECT_ROOT):
        base = Path(directory)
        subdirectories[:] = [
            name for name in subdirectories
            if name not in EXCLUDED_PARTS and not name.startswith(".")
            and not (base / name).is_symlink()
        ]
        for filename in filenames:
            path = base / filename
            relative = path.relative_to(PROJECT_ROOT)
            if path.is_symlink() or not _included(relative):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = path.read_bytes()
            target.write_bytes(contents)
            hashes[relative.as_posix()] = hashlib.sha256(contents).hexdigest()
    return dict(sorted(hashes.items()))


def create_runtime() -> RuntimeSnapshot:
    temporary = tempfile.TemporaryDirectory(prefix="mindpattern-verification-runtime-")
    root = Path(temporary.name).resolve()
    source_root = root / "source"
    scratch_root = root / "scratch"
    source_root.mkdir()
    scratch_root.mkdir()
    try:
        source_hashes = _copy_source(source_root)
        fixture = create_fixture(source_root, scratch_root)
    except BaseException:
        temporary.cleanup()
        raise
    token = secrets.token_urlsafe(32)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(source_root),
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(scratch_root / "tmp"),
        "LANG": "C.UTF-8",
        "MP_DISABLE_OUTBOUND": "1",
        "MP_REPORTS_DIR": fixture["reports_root"],
        "DATA_DIR": fixture["data_root"],
        "MP_EVENTS_DB": str(scratch_root / "events.db"),
        "MP_BOT_HEARTBEAT_PATH": str(scratch_root / "bot-heartbeat"),
        "FASTEMBED_CACHE_DIR": str(scratch_root / "fastembed-cache"),
        "API_TOKEN_HASH": hashlib.sha256(token.encode()).hexdigest(),
        "VERIFICATION_API_TOKEN": token,
        "VERIFICATION_SNAPSHOT": str(source_root / ".verification-runtime.json"),
    }
    Path(environment["VERIFICATION_SNAPSHOT"]).write_text(json.dumps({
        "source": str(source_root), "scratch": str(scratch_root),
    }))
    for directory in (environment["TMPDIR"], environment["FASTEMBED_CACHE_DIR"]):
        Path(directory).mkdir(parents=True, exist_ok=True)
    return RuntimeSnapshot(temporary, source_root, scratch_root, token, environment, source_hashes, fixture)


def source_state() -> dict[str, Any]:
    revision = None
    dirty = None
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return {"git_revision": revision, "git_dirty": dirty}


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


def run_worker(runtime: RuntimeSnapshot, arguments: list[str], timeout: float = 60) -> dict[str, Any]:
    process = subprocess.Popen(
        [sys.executable, "-m", "verification", *arguments],
        cwd=runtime.source_root,
        env=runtime.environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"verification worker timed out after {timeout:g}s") from exc
    finally:
        stop_process(process)
    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"worker exited {process.returncode}"
        raise RuntimeError(detail[-4000:])
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"verification worker returned invalid JSON: {stdout[-1000:]}") from exc
