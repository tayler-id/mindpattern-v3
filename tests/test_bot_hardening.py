"""M0 Task 12 — bot hardening.

Fail-closed owner check, redelivered-event dedup, executor dispatch,
and the bot heartbeat that fails /healthz when the socket dies silently.
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# slack_sdk isn't installed in the test env; stub it so bot.py imports cleanly.
for mod in (
    "slack_sdk",
    "slack_sdk.errors",
    "slack_sdk.socket_mode",
    "slack_sdk.socket_mode.request",
    "slack_sdk.socket_mode.response",
):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from slack_bot import heartbeat  # noqa: E402
from slack_bot.bot import MindPatternBot  # noqa: E402


def make_bot(owner="U_OWNER"):
    """MindPatternBot without __init__ (no Slack connection)."""
    bot = MindPatternBot.__new__(MindPatternBot)
    bot.bot_user_id = "B_BOT"
    bot.owner_user_id = owner
    bot.handlers = {"C_CHAN": MagicMock()}
    bot._seen_events = {}
    bot._handler_executor = MagicMock()
    return bot


def make_req(text="do something", user="U_OWNER", ts="100.0", event_id=None):
    req = MagicMock()
    req.type = "events_api"
    req.envelope_id = "env-1"
    event = {
        "type": "message",
        "channel": "C_CHAN",
        "user": user,
        "text": text,
        "ts": ts,
        "event_ts": ts,
    }
    req.payload = {"event": event}
    if event_id:
        req.payload["event_id"] = event_id
    return req


class TestFailClosedOwnerCheck:
    def test_no_owner_configured_refuses_commands(self):
        bot = make_bot(owner="")
        bot._handle_event(MagicMock(), make_req(user="U_ANYONE"))
        bot._handler_executor.submit.assert_not_called()

    def test_non_owner_ignored(self):
        bot = make_bot(owner="U_OWNER")
        bot._handle_event(MagicMock(), make_req(user="U_STRANGER"))
        bot._handler_executor.submit.assert_not_called()

    def test_owner_message_dispatched(self):
        bot = make_bot(owner="U_OWNER")
        bot._handle_event(MagicMock(), make_req(user="U_OWNER"))
        bot._handler_executor.submit.assert_called_once()


class TestEventDedup:
    def test_duplicate_event_id_processed_once(self):
        bot = make_bot()
        bot._handle_event(MagicMock(), make_req(event_id="Ev123"))
        bot._handle_event(MagicMock(), make_req(event_id="Ev123"))
        assert bot._handler_executor.submit.call_count == 1

    def test_duplicate_channel_ts_processed_once(self):
        bot = make_bot()
        bot._handle_event(MagicMock(), make_req(ts="200.0"))
        bot._handle_event(MagicMock(), make_req(ts="200.0"))
        assert bot._handler_executor.submit.call_count == 1

    def test_distinct_events_both_processed(self):
        bot = make_bot()
        bot._handle_event(MagicMock(), make_req(ts="200.0"))
        bot._handle_event(MagicMock(), make_req(ts="201.0"))
        assert bot._handler_executor.submit.call_count == 2

    def test_dedup_entries_expire(self):
        bot = make_bot()
        bot._handle_event(MagicMock(), make_req(event_id="EvOld"))
        # Age the entry past the TTL
        bot._seen_events["EvOld"] = time.monotonic() - 9999
        bot._handle_event(MagicMock(), make_req(event_id="EvOld"))
        assert bot._handler_executor.submit.call_count == 2


class TestRunHandlerErrorReporting:
    def test_handler_error_replies_in_thread(self):
        bot = make_bot()
        handler = MagicMock()
        handler.handle.side_effect = RuntimeError("boom")
        bot._run_handler(handler, "C_CHAN", {"ts": "1.0"})
        handler.reply.assert_called_once()


class TestHeartbeat:
    def test_touch_creates_file_and_is_fresh(self, tmp_path, monkeypatch):
        hb = tmp_path / "bot-heartbeat"
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(hb))
        heartbeat.touch()
        assert hb.exists()
        assert heartbeat.is_stale() is False

    def test_missing_file_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(tmp_path / "nope"))
        assert heartbeat.is_stale() is True

    def test_old_file_is_stale(self, tmp_path, monkeypatch):
        hb = tmp_path / "bot-heartbeat"
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(hb))
        heartbeat.touch()
        old = time.time() - 600
        os.utime(hb, (old, old))
        assert heartbeat.is_stale() is True


class TestHealthzBotLiveness:
    def _client(self):
        from fastapi.testclient import TestClient

        from dashboard.app import app

        return TestClient(app)

    def test_stale_heartbeat_on_fly_returns_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(tmp_path / "missing"))
        monkeypatch.setenv("FLY_APP_NAME", "mindpattern")
        with self._client() as client:
            resp = client.get("/healthz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "bot-dead"

    def test_fresh_heartbeat_on_fly_returns_200(self, tmp_path, monkeypatch):
        hb = tmp_path / "bot-heartbeat"
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(hb))
        monkeypatch.setenv("FLY_APP_NAME", "mindpattern")
        heartbeat.touch()
        with self._client() as client:
            resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["bot"] == "alive"

    def test_stale_heartbeat_off_fly_stays_200(self, tmp_path, monkeypatch):
        """Local dev (no FLY_APP_NAME): report status, never 503."""
        monkeypatch.setenv("MP_BOT_HEARTBEAT_PATH", str(tmp_path / "missing"))
        monkeypatch.delenv("FLY_APP_NAME", raising=False)
        with self._client() as client:
            resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["bot"] == "stale"
