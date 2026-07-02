"""HTTPS sync-bundle upload: the durable replacement for flyctl sftp.

The local pipeline POSTs the daily tar.gz here over Fly's production edge
(anycast HTTP, no WireGuard tunnel), authenticated by the pipeline shared
secret, verified by sha256, then extracted into the data volume with the
same WAL hygiene the sftp path used. See docs/handoff research brief
2026-07-02: flyctl's sftp has no resume or integrity check and truncates
on tunnel instability; this path retries and verifies end to end.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tarfile
import tempfile
from pathlib import Path

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter()

MAX_BUNDLE_BYTES = 300 * 1024 * 1024
_SAFE_USER = {"ramsay"}


def _data_root() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def _secret_ok(provided: str | None) -> bool:
    expected = os.environ.get("MP_PIPELINE_SECRET", "")
    return bool(expected) and bool(provided) and hmac.compare_digest(provided, expected)


def _member_allowed(name: str, user: str) -> bool:
    normalized = name.lstrip("./")
    return normalized.startswith((f"{user}/", f"reports/{user}/"))


@router.post("/api/sync/bundle")
async def receive_sync_bundle(
    request: Request,
    user: str = Query("ramsay"),
    x_pipeline_secret: str | None = Header(default=None),
    x_bundle_sha256: str | None = Header(default=None),
):
    if not _secret_ok(x_pipeline_secret):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    if user not in _SAFE_USER:
        return JSONResponse(status_code=400, content={"error": "unknown user"})
    if not x_bundle_sha256:
        return JSONResponse(status_code=400, content={"error": "X-Bundle-Sha256 required"})

    root = _data_root()
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    received = 0
    tmp = tempfile.NamedTemporaryFile(dir=root, suffix=".bundle", delete=False)
    tmp_path = Path(tmp.name)
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_BUNDLE_BYTES:
                return JSONResponse(status_code=413, content={"error": "bundle too large"})
            digest.update(chunk)
            tmp.write(chunk)
        tmp.close()

        if digest.hexdigest() != x_bundle_sha256.lower():
            return JSONResponse(status_code=400, content={
                "error": "sha256 mismatch",
                "received_sha256": digest.hexdigest(),
                "received_bytes": received,
            })

        extracted = 0
        with tarfile.open(tmp_path, "r:gz") as bundle:
            for member in bundle.getmembers():
                if not _member_allowed(member.name, user):
                    return JSONResponse(status_code=400, content={
                        "error": f"member outside allowed layout: {member.name[:80]}",
                    })
            # Replacing the databases: drop stale WAL/SHM in the same
            # operation so leftover journals never replay into fresh files.
            for suffix in ("-wal", "-shm"):
                for db in ("memory.db", "traces.db"):
                    (root / user / f"{db}{suffix}").unlink(missing_ok=True)
            bundle.extractall(root, filter="data")
            extracted = len(bundle.getnames())

        return {
            "status": "ok",
            "received_bytes": received,
            "sha256": digest.hexdigest(),
            "extracted_files": extracted,
        }
    except tarfile.TarError as exc:
        return JSONResponse(status_code=400, content={"error": f"bad bundle: {exc}"})
    finally:
        tmp_path.unlink(missing_ok=True)
