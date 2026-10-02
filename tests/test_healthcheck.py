"""Tests for scripts/healthcheck.py — no network, no real subprocess calls."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# Registered as "healthcheck", NOT "preflight" — that name belongs to the
# preflight/ data-collection package, and shadowing it in sys.modules would
# break any later test that imports the real package.
_spec = importlib.util.spec_from_file_location("healthcheck", REPO / "scripts" / "healthcheck.py")
preflight = importlib.util.module_from_spec(_spec)
sys.modules["healthcheck"] = preflight
_spec.loader.exec_module(preflight)


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- claude auth ---------------------------------------------------------


def test_claude_auth_passes_when_token_echoed(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda *a, **k: "/fake/claude")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: _Proc(stdout="AUTH_OK\n"))
    r = preflight.check_claude_auth()
    assert r.ok and r.required


def test_claude_auth_fails_when_logged_out(monkeypatch):
    """The exact symptom of a subscription swap that did not take."""
    monkeypatch.setattr(preflight.shutil, "which", lambda *a, **k: "/fake/claude")
    monkeypatch.setattr(
        preflight.subprocess, "run",
        lambda *a, **k: _Proc(returncode=1, stdout="Not logged in · Please run /login"),
    )
    r = preflight.check_claude_auth()
    assert not r.ok
    assert "Not logged in" in r.detail


def test_claude_auth_fails_when_not_on_launchd_path(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda *a, **k: None)
    r = preflight.check_claude_auth()
    assert not r.ok
    assert "launchd PATH" in r.detail


def test_claude_auth_uses_launchd_environment(monkeypatch):
    """A bare interactive `claude -p` can pass while the 8 AM run fails, so the
    check must run under launchd's minimal env, not the caller's."""
    seen = {}

    def fake_run(cmd, env=None, **kwargs):
        seen["env"] = env
        return _Proc(stdout="AUTH_OK")

    monkeypatch.setattr(preflight.shutil, "which", lambda *a, **k: "/fake/claude")
    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    preflight.check_claude_auth()
    assert seen["env"]["PATH"] == preflight.LAUNCHD_PATH
    assert "VIRTUAL_ENV" not in seen["env"]


def test_claude_auth_handles_timeout(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda *a, **k: "/fake/claude")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=180)

    monkeypatch.setattr(preflight.subprocess, "run", boom)
    r = preflight.check_claude_auth()
    assert not r.ok and "timed out" in r.detail


# --- claude account ------------------------------------------------------


def test_claude_account_reports_email_and_tier(monkeypatch, tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({
        "oauthAccount": {
            "emailAddress": "someone@example.com",
            "organizationRateLimitTier": "default_claude_max_5x",
        }
    }))
    monkeypatch.setattr(preflight.Path, "home", staticmethod(lambda: tmp_path))
    r = preflight.check_claude_account()
    assert r.ok
    assert "someone@example.com" in r.detail
    assert not r.required, "either subscription is valid; this is informational"


def test_claude_account_missing_config_is_not_required(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight.Path, "home", staticmethod(lambda: tmp_path))
    r = preflight.check_claude_account()
    assert not r.ok and not r.required


# --- fly ------------------------------------------------------------------


def test_fly_access_passes_when_app_visible(monkeypatch):
    monkeypatch.setattr(preflight, "_flyctl", lambda: "/fake/flyctl")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: _Proc(returncode=0))
    r = preflight.check_fly_app_access()
    assert r.ok and r.required


def test_fly_access_detects_logged_out(monkeypatch):
    monkeypatch.setattr(preflight, "_flyctl", lambda: "/fake/flyctl")
    monkeypatch.setattr(
        preflight.subprocess, "run",
        lambda *a, **k: _Proc(returncode=1, stderr="Error: no access token available."),
    )
    r = preflight.check_fly_app_access()
    assert not r.ok
    assert "flyctl auth login" in r.detail


def test_fly_access_detects_wrong_account(monkeypatch):
    """whoami succeeds on the wrong Fly account; only the app lookup catches it."""
    monkeypatch.setattr(preflight, "_flyctl", lambda: "/fake/flyctl")
    monkeypatch.setattr(
        preflight.subprocess, "run",
        lambda *a, **k: _Proc(returncode=1, stderr='Error: Could not find App "mindpattern"'),
    )
    r = preflight.check_fly_app_access()
    assert not r.ok
    assert "cannot see mindpattern" in r.detail


def test_fly_access_fails_when_flyctl_missing(monkeypatch):
    monkeypatch.setattr(preflight, "_flyctl", lambda: None)
    r = preflight.check_fly_app_access()
    assert not r.ok and "not found" in r.detail


# --- launchd / wake / venv ------------------------------------------------


def test_launchd_agent_loaded(monkeypatch):
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: _Proc(returncode=0))
    assert preflight.check_launchd_agent().ok


def test_launchd_agent_not_loaded(monkeypatch):
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: _Proc(returncode=1))
    r = preflight.check_launchd_agent()
    assert not r.ok and "not loaded" in r.detail


@pytest.mark.parametrize(
    "sched,batt,expected_ok",
    [
        ("wakepoweron at 4:55AM every day", "Now drawing from 'AC Power'", True),
        ("wakepoweron at 4:55AM every day", "Now drawing from 'Battery Power'", False),
        ("No scheduled events.", "Now drawing from 'AC Power'", False),
    ],
)
def test_wake_event(monkeypatch, sched, batt, expected_ok):
    calls = iter([_Proc(stdout=sched), _Proc(stdout=batt)])
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: next(calls))
    assert preflight.check_wake_event().ok is expected_ok


def test_wake_event_on_battery_explains_why(monkeypatch):
    calls = iter([
        _Proc(stdout="wakepoweron at 4:55AM every day"),
        _Proc(stdout="Now drawing from 'Battery Power'"),
    ])
    monkeypatch.setattr(preflight.subprocess, "run", lambda *a, **k: next(calls))
    assert "battery" in preflight.check_wake_event().detail


def test_venv_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight, "REPO", tmp_path)
    r = preflight.check_venv()
    assert not r.ok and r.required


# --- exit code ------------------------------------------------------------


def test_main_exits_nonzero_when_required_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "run_all", lambda: [
        preflight.Result("a", True, True, "fine"),
        preflight.Result("b", False, True, "broken"),
    ])
    monkeypatch.setattr(sys, "argv", ["preflight.py"])
    assert preflight.main() == 1
    assert "[FAIL] b" in capsys.readouterr().out


def test_main_exits_zero_when_only_optional_fails(monkeypatch, capsys):
    monkeypatch.setattr(preflight, "run_all", lambda: [
        preflight.Result("a", True, True, "fine"),
        preflight.Result("b", False, False, "meh"),
    ])
    monkeypatch.setattr(sys, "argv", ["preflight.py"])
    assert preflight.main() == 0
    assert "[WARN] b" in capsys.readouterr().out
