"""The site proxy's allowlist mirrors the backend's public surface.

src/app/api/proxy/[...path]/route.ts (vercel-mindpattern) hand-lists the
first path segments it forwards, and dashboard/auth.py hand-lists the public
prefixes. Nothing failed when the two drifted. A public endpoint added only
in auth.py 404s through the proxy for client-side fetches, and a proxy
segment with no public prefix behind it 401s at the backend. This test
parses the frontend file out of the sibling checkout and pins the mirror,
with every deliberate difference named.

Skips when the frontend checkout is not next to this repo, so the suite
stays runnable from a bare clone.
"""

import re
from pathlib import Path

import pytest

from dashboard.auth import PUBLIC_PREFIXES

FRONTEND_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "mindpattern-rabbit-hole"
    / "src"
    / "app"
    / "api"
    / "proxy"
    / "[...path]"
    / "route.ts"
)

# Public GET prefixes that are deliberately not proxied. warmup is the
# pipeline's own poll target, never fetched by a reader page.
NOT_PROXIED = {"warmup"}
# Public surface that is not a GET /api/<segment> shape at all.
NOT_SEGMENTS = {"/healthz", "/mcp"}
# The analytics beacon goes through the proxy's POST allowlist instead.
POST_ONLY = {"event"}


def _frontend_sets(source: str) -> tuple[set[str], set[str]]:
    def parse(name: str) -> set[str]:
        match = re.search(name + r"\s*=\s*new Set\(\[(.*?)\]\)", source, re.S)
        assert match, f"{name} not found in route.ts"
        segments = set(re.findall(r"'([a-z0-9-]+)'", match.group(1)))
        assert segments, f"{name} parsed empty; the route.ts shape changed"
        return segments

    return parse("PUBLIC_GET_SEGMENTS"), parse("PUBLIC_POST_SEGMENTS")


def test_the_proxy_allowlist_mirrors_the_backend_public_surface():
    if not FRONTEND_ROUTE.is_file():
        pytest.skip("vercel-mindpattern checkout not present next to this repo")
    get_segments, post_segments = _frontend_sets(FRONTEND_ROUTE.read_text())

    backend_segments = {
        prefix.removeprefix("/api/").strip("/")
        for prefix in PUBLIC_PREFIXES
        if prefix not in NOT_SEGMENTS
    }

    assert post_segments == POST_ONLY

    missing_from_proxy = backend_segments - get_segments - NOT_PROXIED - POST_ONLY
    assert not missing_from_proxy, (
        "public backend endpoints the proxy cannot reach; add each segment to "
        "PUBLIC_GET_SEGMENTS in route.ts or to NOT_PROXIED here: "
        f"{sorted(missing_from_proxy)}"
    )

    dead_proxy_segments = get_segments - backend_segments
    assert not dead_proxy_segments, (
        "proxy segments with no public backend prefix behind them; every one "
        f"401s at the backend: {sorted(dead_proxy_segments)}"
    )
