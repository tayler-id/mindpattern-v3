"""The identity phase writes analysis it never acts on.

Three defects, all observed in the live vault on 2026-08-20:

1. voice.md has not changed since 2026-06-26 and user.md not since 07-01, yet
   the prompt asks the model to update both every run. Per the 2026-08-17
   STE-house-style revert, runtime prose drift is exactly what we do not want,
   so those two files are now hand-edited only.
2. The scheduled run passes --skip-social, so four of eight inputs arrive
   absent. The model records them as "Not available for this run" and treats
   the gap as a finding, re-flagging the same Gate 1 telemetry hole daily for
   eight weeks.
3. decisions.md entries end in "Action required" items that nothing ever reads
   back, so the same item is restated indefinitely.
"""

import pytest

from memory import identity_evolve as ie


class TestRuntimeWritePolicy:
    def test_only_soul_and_decisions_are_runtime_writable(self):
        assert ie.RUNTIME_WRITABLE_KEYS == {"soul", "decisions"}

    def test_apply_skips_voice_and_user_and_reports_them(self, tmp_path):
        for name, body in (
            ("soul.md", "# Soul\n\n## Self Assessment\n\nold\n"),
            ("voice.md", "# Voice\n\n## Tone\n\nkeep me\n"),
            ("user.md", "# User\n\n## Topics\n\nkeep me too\n"),
            ("decisions.md", "# Decisions\n"),
        ):
            (tmp_path / name).write_text(body)

        result = ie.apply_evolution_diff(
            tmp_path,
            {
                "soul": {"action": "update", "section": "Self Assessment",
                         "content": "new assessment"},
                "voice": {"action": "update", "section": "Tone",
                          "content": "MODEL REWROTE THE VOICE"},
                "user": {"action": "update", "section": "Topics",
                         "content": "MODEL REWROTE THE USER"},
            },
        )

        assert "keep me" in (tmp_path / "voice.md").read_text()
        assert "MODEL REWROTE THE VOICE" not in (tmp_path / "voice.md").read_text()
        assert "keep me too" in (tmp_path / "user.md").read_text()
        assert "new assessment" in (tmp_path / "soul.md").read_text()
        assert set(result["skipped_readonly"]) == {"voice", "user"}

    def test_prompt_no_longer_asks_for_voice_or_user_updates(self, tmp_path):
        for name in ("soul.md", "user.md", "voice.md", "decisions.md"):
            (tmp_path / name).write_text(f"# {name}\n")
        prompt = ie.build_evolve_prompt(tmp_path, {"date": "2026-08-21"})
        assert "### voice.md — UPDATE" not in prompt
        assert "### user.md — UPDATE" not in prompt
        assert "hand-edited" in prompt.lower()


class TestSkippedSocialIsNotAGap:
    def test_says_skipped_when_the_run_skipped_social(self, tmp_path):
        for name in ("soul.md", "user.md", "voice.md", "decisions.md"):
            (tmp_path / name).write_text(f"# {name}\n")
        prompt = ie.build_evolve_prompt(
            tmp_path,
            {"date": "2026-08-21", "social": {"skipped": True,
                                              "skip_reason": "--skip-social"}},
        )
        assert "skipped" in prompt.lower()
        assert "not available" not in prompt.lower()
        assert "do not record" in prompt.lower()

    def test_still_reports_social_results_when_social_ran(self, tmp_path):
        for name in ("soul.md", "user.md", "voice.md", "decisions.md"):
            (tmp_path / name).write_text(f"# {name}\n")
        prompt = ie.build_evolve_prompt(
            tmp_path,
            {"date": "2026-08-21",
             "social": {"topic": "agent memory", "gate1_outcome": "approved"}},
        )
        assert "agent memory" in prompt
        assert "approved" in prompt


class TestOpenActionsCarryForward:
    def test_extracts_action_required_items_from_entries(self):
        entries = [
            "## 2026-08-20 — Pipeline Run\n"
            "- **Pattern**: things happened\n"
            "- **Action required**: (1) Check reddit intake. (2) Verify Gate 1 "
            "logging is not broken.\n"
            "- **Tags**: pipeline\n",
            "## 2026-08-19 — Pipeline Run\n"
            "- **Action required**: (1) Check reddit intake.\n",
        ]
        actions = ie.extract_open_actions(entries)
        assert any("reddit intake" in a for a in actions)
        assert any("Gate 1" in a for a in actions)

    def test_deduplicates_an_item_restated_across_runs(self):
        entries = [
            "- **Action required**: (1) Check reddit intake.\n",
            "- **Action required**: (1) Check reddit intake.\n",
            "- **Action required**: (1) check REDDIT intake\n",
        ]
        assert len(ie.extract_open_actions(entries)) == 1

    def test_counts_how_many_runs_have_restated_each_item(self):
        entries = ["- **Action required**: (1) Check reddit intake.\n"] * 3
        actions = ie.extract_open_actions(entries, with_counts=True)
        assert actions[0]["runs"] == 3

    def test_no_action_lines_yields_empty(self):
        assert ie.extract_open_actions(["- **Pattern**: nothing\n"]) == []

    def test_prompt_lists_open_actions_and_demands_they_be_closed(self, tmp_path):
        for name in ("soul.md", "user.md", "voice.md"):
            (tmp_path / name).write_text(f"# {name}\n")
        (tmp_path / "decisions.md").write_text(
            "# Decisions\n\n"
            "## 2026-08-20 — Pipeline Run\n"
            "- **Action required**: (1) Verify Gate 1 logging is not broken.\n\n"
            "## 2026-08-19 — Pipeline Run\n"
            "- **Action required**: (1) Verify Gate 1 logging is not broken.\n"
        )
        prompt = ie.build_evolve_prompt(tmp_path, {"date": "2026-08-21"})
        assert "Open Action Items" in prompt
        assert "Gate 1 logging" in prompt
        assert "restated" in prompt.lower()
