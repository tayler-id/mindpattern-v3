"""Contract tests for the public JSON API consumed by vercel-mindpattern.

These 12 GET endpoints ARE the contract with the live site (mindpattern.ai →
mindpattern.fly.dev). Fixtures in tests/fixtures/api/ were snapshotted from the
deployed app on 2026-06-11.

Shape rule: every key present in the fixture must exist in the response with
the same JSON type. Additive fields are allowed; removed keys and type changes
are breaking. (/mcp is deliberately absent: the live backend 404s it today —
it becomes a real endpoint in v4 M1.)

Run modes:
    default            — in-process TestClient against dashboard.app
    MP_CONTRACT_LIVE=1 — hits https://mindpattern.fly.dev (post-deploy check)
"""

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "api"
LIVE_BASE = "https://mindpattern.fly.dev"

ENDPOINTS = [
    ("search_q_ai_limit_3", "/api/search?q=ai&limit=3&user=ramsay"),
    ("findings_limit_5", "/api/findings?limit=5&user=ramsay"),
    ("stats", "/api/stats?user=ramsay"),
    ("patterns", "/api/patterns?user=ramsay"),
    ("sources", "/api/sources?user=ramsay"),
    ("skills", "/api/skills?user=ramsay"),
    ("skills_search_q_agents_limit_3", "/api/skills/search?q=agents&limit=3&user=ramsay"),
    ("skill-domains", "/api/skill-domains?user=ramsay"),
    ("health", "/api/health?user=ramsay"),
    ("reports", "/api/reports?user=ramsay"),
    ("reports_single", "/api/reports/2026-06-10?user=ramsay"),
    ("reports_search", "/api/reports/search?q=agents&limit=3&user=ramsay"),
]


def _json_type(value):
    """Collapse JSON types: ints and floats are both 'number'."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "null"


def assert_same_shape(fixture, actual, path="$"):
    """Every fixture key must exist in actual with the same JSON type."""
    ftype = _json_type(fixture)
    if ftype == "null":
        return  # fixture gave no type information for this field
    atype = _json_type(actual)
    if atype == "null":
        # live data may legitimately have nulls where the fixture had values
        return
    assert atype == ftype, f"{path}: expected {ftype}, got {atype}"
    if ftype == "dict":
        for key, fval in fixture.items():
            assert key in actual, f"{path}.{key}: key missing from response"
            assert_same_shape(fval, actual[key], f"{path}.{key}")
    elif ftype == "list" and fixture and actual:
        assert_same_shape(fixture[0], actual[0], f"{path}[0]")


@pytest.fixture(scope="module")
def client():
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        import httpx

        with httpx.Client(base_url=LIVE_BASE, timeout=30) as c:
            yield c
    else:
        from fastapi.testclient import TestClient

        from dashboard.app import app

        with TestClient(app) as c:
            yield c


@pytest.mark.parametrize("fixture_name,path", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_endpoint_contract(client, fixture_name, path):
    fixture = json.loads((FIXTURES / f"{fixture_name}.json").read_text())
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    body = resp.json()
    # An endpoint that returned data on 2026-06-11 must not start returning empty.
    if _json_type(fixture) == "list" and fixture:
        assert body, f"{path}: returned empty list, fixture had data"
    assert_same_shape(fixture, body, path)


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
