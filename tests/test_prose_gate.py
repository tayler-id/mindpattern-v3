"""Tests for the deterministic prose gate."""

from orchestrator.prose_gate import EM_DASH_BUDGET, sanitize, scan


def test_single_em_dash_becomes_colon():
    src = 'They call it "unhobbling" — stripping guardrails and rules.'
    clean, report = sanitize(src)
    assert clean == 'They call it "unhobbling": stripping guardrails and rules.'
    assert report["replaced"] == 1
    assert report["em_dashes_after"] == 0


def test_single_em_dash_becomes_semicolon_when_sentence_has_a_colon():
    """Never emit two colons in one sentence."""
    src = "The traps: listing ignores order_by — depth accepts only 0 or 1."
    clean, _ = sanitize(src)
    assert clean == "The traps: listing ignores order_by; depth accepts only 0 or 1."
    assert clean.count(":") == 1


def test_paired_em_dashes_become_commas():
    src = "A file carrying gotchas — the stuff that surprises you — rather than facts."
    clean, report = sanitize(src)
    assert clean == "A file carrying gotchas, the stuff that surprises you, rather than facts."
    assert report["replaced"] == 2


def test_three_or_more_in_one_sentence_are_left_for_review():
    """A mechanical rewrite is not safe past two; count it, do not mangle it."""
    src = "One — two — three — four."
    clean, report = sanitize(src)
    assert clean == src
    assert report["replaced"] == 0
    assert report["em_dashes_after"] == 3


def test_headings_are_exempt():
    """The H1 is built by runner.py as '# {title} — {date}' — our own format."""
    src = "# Ramsay Research Agent — July 27, 2026\n\nBody text — with a dash."
    clean, _ = sanitize(src)
    assert clean.startswith("# Ramsay Research Agent — July 27, 2026")
    assert "Body text: with a dash." in clean


def test_fenced_code_is_never_touched():
    src = "Prose — here.\n\n```python\nx = 1  # a — b\n```\n"
    clean, _ = sanitize(src)
    assert "x = 1  # a — b" in clean
    assert "Prose: here." in clean


def test_inline_code_and_link_targets_are_never_touched():
    src = "See `a — b` and [the docs](https://x.example/a—b) — worth reading."
    clean, _ = sanitize(src)
    assert "`a — b`" in clean
    assert "https://x.example/a—b" in clean
    assert clean.endswith(": worth reading.")


def test_bare_url_is_never_touched():
    src = "Fetch https://x.example/p—q — then parse it."
    clean, _ = sanitize(src)
    assert "https://x.example/p—q" in clean


def test_line_structure_and_whitespace_are_preserved():
    """The newsletter is published verbatim; layout must survive untouched."""
    src = "# H\n\n- item one — two\n- item two\n\n| a | b |\n|---|---|\n\nEnd.  Two spaces."
    clean, _ = sanitize(src)
    assert len(clean.split("\n")) == len(src.split("\n"))
    assert "|---|---|" in clean
    assert "End.  Two spaces." in clean


def test_sanitize_is_idempotent():
    src = "A — b. C — d — e. F — g — h — i."
    once, _ = sanitize(src)
    twice, report = sanitize(once)
    assert twice == once
    assert report["replaced"] == 0


def test_scan_reports_metrics_without_changing_text():
    src = "A — b. " * 10
    result = scan(src)
    assert result["em_dashes"] == 10
    assert result["words"] == len(src.split())
    assert result["budget"] == EM_DASH_BUDGET


def test_scan_flags_over_budget():
    assert scan("x — y. " * (EM_DASH_BUDGET + 1))["over_budget"] is True
    assert scan("x — y. " * EM_DASH_BUDGET)["over_budget"] is False


def test_clean_prose_passes_through_unchanged():
    src = "Not paperclips. Just reward hacking with a bigger blast radius.\n\nGo look."
    clean, report = sanitize(src)
    assert clean == src
    assert report["replaced"] == 0
    assert report["remaining_over_budget"] is False


def test_self_referential_word_count_is_corrected_to_the_real_length():
    """2026-08-04 promised 'the next 4,000 words' above an 8,100-word issue."""
    body = " ".join(["word"] * 2000)
    src = f"I'll spend the next 4,000 words explaining why.\n\n{body}"
    clean, report = sanitize(src)
    assert "the next 2,000 words" in clean
    assert "4,000 words" not in clean
    assert report["length_claims_corrected"] == 1


def test_length_claim_already_accurate_is_left_alone():
    body = " ".join(["word"] * 1500)
    src = f"These 1,500 words cover it.\n\n{body}"
    clean, report = sanitize(src)
    assert "These 1,500 words" in clean
    assert report["length_claims_corrected"] == 0


def test_word_count_quoted_about_something_else_is_untouched():
    """No self-referential lead-in means it is someone else's number."""
    src = "The leaked system prompt runs to 4,000 words of policy. " + " ".join(["w"] * 900)
    clean, report = sanitize(src)
    assert "4,000 words of policy" in clean
    assert report["length_claims_corrected"] == 0


def test_the_following_words_are_self_referential():
    body = " ".join(["word"] * 1000)
    src = f"The following 300 words cover it.\n\n{body}"
    clean, report = sanitize(src)
    assert "The following 1,000 words" in clean
    assert report["length_claims_corrected"] == 1


def test_a_hyphenated_count_names_another_document_and_is_untouched():
    """`this 2,000-word post` is Simon's length, not ours."""
    body = " ".join(["word"] * 8000)
    src = f"Read this 2,000-word post by Simon Willison.\n\n{body}"
    clean, report = sanitize(src)
    assert "Read this 2,000-word post by Simon Willison." in clean
    assert report["length_claims_corrected"] == 0


def test_another_documents_next_words_are_untouched():
    body = " ".join(["word"] * 8000)
    src = f"The paper's next 400 words explain the method.\n\n{body}"
    clean, report = sanitize(src)
    assert "The paper's next 400 words explain the method." in clean
    assert report["length_claims_corrected"] == 0


class TestUnslopReachesEveryWriter:
    """The humanize pass must reach every prose surface, not just the newsletter.

    voice.md is the single source: the social writers, site story writer,
    humanizer, and tightener all inline it, and engagement pulls the section
    out of it. A silent break here means slop ships (2026-08-19).
    """

    def _voice(self):
        from pathlib import Path
        return Path("data/ramsay/mindpattern/voice.md").read_text()

    def test_voice_guide_carries_the_pass(self):
        voice = self._voice()
        assert "# Humanize pass (unslop)" in voice
        assert "Prefer the plain word" in voice      # rule 31, the last one
        assert "Platform rules win" in voice         # precedence note

    def test_newsletter_writer_invokes_the_pass_without_copying_it(self):
        """The skill points at the pass; voice.md carries the only copy.

        The rules lived in both files briefly. Two copies of 31 rules in one
        prompt can disagree after an edit, so the skill keeps the pointer and
        the structural precedence note, and nothing else.
        """
        from pathlib import Path
        skill = Path("agents/synthesis-writer.md").read_text()
        assert "Humanize pass" in skill
        assert "Prefer the plain word" not in skill   # rule 31 lives in voice.md

    def test_newsletter_prompt_still_receives_the_pass(self):
        """runner inlines voice.md into pass 2, so the rules do reach the writer."""
        from pathlib import Path
        runner_src = Path("orchestrator/runner.py").read_text()
        assert 'voice_file = identity_dir / "voice.md"' in runner_src
        assert "voice_text" in runner_src
        assert "Prefer the plain word" in self._voice()

    def test_site_writer_prompt_carries_the_pass(self):
        from orchestrator.site_writer import build_site_writer_prompt
        prompt = build_site_writer_prompt(
            {"candidate_id": "x"}, {}, voice_text=self._voice())
        assert "# Humanize pass (unslop)" in prompt
        assert "Say what it does" in prompt          # rule 27

    def test_platform_writer_skills_invoke_the_pass(self):
        from pathlib import Path
        for name in ("bluesky-writer", "linkedin-writer", "site-story-writer"):
            skill = Path(f"agents/{name}.md").read_text()
            assert "Humanize pass (unslop)" in skill, name

    def test_engagement_extracts_the_pass_from_voice(self):
        from social.engagement import _unslop_section
        section = _unslop_section()
        assert section.startswith("# Humanize pass (unslop)")
        assert "Prefer the plain word" in section

    def test_engagement_section_survives_a_missing_voice_file(self, tmp_path,
                                                              monkeypatch):
        import social.engagement as eng
        monkeypatch.setattr(eng, "_VOICE_GUIDE_PATH", tmp_path / "gone.md")
        assert eng._unslop_section() == ""

    def test_engagement_section_survives_a_voice_file_without_the_pass(
            self, tmp_path, monkeypatch):
        import social.engagement as eng
        stub = tmp_path / "voice.md"
        stub.write_text("# Voice\n\nNo pass here.\n")
        monkeypatch.setattr(eng, "_VOICE_GUIDE_PATH", stub)
        assert eng._unslop_section() == ""
