"""Worker-side route driver loaded only inside a disposable snapshot."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from verification.features import FEATURE_BY_ID, VERIFIERS
from verification.models import RequestResult

ALLOWED_PATHS = (
    "/healthz",
    "/api/stories",
    "/api/search/site",
    "/api/site/runs/",
    "/api/site/corpus/",
    "/api/site/sitemap",
    "/api/users",
)


def validate_snapshot() -> None:
    root = Path(__file__).resolve().parent.parent
    marker = root / ".verification-runtime.json"
    try:
        if os.environ.get("VERIFICATION_SNAPSHOT") != str(marker):
            raise ValueError("missing snapshot marker")
        config = json.loads(marker.read_text())
        scratch = root.parent / "scratch"
        if config != {"source": str(root), "scratch": str(scratch)}:
            raise ValueError("invalid snapshot roots")
        expected = {
            "DATA_DIR": str(root / "data"),
            "MP_REPORTS_DIR": str(scratch / "reports"),
            "MP_EVENTS_DB": str(scratch / "events.db"),
            "MP_BOT_HEARTBEAT_PATH": str(scratch / "bot-heartbeat"),
            "FASTEMBED_CACHE_DIR": str(scratch / "fastembed-cache"),
            "MP_DISABLE_OUTBOUND": "1",
        }
        if any(os.environ.get(key) != value for key, value in expected.items()):
            raise ValueError("invalid snapshot environment")
        token = os.environ["VERIFICATION_API_TOKEN"]
        if hashlib.sha256(token.encode()).hexdigest() != os.environ.get("API_TOKEN_HASH"):
            raise ValueError("invalid snapshot authentication")
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError("internal workers require a CLI-created isolated snapshot") from exc


def validate_request_path(path: str) -> str:
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/"):
        raise ValueError("PATH must be an absolute local path without a fragment")
    if not any(
        parsed.path == allowed
        or (allowed in {"/api/stories", "/api/site/runs/", "/api/site/corpus/"}
            and parsed.path.startswith(allowed.rstrip("/") + "/"))
        for allowed in ALLOWED_PATHS
    ):
        raise ValueError(f"PATH is outside the verification route set: {parsed.path}")
    if parsed.path == "/api/search/site":
        query = parse_qs(parsed.query)
        if query.get("types") != ["stories"]:
            raise ValueError("site search requests must set types=stories")
    return path


def _block_outbound() -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("outbound access is disabled in the verification worker")

    socket.create_connection = blocked
    socket.socket.connect = blocked
    subprocess.Popen = blocked
    subprocess.run = blocked
    subprocess.call = blocked
    subprocess.check_call = blocked
    subprocess.check_output = blocked


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:10000]


async def _client() -> tuple[httpx.AsyncClient, str]:
    _block_outbound()
    from dashboard.app import app

    token = os.environ["VERIFICATION_API_TOKEN"]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://verification.local"), token


def _cache_inventory() -> list[dict[str, Any]]:
    root = Path(os.environ["DATA_DIR"]) / "ramsay" / "site-cache"
    artifacts = []
    if root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            contents = path.read_bytes()
            artifacts.append({
                "path": path.relative_to(root).as_posix(),
                "bytes": len(contents),
                "sha256": hashlib.sha256(contents).hexdigest(),
            })
    return artifacts


async def request_fixture(path: str) -> dict[str, Any]:
    path = validate_request_path(path)
    client, _ = await _client()
    async with client:
        started = time.perf_counter()
        response = await client.get(path)
        result = RequestResult("GET", path, response.status_code, _body(response), (time.perf_counter() - started) * 1000)
    return {
        "mode": "isolated-asgi",
        "lifespan": "skipped",
        "request": result.to_dict(),
        "cache_artifacts": _cache_inventory(),
    }


async def verify(feature_ids: list[str]) -> dict[str, Any]:
    client, token = await _client()
    results = []
    async with client:
        async def fetch(path: str, headers: dict[str, str] | None) -> RequestResult:
            path = validate_request_path(path)
            safe_headers = dict(headers or {})
            if safe_headers.get("authorization") == "Bearer __generated__":
                safe_headers["authorization"] = f"Bearer {token}"
            started = time.perf_counter()
            response = await client.get(path, headers=safe_headers)
            return RequestResult(
                method="GET",
                path=path,
                status=response.status_code,
                body=_body(response),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

        for feature_id in feature_ids:
            feature = FEATURE_BY_ID[feature_id]
            requests, assertions = await VERIFIERS[feature.verifier](fetch)
            results.append({
                "id": feature.id,
                "passed": all(assertion.passed for assertion in assertions),
                "requests": [request.to_dict() for request in requests],
                "assertions": [assertion.to_dict() for assertion in assertions],
            })
    return {
        "mode": "isolated-asgi",
        "lifespan": "skipped",
        "passed": all(result["passed"] for result in results),
        "features": results,
        "cache_artifacts": _cache_inventory(),
    }


def run_worker(action: str, values: list[str]) -> dict[str, Any]:
    validate_snapshot()
    if action == "serve":
        _block_outbound()
        import uvicorn
        from dashboard.app import app

        uvicorn.run(app, host="127.0.0.1", port=int(values[0]), lifespan="off", loop="asyncio")
        return {"status": "stopped"}
    if action == "request":
        return asyncio.run(request_fixture(values[0]))
    if action == "verify":
        return asyncio.run(verify(values))
    raise ValueError(f"unknown worker action: {action}")
