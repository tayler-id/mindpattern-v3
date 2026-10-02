"""The word bank has to be enforced, not just described.

One test per surface. Each asserts that "landed" reaches a deterministic gate,
because prompt-only enforcement is what let it into 9 of 10 August issues.
"""

import pytest

from orchestrator import word_bank

LANDED_POST = (
    "Streaming support landed in 2.1.239 and the docs are already stale. "
    "https://example.com/changelog https://mindpattern.ai"
)


class TestSocialGate:
    def test_deterministic_validate_rejects_a_bank_term(self):
        from social.critics import deterministic_validate

        errors = deterministic_validate("linkedin", LANDED_POST)
        assert any("landed" in e.lower() for e in errors), errors

    def test_a_clean_post_still_passes(self):
        from social.critics import deterministic_validate

        clean = (
            "Streaming shipped in 2.1.239 and the docs are already stale. "
            "https://example.com/changelog https://mindpattern.ai"
        )
        assert deterministic_validate("linkedin", clean) == []

    def test_the_error_names_the_replacement(self):
        """A gate that only says no makes the next draft a guess."""
        from social.critics import deterministic_validate

        errors = [e for e in deterministic_validate("linkedin", LANDED_POST)
                  if "landed" in e.lower()]
        assert "->" in errors[0] and len(errors[0].split("->")[1]) > 20


class TestSiteGate:
    def test_lint_site_copy_fails_a_bank_term(self):
        from orchestrator.site_copy_lint import lint_site_copy

        issues = lint_site_copy(
            {
                "title": "Streaming support in 2.1.239",
                "dek": "The release note is one line long.",
                "take": "Support landed without a migration note.",
                "why_now": "The tag is public.",
                "body_markdown": "The tag is public and the SDK compiles.",
            },
            include_revise=False,
        )
        landed = [i for i in issues if "landed" in i.excerpt.lower()
                  or "landed" in i.message.lower()]
        assert landed, [i.as_dict() for i in issues]
        assert landed[0].severity == "fail"
        assert landed[0].field == "take"

    def test_clean_copy_has_no_bank_issue(self):
        from orchestrator.site_copy_lint import lint_site_copy

        issues = lint_site_copy(
            {
                "title": "Streaming support in 2.1.239",
                "dek": "The release note is one line long.",
                "take": "Support shipped without a migration note.",
                "why_now": "The tag is public.",
                "body_markdown": "The tag is public and the SDK compiles.",
            },
            include_revise=False,
        )
        assert not [i for i in issues if i.code == "word_bank"]


class TestNewsletterGate:
    def test_the_prose_gate_reports_bank_hits(self):
        from orchestrator.prose_gate import scan

        report = scan("Streaming support landed in 2.1.239.\n")
        assert report["word_bank_hits"] == 1
        assert any("landed" in v for v in report["word_bank"])

    def test_sanitize_carries_the_bank_report_through(self):
        from orchestrator.prose_gate import sanitize

        _, report = sanitize("Streaming support landed in 2.1.239.\n")
        assert report["word_bank_hits"] == 1

    def test_a_clean_issue_reports_nothing(self):
        from orchestrator.prose_gate import scan

        report = scan("Streaming support shipped in 2.1.239.\n")
        assert report["word_bank_hits"] == 0

    def test_sanitize_never_rewrites_a_bank_term_itself(self):
        """Only a person or a writer pass can choose the replacement word."""
        from orchestrator.prose_gate import sanitize

        text = "Streaming support landed in 2.1.239.\n"
        clean, _ = sanitize(text)
        assert "landed" in clean


class TestEveryBanIsReachable:
    @pytest.mark.parametrize(
        "entry", [e for e in word_bank.BANK if e.tier == "ban"],
        ids=lambda e: e.term,
    )
    def test_each_ban_fires_on_its_own_example(self, entry):
        for surface in entry.surfaces:
            assert word_bank.violations(entry.example, surface), (
                f"{entry.term} does not fire on {surface}"
            )


class TestNewsletterPromptCarriesTheBank:
    """The writer has to be told every term the gate will measure."""

    def test_synthesis_pass2_prompt_names_every_newsletter_ban(self):
        import inspect

        from orchestrator import runner

        source = inspect.getsource(runner.ResearchPipeline._phase_synthesis)
        assert "word_bank.prompt_block(\"newsletter\")" in source, (
            "synthesis pass 2 does not inject the word bank, so the gate "
            "measures terms the writer was never given"
        )


class TestEngagementRepliesAreGated:
    """Replies went from the model straight to the platform, ungated."""

    def test_the_reply_prompt_carries_the_bank(self):
        import inspect

        from social import engagement

        source = inspect.getsource(engagement.EngagementPipeline._draft_replies)
        assert 'word_bank.prompt_block("engagement")' in source

    def test_a_reply_with_a_bank_term_is_rejected(self):
        from social.engagement import check_reply

        assert check_reply("Support landed last week, worth a look.")

    def test_a_clean_reply_passes(self):
        from social.engagement import check_reply

        assert check_reply("Support shipped last week. The docs are stale.") == []


class TestSiteWriterPrompt:
    def test_the_bank_survives_voice_guide_truncation(self):
        """voice.md is inlined and was silently cut at 12,000 chars.

        The file passed that length on 2026-08-23, so the tail of the humanize
        pass stopped reaching the writer. The bank is appended separately so its
        position in voice.md cannot decide whether the writer sees it.
        """
        from orchestrator import word_bank
        from orchestrator.site_writer import build_site_writer_prompt

        prompt = build_site_writer_prompt(
            {"candidate_id": "x"}, [],
            voice_text="v" * 40_000,
            rules_text="rules",
        )
        for entry in word_bank.entries_for("site"):
            if entry.tier == "ban":
                assert entry.term in prompt, entry.term

    def test_voice_guide_is_not_truncated_below_its_own_length(self):
        from pathlib import Path

        from orchestrator import site_writer

        voice = Path("data/ramsay/mindpattern/voice.md").read_text()
        assert len(site_writer._voice_excerpt(voice)) == len(voice.strip()), (
            "voice.md is longer than the excerpt limit, so the writer is "
            "reading a truncated voice guide"
        )


class TestEngagementRepair:
    """A violating reply gets one rewrite before it is thrown away.

    Social posts have a three-iteration critic loop. Replies had nothing, so
    gating them without a repair pass would silently drop 15% of the replies
    the 2026-08 corpus produced.
    """

    def test_a_violating_reply_is_rewritten_not_dropped(self):
        from social.engagement import repair_reply

        calls = []

        def runner(prompt):
            calls.append(prompt)
            return "Support shipped in 2.1.239. The docs are stale.", 0

        out = repair_reply("Support landed in 2.1.239.", runner=runner)
        assert out == "Support shipped in 2.1.239. The docs are stale."
        assert "landed" in calls[0], "the repair prompt must name the violation"

    def test_a_reply_that_stays_dirty_is_dropped(self):
        from social.engagement import repair_reply

        assert repair_reply(
            "Support landed.", runner=lambda p: ("It still landed.", 0)
        ) is None

    def test_a_failed_repair_call_drops_the_reply(self):
        from social.engagement import repair_reply

        assert repair_reply(
            "Support landed.", runner=lambda p: ("", 1)
        ) is None

    def test_a_clean_reply_is_returned_untouched_without_a_call(self):
        from social.engagement import repair_reply

        def runner(prompt):
            raise AssertionError("clean reply must not cost a model call")

        text = "Support shipped in 2.1.239."
        assert repair_reply(text, runner=runner) == text


class TestSiteSeverity:
    """A word the writer must never type is a hard fail. A rhetorical frame
    is a revision note, because rejecting the whole draft over a sentence
    shape costs a full regeneration and the critic can fix it in place.
    """

    def test_a_banned_word_hard_fails_the_draft(self):
        from orchestrator.site_copy_lint import hard_fail_issues, lint_site_copy

        issues = lint_site_copy(
            {
                "title": "Streaming support in 2.1.239",
                "dek": "One line of release note.",
                "take": "Support landed without a migration note.",
                "why_now": "The tag is public.",
                "body_markdown": "The tag is public.",
            }
        )
        assert [i for i in hard_fail_issues(issues) if i.code == "word_bank"]

    def test_a_banned_frame_is_a_revision_note_not_a_rejection(self):
        from orchestrator.site_copy_lint import (
            hard_fail_issues, lint_site_copy, revise_issues,
        )

        copy = {
            "title": "Streaming support in 2.1.239",
            "dek": "One line of release note.",
            "take": "Buffering is the part that broke.",
            "why_now": "The tag is public.",
            "body_markdown": "The tag is public.",
        }
        issues = lint_site_copy(copy)
        assert not [i for i in hard_fail_issues(issues) if i.code == "word_bank"]
        assert [i for i in revise_issues(issues) if i.code == "word_bank"]

    def test_every_entry_declares_a_valid_site_severity(self):
        from orchestrator import word_bank

        for entry in word_bank.BANK:
            assert entry.site_severity in ("fail", "revise"), entry.term
