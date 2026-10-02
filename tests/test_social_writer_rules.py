"""Every social writing path has to carry the same rules.

There are five: the pipeline writer (social/writers.py, behind #posts), the
Slack revision path (slack_bot/drafts.py), #tips, #skills, and the engagement
reply sniper. Before 2026-08-23 the last three depended entirely on voice.md
reaching them, and the reply sniper read only its first 1,000 characters, which
is frontmatter and a biography. None of them saw a banned word.
"""

import inspect

import pytest

from orchestrator import word_bank

SOCIAL_BANS = [e for e in word_bank.entries_for("social") if e.tier == "ban"]
ENGAGEMENT_BANS = [e for e in word_bank.entries_for("engagement") if e.tier == "ban"]


def _source(func) -> str:
    return inspect.getsource(func)


class TestEveryWriterCarriesTheBank:
    """Source-level check: the rules must be built into the prompt.

    Asserting on the source rather than a rendered prompt is deliberate. These
    handlers need a live Slack client to run, and the failure being guarded
    against is a prompt that never mentions the bank at all.
    """

    @pytest.mark.parametrize(
        "module_name, func_name",
        [
            ("slack_bot.handlers.tips", "TipsHandler._create_drafts"),
            ("slack_bot.handlers.skills", "SkillsHandler._create_drafts"),
            ("slack_bot.handlers.engagement", "EngagementHandler._handle_reply_sniper"),
            ("slack_bot.handlers.engagement", "EngagementHandler._draft_and_approve_reply"),
            ("slack_bot.drafts", "revise_draft"),
            ("social.writers", "_build_writer_agent_prompt"),
        ],
    )
    def test_prompt_builder_injects_the_word_bank(self, module_name, func_name):
        import importlib

        module = importlib.import_module(module_name)
        obj = module
        for part in func_name.split("."):
            obj = getattr(obj, part)

        source = _source(obj)
        assert "word_bank.prompt_block(" in source, (
            f"{module_name}.{func_name} builds a writing prompt without the "
            "word bank, so its output is gated by rules it never saw"
        )


class TestReplySniperReadsTheWholeGuide:
    def test_voice_guide_is_not_truncated_to_frontmatter(self):
        """voice[:1000] is the YAML header, the title and one paragraph."""
        from slack_bot.handlers import engagement

        for name in ("_handle_reply_sniper", "_draft_and_approve_reply"):
            source = _source(getattr(engagement.EngagementHandler, name))
            assert "voice[:1000]" not in source, (
                f"{name} truncates the voice guide before any rule appears"
            )

    def test_the_first_1000_chars_of_voice_md_really_are_ruleless(self):
        """Guards the premise above against a voice.md reshuffle."""
        from pathlib import Path

        head = Path("data/ramsay/mindpattern/voice.md").read_text()[:1000]
        assert "Banned" not in head
        assert "landed" not in head


class TestSniperRepliesAreGated:
    def test_a_drafted_reply_runs_through_the_engagement_gate(self):
        from slack_bot.handlers import engagement

        for name in ("_handle_reply_sniper", "_draft_and_approve_reply"):
            source = _source(getattr(engagement.EngagementHandler, name))
            assert "repair_reply" in source, (
                f"{name} posts model output with no word-bank check"
            )


class TestBansAreActuallyPresent:
    """The parametrized check above proves the call exists. This proves the
    call renders the terms, so a future prompt_block that returns "" fails."""

    def test_social_block_names_every_social_ban(self):
        block = word_bank.prompt_block("social")
        for entry in SOCIAL_BANS:
            assert entry.term in block, entry.term

    def test_engagement_block_names_every_engagement_ban(self):
        block = word_bank.prompt_block("engagement")
        for entry in ENGAGEMENT_BANS:
            assert entry.term in block, entry.term
