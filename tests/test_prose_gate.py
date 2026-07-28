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
