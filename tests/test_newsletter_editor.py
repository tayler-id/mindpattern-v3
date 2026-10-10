"""orchestrator.newsletter_editor applies a second model's line edits only when they keep the facts."""
import json

from core.claude_cli import ClaudeProcessResult
from core.config import Route
from orchestrator import newsletter_editor as ed

ISSUE = (
    "# Daily wire\n\n"
    "## Agents\n\n"
    "Acme shipped Runtime 2.0 on May 2, cutting failed tasks by 40%. This matters for every team running agents. "
    "The planner is the interesting part: it retries with a smaller model. "
    "Read the [release notes](https://example.com/acme) before upgrading.\n"
)


def test_a_clean_edit_is_applied():
    text, applied, rejected = ed.apply_edits(ISSUE, [{
        "find": "This matters for every team running agents.",
        "replace": "Teams running agents get fewer retries.",
        "reason": "significance flag"}])
    assert rejected == [] and len(applied) == 1
    assert "Teams running agents get fewer retries." in text and "This matters" not in text


def test_edits_that_change_facts_are_rejected():
    cases = {
        "drops number '40%'": ("cutting failed tasks by 40%.", "cutting many failed tasks."),
        "adds number '50%'": ("This matters for every team running agents.", "About 50% of teams run agents."),
        "drops url 'https://example.com/acme'": (
            "Read the [release notes](https://example.com/acme) before upgrading.", "Read the notes before upgrading."),
        "drops name 'Acme'": ("Acme shipped Runtime 2.0 on May 2,", "The vendor shipped Runtime 2.0 on May 2,"),
        "find occurs 0 times": ("This text is not in the issue.", "Anything."),
        "touches a heading": ("## Agents", "## Agent news"),
        "adds an em dash": ("The planner is the interesting part:", "The planner — the interesting part —"),
        "adds banned term 'genuinely'": ("This matters for every team running agents.", "Every team running agents is genuinely helped."),
    }
    for expected, (find, replace) in cases.items():
        _, applied, rejected = ed.apply_edits(ISSUE, [{"find": find, "replace": replace, "reason": "x"}])
        assert applied == [], expected
        assert rejected[0]["why"] == expected, (expected, rejected[0]["why"])


def test_a_kept_url_with_new_anchor_text_drops_the_markdown_link():
    _, applied, rejected = ed.apply_edits(ISSUE, [{
        "find": "Read the [release notes](https://example.com/acme) before upgrading.",
        "replace": "Read the [notes](https://example.com/acme) before upgrading.", "reason": "x"}])
    assert applied == [] and rejected[0]["why"] == "drops link '[release notes](https://example.com/acme)'"


def test_a_sentence_opening_word_is_not_treated_as_a_name():
    assert ed.check_edit("The planner is the interesting part: it retries with a smaller model.",
                         "When a task fails, the planner retries it with a smaller model.", ISSUE) is None


def _stream(text: str) -> str:
    return "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "t"}),
        json.dumps({"type": "item.completed", "item": {"id": "i", "type": "agent_message", "text": text}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5}}),
    ])


def test_the_editor_runs_on_its_route_and_reports_before_and_after(monkeypatch):
    route = Route("newsletter_editor", "codex", "gpt-6.1-sol", 600, effort="medium")
    monkeypatch.setattr(ed, "route_for", lambda task: route)
    calls = []
    edits = {"edits": [{"find": "This matters for every team running agents.",
                        "replace": "Teams running agents get fewer retries.", "reason": "significance flag"},
                       {"find": "cutting failed tasks by 40%.", "replace": "cutting failed tasks.", "reason": "x"}]}

    def runner(argv, **kwargs):
        calls.append(argv)
        return ClaudeProcessResult(_stream(json.dumps(edits)), "", 0)

    outcome = ed.edit_newsletter(ISSUE, runner=runner)
    assert calls[0][:2] == ["codex", "exec"]
    assert calls[0][calls[0].index("--output-schema") + 1].endswith("contracts/editor_edits.schema.json")
    assert outcome.summary() == {"skipped": None, "applied": 1, "rejected": 1, "rejections": ["drops number '40%'"],
                                 "violations_before": 3, "violations_after": 2}


def test_the_editor_fails_open(monkeypatch):
    monkeypatch.setattr(ed, "route_for", lambda task: Route("newsletter_editor", "codex", "gpt-6.1-sol", 600))
    broken = ed.edit_newsletter(ISSUE, runner=lambda argv, **kw: ClaudeProcessResult(_stream("not json"), "", 0))
    assert broken.text == ISSUE and broken.skipped.startswith("contract:")
    failed = ed.edit_newsletter(ISSUE, runner=lambda argv, **kw: ClaudeProcessResult("", "", 1, timed_out=True))
    assert failed.text == ISSUE and failed.skipped == "editor call timeout"


def test_a_disabled_route_skips_the_editor(monkeypatch):
    monkeypatch.setattr(ed, "route_for", lambda task: Route("newsletter_editor", "codex", "gpt-6.1-sol", 600,
                                                           enabled=False))
    assert ed.edit_newsletter(ISSUE).skipped == "disabled in config/models.json"


def test_an_ordinary_word_opening_a_sentence_is_not_a_name():
    text = ISSUE + "\nBeyond that, log what the agent read. The fix goes beyond the default.\n"
    assert ed.check_edit("Beyond that, log what the agent read.", "Log what the agent read as well.", text) is None
    assert ed.check_edit("Acme shipped Runtime 2.0 on May 2,", "The vendor shipped Runtime 2.0 on May 2,",
                         text) == "drops name 'Acme'"


def test_a_list_the_layout_forbids_goes_to_the_editor_and_folding_it_into_prose_clears_it():
    listed = ISSUE + "\nWhat changed:\n- Runtime 2.0 retries with a smaller model.\n- Failed tasks fell 40%.\n"
    found = ed.policy_violations(listed)
    assert 'layout: section "Agents" has 1 lists where 0 is allowed; fold the extra lists into prose' in found
    assert found[-1] in ed.build_prompt(listed, found)
    folded, applied, rejected = ed.apply_edits(listed, [{
        "find": "What changed:\n- Runtime 2.0 retries with a smaller model.\n- Failed tasks fell 40%.\n",
        "replace": "Runtime 2.0 retries with a smaller model, and failed tasks fell 40%.\n", "reason": "layout"}])
    assert (len(applied), rejected) == (1, [])
    assert not [v for v in ed.policy_violations(folded) if v.startswith("layout:")]
