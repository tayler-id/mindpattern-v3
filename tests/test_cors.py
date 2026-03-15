"""Tests for CORS middleware configuration on dashboard app.

Verifies that CORSMiddleware is configured to allow only
https://mindpattern.fly.dev with the correct methods and headers.
"""

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


ALLOWED_ORIGIN = "https://mindpattern.fly.dev"
DISALLOWED_ORIGIN = "https://evil.example.com"


class TestCORSAllowedOrigin:
    """Requests from https://mindpattern.fly.dev get proper CORS headers."""

    def test_preflight_returns_cors_headers(self, client):
        """OPTIONS preflight from allowed origin returns access-control headers."""
        resp = client.options(
            "/",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
        assert "GET" in resp.headers.get("access-control-allow-methods", "")
        assert "POST" in resp.headers.get("access-control-allow-methods", "")
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_simple_get_returns_cors_origin(self, client):
        """A normal GET from the allowed origin includes the CORS origin header."""
        resp = client.get("/", headers={"Origin": ALLOWED_ORIGIN})
        assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    def test_allowed_headers_include_authorization_and_content_type(self, client):
        """Preflight response advertises Authorization and Content-Type."""
        resp = client.options(
            "/",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        allowed = resp.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allowed
        assert "content-type" in allowed


class TestCORSDisallowedOrigin:
    """Requests from unknown origins must NOT receive CORS allow headers."""

    def test_preflight_from_disallowed_origin_no_allow(self, client):
        """OPTIONS from a disallowed origin must not echo that origin back."""
        resp = client.options(
            "/",
            headers={
                "Origin": DISALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = resp.headers.get("access-control-allow-origin")
        assert acao != DISALLOWED_ORIGIN
        assert acao != "*"

    def test_simple_get_from_disallowed_origin_no_allow(self, client):
        """GET from a disallowed origin must not include allow-origin for it."""
        resp = client.get("/", headers={"Origin": DISALLOWED_ORIGIN})
        acao = resp.headers.get("access-control-allow-origin")
        assert acao != DISALLOWED_ORIGIN
        assert acao != "*"
