"""M0 Task 13 — newsletter receipts + delivery truthfulness.

The audit's double-send scenario: a crash after send + resume must produce
zero duplicate emails. Receipts are claimed BEFORE sending; raw HTML in
agent-written markdown is escaped; the 4xx retry-classification bug
(`if e.response` is False for error responses) is fixed.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

import memory
from core import migrations
from orchestrator.newsletter import (
    broadcast_to_subscribers,
    render_html,
    send_newsletter,
)


@pytest.fixture
def db(tmp_path):
    conn = memory.get_db(tmp_path / "memory.db", user_id="test")
    migrations.migrate(conn)
    yield conn
    conn.close()


USER_CONFIG = {
    "email": "owner@example.com",
    "newsletter_title": "Test Letter",
    "reply_to": "reply@example.com",
}


def ok_response():
    resp = MagicMock()
    resp.json.return_value = {"id": "email-123"}
    resp.raise_for_status.return_value = None
    return resp


class TestNewsletterReceipt:
    @patch("orchestrator.newsletter.keychain_lookup", return_value="key")
    @patch("orchestrator.newsletter.requests.post")
    def test_resume_after_send_does_not_resend(self, mock_post, _kc, db, tmp_path):
        """Crash-after-send + resume = exactly one email (the audit scenario)."""
        mock_post.return_value = ok_response()
        report = tmp_path / "report.md"
        report.write_text("# Daily")

        first = send_newsletter(report, USER_CONFIG, "2026-06-11", db=db)
        second = send_newsletter(report, USER_CONFIG, "2026-06-11", db=db)

        assert first["success"] is True and first["skipped"] is False
        assert second["success"] is True and second["skipped"] is True
        assert mock_post.call_count == 1

    @patch("orchestrator.newsletter.keychain_lookup", return_value=None)
    def test_missing_api_key_releases_receipt(self, _kc, db, tmp_path):
        """A definite no-send failure frees the receipt for retry."""
        report = tmp_path / "report.md"
        report.write_text("# Daily")

        first = send_newsletter(report, USER_CONFIG, "2026-06-11", db=db)
        assert first["success"] is False

        with patch("orchestrator.newsletter.keychain_lookup", return_value="key"), \
             patch("orchestrator.newsletter.requests.post", return_value=ok_response()) as mock_post:
            retry = send_newsletter(
                report, USER_CONFIG, "2026-06-11",
                report_content="# Daily", db=db,
            )
        assert retry["success"] is True and retry["skipped"] is False
        assert mock_post.call_count == 1

    def test_kill_switch_blocks_send(self, db, tmp_path, monkeypatch):
        monkeypatch.setenv("MP_DISABLE_OUTBOUND", "1")
        report = tmp_path / "report.md"
        report.write_text("# Daily")

        with patch("orchestrator.newsletter.requests.post") as mock_post:
            result = send_newsletter(report, USER_CONFIG, "2026-06-11", db=db)

        mock_post.assert_not_called()
        assert result["success"] is False
        assert "MP_DISABLE_OUTBOUND" in result["error"]


class TestBroadcastReceipts:
    def _contacts_response(self, emails):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "data": [{"email": e, "unsubscribed": False} for e in emails],
            "has_more": False,
        }
        return resp

    @patch("orchestrator.newsletter.BROADCAST_DELAY_SECONDS", 0)
    @patch("orchestrator.newsletter.keychain_lookup", return_value="key-or-audience")
    def test_resumed_broadcast_skips_already_sent(self, _kc, db):
        with patch("orchestrator.newsletter.requests.get",
                   return_value=self._contacts_response(["a@x.com", "b@x.com"])), \
             patch("orchestrator.newsletter.requests.post",
                   return_value=ok_response()) as mock_post:
            first = broadcast_to_subscribers("# Daily", "2026-06-11", db=db)
            second = broadcast_to_subscribers("# Daily", "2026-06-11", db=db)

        assert first["sent_count"] == 2
        assert second["sent_count"] == 0
        assert second["skipped_count"] == 2
        assert mock_post.call_count == 2  # exactly one send per recipient ever

    @patch("orchestrator.newsletter.BROADCAST_DELAY_SECONDS", 0)
    @patch("orchestrator.newsletter.keychain_lookup", return_value="key-or-audience")
    def test_http_4xx_classified_correctly_no_retry(self, _kc, db):
        """Response.__bool__ is False for 4xx — classification must use
        `is not None` or a 400 looks like status 0 and gets retried."""
        error_resp = MagicMock()
        error_resp.__bool__ = MagicMock(return_value=False)  # like real 4xx
        error_resp.status_code = 400
        http_error = requests_lib.exceptions.HTTPError(response=error_resp)

        failing = MagicMock()
        failing.raise_for_status.side_effect = http_error

        with patch("orchestrator.newsletter.requests.get",
                   return_value=self._contacts_response(["a@x.com"])), \
             patch("orchestrator.newsletter.requests.post",
                   return_value=failing) as mock_post, \
             patch("orchestrator.newsletter.time.sleep"):
            result = broadcast_to_subscribers("# Daily", "2026-06-11", db=db)

        assert result["failed_count"] == 1
        assert "HTTP 400" in result["errors"][0]
        assert mock_post.call_count == 1  # 4xx must not retry


class TestRenderHtmlEscapesRawHtml:
    def test_script_tag_escaped(self):
        html = render_html("Hello <script>alert(1)</script> world")
        assert "<script>" not in html
        assert "alert(1)" in html  # content survives, tag is neutralized

    def test_markdown_still_renders(self):
        html = render_html("# Title\n\n**bold**")
        assert "<h1" in html
        assert "<strong>bold</strong>" in html


class TestProductionDbMigrated:
    """Regression for 2026-06-12: migrations existed and were tested but
    nothing ran them against the production db — DELIVER crashed on a
    missing receipts table and the newsletter silently didn't go out.
    get_db() is the chokepoint; it must migrate."""

    def test_get_db_applies_core_migrations(self, tmp_path):
        conn = memory.get_db(tmp_path / "fresh.db", user_id="test")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        receipts_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='receipts'"
        ).fetchone()
        conn.close()
        assert version >= 1
        assert receipts_table is not None

    def test_deliver_exception_still_produces_failure_result(self):
        """The runner wraps send_newsletter — an exception becomes a failure
        result so the Slack alert fires instead of being skipped."""
        from pathlib import Path

        source = Path(__file__).parent.parent.joinpath(
            "orchestrator", "runner.py"
        ).read_text()
        deliver = source.split("def _phase_deliver")[1].split("def _phase_learn")[0]
        assert "try:" in deliver and "except Exception" in deliver
        assert deliver.index("send_newsletter(") > deliver.index("try:")
