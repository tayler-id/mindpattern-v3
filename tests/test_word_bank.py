"""Tests for the shared word bank.

The bank is the one place a banned term is written down. Four surfaces read it
(newsletter, social, engagement replies, site stories) and the writer prompts
are rendered from the same rows, so a ban cannot be enforced by a gate the
prompt never mentioned.
"""

import re

import pytest

from orchestrator import word_bank


class TestBankShape:
    def test_every_pattern_compiles_and_matches_its_own_term(self):
        for entry in word_bank.BANK:
            pattern = re.compile(entry.pattern, re.IGNORECASE)
            assert pattern.search(entry.example), (
                f"{entry.term}: pattern does not match its own example "
                f"{entry.example!r}"
            )

    def test_every_entry_names_a_replacement(self):
        """A ban list without replacements makes writing worse, not better."""
        for entry in word_bank.BANK:
            assert entry.instead.strip(), f"{entry.term} has no replacement"

    def test_surfaces_are_known(self):
        for entry in word_bank.BANK:
            for surface in entry.surfaces:
                assert surface in word_bank.SURFACES, (
                    f"{entry.term} targets unknown surface {surface!r}"
                )

    def test_caps_carry_a_ceiling_and_bans_do_not(self):
        for entry in word_bank.BANK:
            if entry.tier == "cap":
                assert entry.cap_per_10k > 0, f"{entry.term} caps at zero"
            else:
                assert entry.tier == "ban"
                assert entry.cap_per_10k == 0

    def test_terms_are_unique(self):
        terms = [e.term for e in word_bank.BANK]
        assert len(terms) == len(set(terms))


class TestLanded:
    """The seed case. 27 uses across 9 of 10 August issues, owner said never."""

    def test_landed_is_banned_on_every_surface(self):
        for surface in word_bank.SURFACES:
            found = word_bank.violations(
                "Support for streaming landed in 2.1.239.", surface
            )
            assert any("landed" in v for v in found), surface

    def test_the_owners_three_phrasings_are_all_caught(self):
        for text in (
            "This week Codex landed a new sandbox.",
            "It landed like this for the team.",
            "Where this landed for me is the tool budget.",
        ):
            assert word_bank.violations(text, "social"), text

    def test_landing_page_is_not_a_violation(self):
        assert not word_bank.violations(
            "The landing page ships tomorrow.", "site"
        )


class TestProtectedSpans:
    def test_code_link_and_url_spans_do_not_count(self):
        for text in (
            "The flag is `--landed` in the CLI.",
            "See [landed](https://example.com/landed) for the changelog.",
            "https://example.com/landed-in-2-1-239",
            "```\nlanded = True\n```",
        ):
            assert not word_bank.violations(text, "newsletter"), text

    def test_a_quoted_source_sentence_does_not_count(self):
        """We police our prose, not the words a source used."""
        assert not word_bank.violations(
            'Karpathy wrote "the feature landed last night" on X.',
            "newsletter",
        )

    def test_our_own_sentence_next_to_a_quote_still_counts(self):
        assert word_bank.violations(
            'Support landed today. Karpathy called it "overdue".',
            "newsletter",
        )


class TestRateCaps:
    def test_under_the_cap_passes_and_over_it_fails(self):
        entry = next(e for e in word_bank.BANK if e.tier == "cap")
        filler = "word " * 10_000
        allowed = int(entry.cap_per_10k)

        under = (entry.example + " ") * allowed + filler
        assert not [v for v in word_bank.violations(under, entry.surfaces[0])
                    if entry.term in v]

        over = (entry.example + " ") * (allowed + 4) + filler
        assert [v for v in word_bank.violations(over, entry.surfaces[0])
                if entry.term in v]

    def test_a_short_post_gets_at_least_one_use_of_a_capped_word(self):
        """A 40-word post must not fail a cap expressed per 10,000 words."""
        entry = next(e for e in word_bank.BANK
                     if e.tier == "cap" and "social" in e.surfaces)
        post = entry.example + " " + ("word " * 40)
        assert not [v for v in word_bank.violations(post, "social")
                    if entry.term in v]


class TestSurfaceFiltering:
    def test_entries_for_returns_only_that_surface(self):
        for surface in word_bank.SURFACES:
            for entry in word_bank.entries_for(surface):
                assert surface in entry.surfaces

    def test_every_surface_has_at_least_one_entry(self):
        for surface in word_bank.SURFACES:
            assert word_bank.entries_for(surface)


class TestPromptBlock:
    def test_block_lists_every_ban_for_that_surface_with_its_replacement(self):
        block = word_bank.prompt_block("newsletter")
        for entry in word_bank.entries_for("newsletter"):
            if entry.tier != "ban":
                continue
            assert entry.term in block, f"{entry.term} missing from prompt"
            # The renderer sentence-cases the replacement, so compare the tail.
            assert entry.instead[1:] in block, (
                f"{entry.term} listed without its replacement"
            )

    def test_block_is_stable_across_calls(self):
        assert word_bank.prompt_block("social") == word_bank.prompt_block("social")

    def test_block_carries_no_em_dashes(self):
        """The block is pasted into prose the prose gate then measures."""
        for surface in word_bank.SURFACES:
            assert "—" not in word_bank.prompt_block(surface)


class TestScan:
    def test_scan_reports_counts_and_examples(self):
        text = "Support landed Monday. The fix landed Tuesday."
        hits = word_bank.scan(text, "newsletter")
        landed = next(h for h in hits if h.entry.term == "landed")
        assert landed.count == 2
        assert landed.examples
        assert "landed" in landed.examples[0].lower()

    def test_clean_text_scans_empty(self):
        assert word_bank.scan("The parser reads 40 files a second.", "site") == []


class TestNoDriftFromTheOtherLists:
    def test_bank_terms_are_not_silently_dropped_by_voice_md(self):
        """voice.md is generated from the bank, so the section must exist."""
        from pathlib import Path

        voice = Path("data/ramsay/mindpattern/voice.md").read_text()
        assert word_bank.VOICE_SECTION_MARKER in voice
