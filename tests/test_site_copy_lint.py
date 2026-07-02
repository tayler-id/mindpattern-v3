"""Deterministic copy lint for Rabbit Hole site stories."""

import json
from pathlib import Path

import pytest

from orchestrator.site_copy_lint import (
    hard_fail_issues,
    lint_site_copy,
    revise_issues,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "site_copy_lint"


def _good_payload():
    return json.loads((FIXTURE_ROOT / "good" / "strong_story.json").read_text())


def _good_copy():
    return dict(_good_payload()["copy"])


def _allowed_urls():
    return set(_good_payload()["allowed_urls"])


def _codes(copy, *, allowed_urls=None, include_revise=True):
    issues = lint_site_copy(
        copy,
        allowed_urls=set(_allowed_urls() if allowed_urls is None else allowed_urls),
        include_revise=include_revise,
    )
    return {issue.code for issue in issues}, issues


def test_good_fixture_has_no_lint_issues():
    codes, issues = _codes(_good_copy())
    assert codes == set(), [issue.as_dict() for issue in issues]


def test_non_object_payload_is_hard_fail():
    issues = lint_site_copy("not a dict", allowed_urls=set())

    assert [issue.code for issue in issues] == ["not_object"]
    assert hard_fail_issues(issues) == issues


@pytest.mark.parametrize(
    ("code", "mutate"),
    [
        ("missing_field", lambda c: c.pop("title")),
        ("field_too_long", lambda c: c.__setitem__("title", "x" * 91)),
        ("banned_word", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\nThis is robust.")),
        ("banned_phrase", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\nIn conclusion, the market changed.")),
        ("em_dash", lambda c: c.__setitem__("take", "Reliability is the control plane — buyers know it.")),
        ("invented_url", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + " https://example.com/nope")),
        ("raw_markdown_public_field", lambda c: c.__setitem__("dek", "[OpenAI](https://openai.com/news/agents) changed the procurement screen.")),
        ("internal_machinery", lambda c: c.__setitem__("why_now", "The evidence pack connects source evidence to buying criteria.")),
        ("unsupported_temporal_claim", lambda c: c.__setitem__("why_now", "OpenAI made reliability a buyer-visible benchmark this week.")),
    ],
)
def test_hard_fail_lint_codes(code, mutate):
    copy = _good_copy()
    mutate(copy)
    codes, issues = _codes(copy, include_revise=False)
    assert code in codes, [issue.as_dict() for issue in issues]
    assert any(issue.code == code and issue.severity == "fail" for issue in issues)


@pytest.mark.parametrize(
    ("code", "mutate"),
    [
        ("overlong_sentence", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\n" + " ".join(["Long"] * 26) + ".")),
        ("body_word_count", lambda c: c.__setitem__("body_markdown", "OpenAI made reliability visible. It isn't enough.")),
        ("repeated_paragraph_opener", lambda c: c.__setitem__("body_markdown", "OpenAI made reliability visible.\n\nOpenAI moved the buying screen.\n\nIt isn't enough.")),
        ("generic_take", lambda c: c.__setitem__("take", "Teams need to pay attention because this matters.")),
        ("echo_dek", lambda c: c.__setitem__("dek", "OpenAI puts agent reliability on buyer scorecards.")),
        ("missing_contraction", lambda c: (
            c.__setitem__("take", c["take"].replace("won't", "will not")),
            c.__setitem__("body_markdown", c["body_markdown"].replace("isn't", "is not").replace("can't", "cannot").replace("won't", "will not")),
        )),
        ("promotional_adjective_pile", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\nThis amazing, powerful shift is stunning.")),
        ("vague_attribution", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\nExperts say buyers will demand proof.")),
        ("summary_closer", lambda c: c.__setitem__("body_markdown", c["body_markdown"] + "\n\nIn summary, buyers will ask harder questions.")),
        ("uniform_sentence_rhythm", lambda c: c.__setitem__("body_markdown", "Agents need reliable runtime proof. Buyers need reliable runtime proof. Vendors need reliable runtime proof. Operators need reliable runtime proof.")),
    ],
)
def test_revise_lint_codes(code, mutate):
    copy = _good_copy()
    mutate(copy)
    codes, issues = _codes(copy)
    assert code in codes, [issue.as_dict() for issue in issues]
    assert any(issue.code == code and issue.severity == "revise" for issue in issues)


def test_fixture_corpus_bad_examples_name_the_expected_issue():
    for path in sorted((FIXTURE_ROOT / "bad").glob("*.json")):
        payload = json.loads(path.read_text())
        issues = lint_site_copy(
            payload["copy"],
            allowed_urls=set(payload.get("allowed_urls") or []),
        )
        matching = [issue for issue in issues if issue.code == payload["expected_code"]]
        assert matching, path.name
        assert matching[0].severity == payload["expected_severity"]


def test_hard_fail_and_revise_helpers_split_issue_severity():
    copy = _good_copy()
    copy["take"] = "Runtime reliability is the control plane — buyers know it."
    copy["body_markdown"] = "OpenAI made reliability visible. It isn't enough."

    issues = lint_site_copy(copy, allowed_urls=_allowed_urls())

    assert [issue.code for issue in hard_fail_issues(issues)] == ["em_dash"]
    assert "body_word_count" in {issue.code for issue in revise_issues(issues)}
