"""Bearer token authentication for the dashboard API.

Generate a token: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
Store hash: API_TOKEN_HASH env var = hashlib.sha256(token.encode()).hexdigest()

Public endpoints (no auth): GET /api/findings, /api/sources, /api/patterns,
/api/finding, /api/related, /api/feed, /api/issues, /api/stories, /api/skills, /api/stats,
/api/entities, /api/reports, /api/audio-briefings, /healthz
Private endpoints (auth required): everything else under /api/
"""

import hashlib
import os
from functools import wraps
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

def get_token_hash() -> str:
    """Get the API token hash from environment."""
    return os.environ.get("API_TOKEN_HASH", "")

async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency for private endpoints. Raises 401 if token invalid."""
    token_hash = get_token_hash()
    if not token_hash:
        raise HTTPException(status_code=500, detail="API_TOKEN_HASH not configured")
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization required")
    provided_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    if provided_hash != token_hash:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

# Public routes (no auth needed). This list IS the contract with the
# vercel-mindpattern site (tests/test_api_contract.py) — public reads only.
PUBLIC_PREFIXES = [
    "/api/search",
    "/api/finding",
    "/api/related",
    "/api/feed",
    "/api/issues",
    "/api/stories",
    "/api/entities",
    "/api/findings",
    "/api/stats",
    "/api/patterns",
    "/api/narrative-arcs",
    "/api/sources",
    "/api/skills",        # covers /api/skills/search
    "/api/skill-domains",
    "/api/health",
    "/api/reports",
    "/api/audio-briefings",
    "/healthz",
    "/mcp",               # MCP server for the site's chat tab (lands in v4 M1)
]

def is_public_route(path: str) -> bool:
    """Check if a route is public (no auth required)."""
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _token_valid(token: str) -> bool:
    token_hash = get_token_hash()
    return bool(token_hash) and hashlib.sha256(token.encode()).hexdigest() == token_hash


def _pipeline_secret_valid(provided: str | None) -> bool:
    """Shared secret for the local pipeline's approval submit/poll calls."""
    expected = os.environ.get("MP_PIPELINE_SECRET", "")
    return bool(expected) and provided == expected


async def enforce_auth(request: Request, call_next):
    """Default-deny middleware: everything not on the public allowlist
    requires a bearer token (or the pipeline secret for /api/approvals).

    Fails CLOSED: with no API_TOKEN_HASH configured, private routes are
    unreachable rather than open (the v3 failure was enforcement that
    existed but was never wired in — see docs/audit-2026-06-11.md).
    """
    from fastapi.responses import JSONResponse

    if request.method == "OPTIONS":  # CORS preflight
        return await call_next(request)

    if is_public_route(request.url.path) and request.method in ("GET", "HEAD"):
        return await call_next(request)

    if request.url.path.startswith("/api/approvals") and _pipeline_secret_valid(
        request.headers.get("X-Pipeline-Secret")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and _token_valid(auth_header[7:]):
        return await call_next(request)

    return JSONResponse({"detail": "Authorization required"}, status_code=401)
