"""Command-line interface for isolated MindPattern verification."""

from __future__ import annotations

import argparse
import json
import signal
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from verification.features import FEATURES, FEATURE_BY_ID, feature_payload
from verification.runtime import create_runtime, run_worker, source_state, stop_process
from verification.worker import validate_request_path


class CliError(Exception):
    pass


def _json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m verification", description="Verify MindPattern routes in an isolated synthetic runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    features = subparsers.add_parser("features", help="List supported feature checks.")
    features.add_argument("feature", nargs="?", choices=tuple(FEATURE_BY_ID))
    subparsers.add_parser("doctor", help="Check snapshot import and isolated health behavior.")

    request = subparsers.add_parser("request", help="Send one scoped GET request.")
    request.add_argument("path")
    request.add_argument("--base-url", help="Observe an existing loopback server instead of the fixture.")

    verify = subparsers.add_parser("verify", help="Run one feature check or all checks.")
    verify.add_argument("feature", choices=(*FEATURE_BY_ID, "all"))
    verify.add_argument("--evidence", type=Path, help="New directory for the retained manifest.")

    serve = subparsers.add_parser("serve", help="Serve the isolated fixture on loopback until interrupted.")
    serve.add_argument("--port", type=int, default=8011)

    return parser


def _evidence_directory(requested: Path | None) -> Path:
    if requested is None:
        import tempfile

        return Path(tempfile.mkdtemp(prefix="mindpattern-verification-evidence-"))
    path = requested.expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CliError(f"evidence directory already exists: {path}") from exc
    return path


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    target = path / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _external_request(path: str, base_url: str) -> dict[str, Any]:
    path = validate_request_path(path)
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise CliError("--base-url must be an http loopback URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise CliError("--base-url must contain only scheme, loopback host, and port")
    if parsed.port is None:
        raise CliError("--base-url must include a port")
    started = datetime.now(timezone.utc)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        response = client.get(f"{base_url.rstrip('/')}{path}")
    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:10000]
    return {
        "mode": "external-loopback-observation",
        "assertions": "not run",
        "request": {"method": "GET", "path": path, "status": response.status_code, "body": body, "elapsed_ms": elapsed},
    }


def _verify(feature: str, evidence: Path | None) -> int:
    evidence_dir = _evidence_directory(evidence)
    selected = list(FEATURE_BY_ID) if feature == "all" else [feature]
    runtime = None
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "isolated-asgi",
        "lifespan": "skipped",
        "selected_features": selected,
        "status": "error",
    }
    try:
        runtime = create_runtime()
        manifest["fixture"] = {
            "date": runtime.fixture["date"],
            "user": runtime.fixture["user"],
            "limits": "Synthetic files only. No personal databases, reports, identities, or credentials are copied.",
        }
        manifest["source"] = {**source_state(), "sha256": runtime.source_hashes}
        result = run_worker(runtime, ["_worker", "verify", *selected])
        manifest.update(result)
        manifest["status"] = "passed" if result["passed"] else "failed"
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if runtime is not None:
            runtime.cleanup()
        _write_manifest(evidence_dir, manifest)
    _json({
        "status": manifest["status"],
        "passed": manifest.get("passed", False),
        "evidence": str(evidence_dir),
        "features": [{"id": item["id"], "passed": item["passed"]} for item in manifest.get("features", [])],
        **({"error": manifest["error"]} if "error" in manifest else {}),
    })
    return 0 if manifest["status"] == "passed" else 1


def _doctor() -> int:
    runtime = create_runtime()
    try:
        result = run_worker(runtime, ["_worker", "request", "/healthz"])
    finally:
        runtime.cleanup()
    request = result["request"]
    healthy = request["status"] == 200 and isinstance(request["body"], dict)
    payload = {
        "status": "ok" if healthy else "degraded",
        "interpreter": sys.executable,
        "snapshot_import": "ok" if request["status"] else "failed",
        "lifespan": "skipped",
        "health": request,
    }
    _json(payload)
    return 0 if healthy else 1


def _fixture_request(path: str) -> int:
    runtime = create_runtime()
    try:
        result = run_worker(runtime, ["_worker", "request", path])
    finally:
        runtime.cleanup()
    _json(result)
    return 0 if result["request"]["status"] < 500 else 1


def _check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise CliError("--port must be between 1 and 65535")
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise CliError(f"cannot bind 127.0.0.1:{port}: {exc}") from exc


def _serve(port: int) -> int:
    _check_port(port)
    runtime = None
    process = None
    previous_handler = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        runtime = create_runtime()
        process = subprocess.Popen(
            [sys.executable, "-m", "verification", "_worker", "serve", str(port)],
            cwd=runtime.source_root,
            env=runtime.environment,
            start_new_session=True,
        )
        _json({
            "status": "serving",
            "base_url": f"http://127.0.0.1:{port}",
            "mode": "isolated-http",
            "lifespan": "skipped",
            "fixture": {"date": runtime.fixture["date"], "user": runtime.fixture["user"]},
        })
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process is not None:
            stop_process(process)
        if runtime is not None:
            runtime.cleanup()
        signal.signal(signal.SIGTERM, previous_handler)


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "_worker":
        if len(values) < 3 or values[1] not in {"request", "verify", "serve"}:
            _json({"status": "error", "error": "invalid internal worker invocation"})
            return 2
        from verification.worker import run_worker as execute_worker

        try:
            _json(execute_worker(values[1], values[2:]))
        except ValueError as exc:
            _json({"status": "error", "error": str(exc)})
            return 2
        return 0
    arguments = _parser().parse_args(values)
    try:
        if arguments.command == "features":
            selected = FEATURES if arguments.feature is None else (FEATURE_BY_ID[arguments.feature],)
            _json({"features": [feature_payload(feature) for feature in selected]})
            return 0
        if arguments.command == "doctor":
            return _doctor()
        if arguments.command == "request":
            result = _external_request(arguments.path, arguments.base_url) if arguments.base_url else None
            if result is not None:
                _json(result)
                return 0 if result["request"]["status"] < 500 else 1
            return _fixture_request(arguments.path)
        if arguments.command == "verify":
            return _verify(arguments.feature, arguments.evidence)
        if arguments.command == "serve":
            return _serve(arguments.port)
    except (CliError, OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        _json({"status": "error", "error": str(exc)})
        return 2
    raise CliError(f"unknown command: {arguments.command}")
