"""Tests for orchestrator/newsletter.py — HTML conversion, footer preservation, broadcast."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from orchestrator.newsletter import (
    render_html, send_newsletter, validate_report,
    broadcast_to_subscribers, SUBSCRIBER_FOOTER,
)


# ── Sample footer matching the structure from memory/feedback.py ──────────

SAMPLE_FOOTER = """\
---

## How This Newsletter Learns From You

This newsletter is **personalized by your feedback**. Just reply to this email and I'll adjust what I research for you.

**Things you can tell me:**
- "More coverage on [topic]" — I'll prioritize it in future issues
- "Less [topic]" — I'll deprioritize it
- "I loved the section on [X]" — I'll find more like it

*Just hit reply — no format required. I read every response.*"""

SAMPLE_REPORT = """\
# Daily AI Research — 2026-03-16

## Top Stories

Some research content here.

### Finding 1
- Detail A
- Detail B

## Sources
- Source 1
- Source 2"""


# ══════════════════════════════════════════════════════════════════════════════
# render_html — footer preservation
# ══════════════════════════════════════════════════════════════════════════════


class TestRenderHTMLFooter:
    """Verify that the feedback footer survives markdown-to-HTML conversion."""

    def test_footer_heading_in_html(self):
        """The footer heading must appear in the rendered HTML."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        assert "How This Newsletter Learns From You" in html

    def test_footer_personalized_text_in_html(self):
        """The 'personalized by your feedback' text must survive conversion."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        assert "personalized by your feedback" in html

    def test_footer_reply_cta_in_html(self):
        """The 'Just hit reply' call-to-action must survive conversion."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        assert "Just hit reply" in html

    def test_footer_hr_rendered(self):
        """The --- separator before the footer must render as <hr>."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        assert "<hr" in html

    def test_footer_bold_rendered(self):
        """Bold text in the footer must be converted to <strong> tags."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        # The footer heading is an h2, not bold text — check footer body bold
        assert "<strong>personalized by your feedback</strong>" in html

    def test_footer_italic_rendered(self):
        """Italic text in the footer must be converted to <em> tags."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        assert "<em>" in html
        assert "Just hit reply" in html

    def test_report_without_footer(self):
        """A report without footer should render normally."""
        html = render_html(SAMPLE_REPORT)
        assert "Daily AI Research" in html
        assert "How This Newsletter Learns From You" not in html

    def test_full_report_with_footer_is_complete(self):
        """Both report and footer content must appear in final HTML."""
        md = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        html = render_html(md)
        # Report content
        assert "Top Stories" in html
        assert "Finding 1" in html
        # Footer content
        assert "How This Newsletter Learns From You" in html
        assert "personalized by your feedback" in html
        # HTML structure
        assert html.strip().startswith("<!DOCTYPE html>")
        assert html.strip().endswith("</html>")


# ══════════════════════════════════════════════════════════════════════════════
# send_newsletter — footer through the full send path
# ══════════════════════════════════════════════════════════════════════════════


class TestSendNewsletterFooter:
    """Verify that the footer is included in the email payload sent to Resend."""

    @pytest.fixture
    def report_with_footer(self, tmp_path):
        """Create a temp report file with footer appended (simulating runner.py)."""
        report = tmp_path / "2026-03-16.md"
        content = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        report.write_text(content)
        return report

    @pytest.fixture
    def user_config(self):
        return {
            "email": "test@example.com",
            "newsletter_title": "Test Newsletter",
            "reply_to": "feedback@test.com",
        }

    @patch("orchestrator.newsletter.keychain_lookup")
    @patch("orchestrator.newsletter.requests.post")
    def test_html_payload_includes_footer(
        self, mock_post, mock_keychain, report_with_footer, user_config
    ):
        """The HTML payload sent to Resend must include the footer content."""
        mock_keychain.return_value = "fake-api-key"
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"id": "test-123"}

        result = send_newsletter(
            report_with_footer, user_config, "2026-03-16",
        )

        assert result["success"] is True

        # Inspect the actual payload sent to Resend
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        # HTML version must include footer
        assert "How This Newsletter Learns From You" in payload["html"]
        assert "personalized by your feedback" in payload["html"]

        # Plain text version must include footer
        assert "How This Newsletter Learns From You" in payload["text"]
        assert "personalized by your feedback" in payload["text"]

    @patch("orchestrator.newsletter.keychain_lookup")
    @patch("orchestrator.newsletter.requests.post")
    def test_report_content_param_overrides_file(
        self, mock_post, mock_keychain, tmp_path, user_config
    ):
        """When report_content is passed, it should be used instead of the file."""
        mock_keychain.return_value = "fake-api-key"
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"id": "test-456"}

        # Write a report WITHOUT footer to the file
        report = tmp_path / "2026-03-16.md"
        report.write_text(SAMPLE_REPORT)

        # But pass content WITH footer directly
        content_with_footer = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER

        result = send_newsletter(
            report, user_config, "2026-03-16",
            report_content=content_with_footer,
        )

        assert result["success"] is True

        # The payload must use the provided content (with footer),
        # NOT the file content (without footer)
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        assert "How This Newsletter Learns From You" in payload["html"]
        assert "personalized by your feedback" in payload["html"]
        assert "How This Newsletter Learns From You" in payload["text"]

    @patch("orchestrator.newsletter.keychain_lookup")
    @patch("orchestrator.newsletter.requests.post")
    def test_file_without_footer_omits_footer_in_email(
        self, mock_post, mock_keychain, tmp_path, user_config
    ):
        """If the file has no footer and no content override, email has no footer."""
        mock_keychain.return_value = "fake-api-key"
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"id": "test-789"}

        report = tmp_path / "2026-03-16.md"
        report.write_text(SAMPLE_REPORT)

        result = send_newsletter(report, user_config, "2026-03-16")

        assert result["success"] is True

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")

        # No footer in file = no footer in email
        assert "How This Newsletter Learns From You" not in payload["html"]
        assert "How This Newsletter Learns From You" not in payload["text"]


# ══════════════════════════════════════════════════════════════════════════════
# validate_report — should not strip the footer
# ══════════════════════════════════════════════════════════════════════════════


class TestValidateReportFooter:
    """Ensure validate_report does not strip footer content."""

    def test_validate_preserves_footer(self, tmp_path):
        """validate_report must not remove the feedback footer."""
        report = tmp_path / "report.md"
        content = SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        report.write_text(content)

        validate_report(report)

        after = report.read_text()
        assert "How This Newsletter Learns From You" in after
        assert "personalized by your feedback" in after

    def test_validate_strips_duplicate_preamble_heading(self, tmp_path):
        """Duplicate h1 preamble from synthesis agent is stripped."""
        report = tmp_path / "report.md"
        content = (
            "# Ramsay Research Agent — April 2, 2026\n\n"
            "Now I have everything I need. Let me write the full newsletter.\n\n"
            "# Ramsay Research Agent, April 2, 2026\n\n"
            "*162 findings from 12 agents.*\n\n"
            "## Top Stories\n\nContent.\n"
        )
        report.write_text(content)

        validate_report(report)

        after = report.read_text()
        assert after.startswith("# Ramsay Research Agent, April 2, 2026")
        assert "Now I have everything" not in after
        assert "Top Stories" in after

    def test_validate_strips_junk_but_keeps_footer(self, tmp_path):
        """Junk lines before the heading are stripped; footer is kept."""
        report = tmp_path / "report.md"
        content = "junk line 1\njunk line 2\n" + SAMPLE_REPORT + "\n\n" + SAMPLE_FOOTER
        report.write_text(content)

        result = validate_report(report)

        assert result["junk_lines_stripped"] == 2
        after = report.read_text()
        assert after.startswith("# Daily AI Research")
        assert "How This Newsletter Learns From You" in after


# ══════════════════════════════════════════════════════════════════════════════
# broadcast_to_subscribers
# ══════════════════════════════════════════════════════════════════════════════


def _mock_contacts_response(contacts, has_more=False):
    """Build a mock Resend contacts API response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "data": contacts,
        "has_more": has_more,
    }
    return resp


def _mock_send_response(resend_id="re_test"):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"id": resend_id}
    return resp


class TestBroadcastToSubscribers:
    """broadcast_to_subscribers: fetches audience, skips exclusions, sends."""

    @patch("orchestrator.newsletter.time.sleep")
    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_skips_excluded_emails_case_insensitive(
        self, mock_kc, mock_requests, mock_sleep
    ):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        contacts = [
            {"id": "c1", "email": "Alice@Example.com", "unsubscribed": False},
            {"id": "c2", "email": "bob@test.com", "unsubscribed": False},
        ]
        mock_requests.get.return_value = _mock_contacts_response(contacts)
        mock_requests.post.return_value = _mock_send_response()

        result = broadcast_to_subscribers(
            "# Report", "2026-04-02",
            exclude_emails=["alice@example.com"],
        )

        assert result["sent_count"] == 1
        assert result["skipped_count"] == 1
        # Only bob should be sent to
        send_call = mock_requests.post.call_args
        payload = send_call.kwargs.get("json") or send_call[1].get("json")
        assert payload["to"] == ["bob@test.com"]

    @patch("orchestrator.newsletter.time.sleep")
    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_skips_unsubscribed(self, mock_kc, mock_requests, mock_sleep):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        contacts = [
            {"id": "c1", "email": "a@test.com", "unsubscribed": True},
            {"id": "c2", "email": "b@test.com", "unsubscribed": False},
        ]
        mock_requests.get.return_value = _mock_contacts_response(contacts)
        mock_requests.post.return_value = _mock_send_response()

        result = broadcast_to_subscribers("# Report", "2026-04-02")

        assert result["sent_count"] == 1
        assert result["skipped_count"] == 1

    @patch("orchestrator.newsletter.time.sleep")
    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_uses_subscriber_footer_not_feedback(
        self, mock_kc, mock_requests, mock_sleep
    ):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        contacts = [{"id": "c1", "email": "a@test.com", "unsubscribed": False}]
        mock_requests.get.return_value = _mock_contacts_response(contacts)
        mock_requests.post.return_value = _mock_send_response()

        broadcast_to_subscribers("# Report", "2026-04-02")

        payload = mock_requests.post.call_args.kwargs.get("json") or \
                  mock_requests.post.call_args[1].get("json")

        # Should contain subscriber footer
        assert "mindpattern.ai" in payload["text"]
        assert "Unsubscribe" in payload["text"]
        # Should NOT contain feedback footer
        assert "How This Newsletter Learns From You" not in payload["text"]

    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_empty_audience(self, mock_kc, mock_requests):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        mock_requests.get.return_value = _mock_contacts_response([])

        result = broadcast_to_subscribers("# Report", "2026-04-02")

        assert result["sent_count"] == 0
        mock_requests.post.assert_not_called()

    @patch("orchestrator.newsletter.keychain_lookup")
    def test_no_api_key(self, mock_kc):
        mock_kc.return_value = None

        result = broadcast_to_subscribers("# Report", "2026-04-02")

        assert result["sent_count"] == 0
        assert any("resend-api-key" in e for e in result["errors"])

    @patch("orchestrator.newsletter.time.sleep")
    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_pagination(self, mock_kc, mock_requests, mock_sleep):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        page1 = _mock_contacts_response(
            [{"id": "c1", "email": "a@test.com", "unsubscribed": False}],
            has_more=True,
        )
        page2 = _mock_contacts_response(
            [{"id": "c2", "email": "b@test.com", "unsubscribed": False}],
            has_more=False,
        )
        mock_requests.get.side_effect = [page1, page2]
        mock_requests.post.return_value = _mock_send_response()

        result = broadcast_to_subscribers("# Report", "2026-04-02")

        assert result["sent_count"] == 2
        assert mock_requests.get.call_count == 2

    @patch("orchestrator.newsletter.time.sleep")
    @patch("orchestrator.newsletter.requests")
    @patch("orchestrator.newsletter.keychain_lookup")
    def test_caps_at_max_contacts(self, mock_kc, mock_requests, mock_sleep):
        mock_kc.side_effect = lambda s: {
            "resend-api-key": "key", "resend-audience-id": "aud-123"
        }.get(s)

        contacts = [
            {"id": f"c{i}", "email": f"user{i}@test.com", "unsubscribed": False}
            for i in range(60)
        ]
        mock_requests.get.return_value = _mock_contacts_response(contacts)
        mock_requests.post.return_value = _mock_send_response()

        result = broadcast_to_subscribers("# Report", "2026-04-02")

        # Should cap at MAX_BROADCAST_CONTACTS (50)
        assert result["sent_count"] == 50
        assert mock_requests.post.call_count == 50
