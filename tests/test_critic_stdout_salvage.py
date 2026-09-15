"""A critic verdict that arrives on stdout is still a verdict.

The critic is told "Write ONLY the JSON file. No other files, no other output."
On 2026-08-23 the LinkedIn critic twice ignored that and printed its verdict as
prose with exit code 0. `run_agent_with_files` only reads the output file, so a
usable APPROVED was discarded and `review_draft` returned REVISE with the
feedback "Critic agent failed to produce output." The writer then burned all
three iterations rewriting against that non-feedback.

Salvaging is safe here because a critic verdict only chooses APPROVED or
REVISE. Everything ambiguous falls back to REVISE, which is what the failure
path already did.
"""

import json

import pytest

from social import critics


class TestVerdictFromText:
    def test_prose_approval_is_salvaged_with_its_reasoning(self):
        text = (
            "**APPROVED** — 9/9/9.\n\nThe draft is clean. Kill switches all "
            "pass. 293 chars with URL, well-varied rhythm, zero banned language."
        )
        verdict = critics._verdict_from_text(text)
        assert verdict["verdict"] == "APPROVED"
        assert "Kill switches all pass" in verdict["feedback"]

    def test_prose_revision_keeps_the_reasoning_as_feedback(self):
        """The whole point: the writer needs the real notes, not a stub."""
        text = (
            "REVISE. The opener is throat-clearing and the third paragraph "
            "uses 'landed'. Cut both."
        )
        verdict = critics._verdict_from_text(text)
        assert verdict["verdict"] == "REVISE"
        assert "throat-clearing" in verdict["feedback"]

    def test_json_printed_instead_of_written_is_parsed(self):
        text = json.dumps({
            "verdict": "APPROVED",
            "feedback": "Reads well.",
            "scores": {"voice_authenticity": 8, "platform_fit": 9,
                       "engagement_potential": 7},
        })
        verdict = critics._verdict_from_text(text)
        assert verdict["verdict"] == "APPROVED"
        assert verdict["scores"]["platform_fit"] == 9

    def test_json_inside_a_fence_is_parsed(self):
        text = "Here you go:\n```json\n{\"verdict\": \"REVISE\", \"feedback\": \"Too long.\"}\n```"
        verdict = critics._verdict_from_text(text)
        assert verdict["verdict"] == "REVISE"
        assert verdict["feedback"] == "Too long."

    @pytest.mark.parametrize("text", [
        "",
        "   \n  ",
        "API Error: Connection closed mid-response.",
        "api error: overloaded_error",
        "I could not find the draft file.",
        "Let me know if you want anything else!",
    ])
    def test_nothing_usable_returns_none(self, text):
        """An API error must never be read as a passing grade."""
        assert critics._verdict_from_text(text) is None

    def test_an_ambiguous_mention_of_both_words_fails_closed(self):
        text = "The rules say APPROVED or REVISE. I am not sure which applies."
        assert critics._verdict_from_text(text)["verdict"] == "REVISE"

    def test_approval_requires_the_word_to_stand_alone(self):
        """'not approved' must not read as approved."""
        text = "This is not approved. Fix the opener."
        assert critics._verdict_from_text(text)["verdict"] == "REVISE"

    @pytest.mark.parametrize("text", [
        "This cannot be approved as written.",
        "I would not have approved this; the opener is throat-clearing.",
        "Can't be approved. Uses 'landed' twice.",
        "This isn't approved.",
        "I'm not sure this should be approved.",
        "Unapproved: the second line is a pitch.",
    ])
    def test_a_negated_approval_is_a_revise(self, text):
        assert critics._verdict_from_text(text)["verdict"] == "REVISE"

    def test_a_negation_elsewhere_in_the_sentence_does_not_veto_the_verdict(self):
        text = "Not one banned word, and the link is offsite. APPROVED."
        assert critics._verdict_from_text(text)["verdict"] == "APPROVED"


class TestReviewDraftUsesTheSalvage:
    """`run_agent_with_files` hands stdout back under `_stdout` when the
    output file is missing and the caller opted in. The critic opts in; the
    writer must not, because a writer narrating into stdout is what got
    published on 2026-07-14.
    """

    def _run(self, monkeypatch, *, file_result):
        seen = {}

        def fake_run(**kwargs):
            seen.update(kwargs)
            return file_result

        monkeypatch.setattr(critics, "run_agent_with_files", fake_run)
        return critics.review_draft("linkedin", "a draft"), seen

    def test_the_critic_opts_into_the_stdout_fallback(self, monkeypatch):
        _, seen = self._run(monkeypatch, file_result=None)
        assert seen.get("stdout_on_missing") is True

    def test_a_stdout_verdict_is_used_when_the_file_is_missing(self, monkeypatch):
        review, _ = self._run(
            monkeypatch,
            file_result={"_stdout": "**APPROVED** — 9/9/9. The draft is clean."},
        )
        assert review["verdict"] == "APPROVED"
        assert "draft is clean" in review["feedback"]

    def test_the_file_still_wins_when_it_exists(self, monkeypatch):
        review, _ = self._run(
            monkeypatch,
            file_result={"verdict": "REVISE", "feedback": "from the file",
                         "scores": {}},
        )
        assert review["verdict"] == "REVISE"
        assert review["feedback"] == "from the file"

    def test_no_file_and_no_usable_stdout_keeps_the_old_failure(self, monkeypatch):
        review, _ = self._run(monkeypatch, file_result={"_stdout": "API Error: boom"})
        assert review["verdict"] == "REVISE"
        assert "failed to produce output" in review["feedback"]

    def test_a_missing_result_entirely_keeps_the_old_failure(self, monkeypatch):
        review, _ = self._run(monkeypatch, file_result=None)
        assert review["verdict"] == "REVISE"
        assert "failed to produce output" in review["feedback"]


class TestWriterDoesNotOptIn:
    def test_the_writer_never_accepts_stdout_as_a_draft(self):
        """2026-07-14: a writer narrating a denied tool call got published."""
        import inspect

        from social import writers

        source = inspect.getsource(writers.write_platform_draft) \
            if hasattr(writers, "write_platform_draft") \
            else inspect.getsource(writers)
        assert "stdout_on_missing" not in source
