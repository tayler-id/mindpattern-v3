"""Bearer token authentication for the dashboard API.

Generate a token: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
Store hash: API_TOKEN_HASH env var = hashlib.sha256(token.encode()).hexdigest()

Public endpoints (no auth): GET /api/findings, /api/sources, /api/patterns, /api/skills, /api/stats, /healthz
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

# Public routes (no auth needed)
PUBLIC_PREFIXES = [
    "/api/findings",
    "/api/sources",
    "/api/patterns",
    "/api/skills",
    "/api/stats",
    "/healthz",
]

def is_public_route(path: str) -> bool:
    """Check if a route is public (no auth required)."""
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)
