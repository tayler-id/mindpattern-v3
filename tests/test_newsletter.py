"""Tests for orchestrator/newsletter.py — HTML conversion and footer preservation."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.newsletter import render_html, send_newsletter, validate_report


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
