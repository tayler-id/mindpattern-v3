"""Site stories have to link the sources they are built on.

Measured 2026-08-23: 63 of 63 site stories written that day had zero links in
body_markdown, and 80 of 84 on 2026-08-21. The site's markdown renderer already
turns [text](url) into a real anchor, so the writer was the blocker.
"""

import json
from pathlib import Path

import pytest

from orchestrator.site_copy_lint import (
    hard_fail_issues,
    lint_site_copy,
    markdown_links,
    normalize_url,
    required_inline_links,
    revise_issues,
)
from orchestrator.site_writer import (
    build_site_writer_prompt,
    evidence_block_for_pack,
    linkable_source_urls,
    parse_writer_output,
)

SOURCE_URL = "https://openai.com/news/agents"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "site_copy_lint"
WRITER_SKILL = Path(__file__).parent.parent / "agents" / "site-story-writer.md"


def _copy(body: str) -> dict[str, str]:
    return {
        "title": "OpenAI puts agent reliability on buyer scorecards",
        "dek": "Procurement teams will ask for recovery and observability before they trust autonomy.",
        "take": "Runtime reliability is the control plane, and buyers won't pay for autonomy without it.",
        "why_now": "The July 2 source trail ties the reliability note to agent buying criteria.",
        "body_markdown": body,
    }


def _codes(copy, *, allowed_urls=(SOURCE_URL,)):
    issues = lint_site_copy(copy, allowed_urls=set(allowed_urls))
    return {issue.code for issue in issues}, issues


def _graph_pack(refs):
    return {"candidate_id": "openai-agent-runtime-reliability", "source_refs": refs}


# --- lint: the missing-link rule ------------------------------------------


def test_body_without_a_link_is_a_revise_not_a_fail():
    codes, issues = _codes(_copy("OpenAI made reliability visible, per OpenAI."))

    assert "missing_source_link" in codes
    issue = next(item for item in issues if item.code == "missing_source_link")
    assert issue.severity == "revise"
    assert issue.field == "body_markdown"
    assert issue not in hard_fail_issues(issues)
    assert issue in revise_issues(issues)
    assert "1 source URL" in issue.message


def test_body_with_an_inline_source_link_clears_the_rule():
    body = f"OpenAI made reliability visible in its [agent platform notes]({SOURCE_URL})."
    codes, _ = _codes(_copy(body))

    assert "missing_source_link" not in codes


def test_rule_is_silent_when_the_evidence_carries_no_urls():
    codes, _ = _codes(_copy("OpenAI made reliability visible."), allowed_urls=())

    assert "missing_source_link" not in codes


def test_generic_anchor_text_is_flagged_instead():
    body = f"OpenAI made reliability visible. [Source]({SOURCE_URL})"
    codes, issues = _codes(_copy(body))

    assert "missing_source_link" not in codes
    issue = next(item for item in issues if item.code == "generic_link_anchor")
    assert issue.severity == "revise"
    assert "Source" in issue.excerpt


@pytest.mark.parametrize("anchor", ["here", "Click here", "read more", "this link"])
def test_every_placeholder_anchor_is_flagged(anchor):
    codes, _ = _codes(_copy(f"Reliability moved. [{anchor}]({SOURCE_URL})"))

    assert "generic_link_anchor" in codes


def test_required_inline_links_scales_with_the_source_count():
    assert required_inline_links(0) == 0
    assert required_inline_links(1) == 1
    assert required_inline_links(2) == 2
    assert required_inline_links(3) == 3
    assert required_inline_links(9) == 3


def test_markdown_links_reads_anchor_and_url():
    assert markdown_links(f"see [the S-1]({SOURCE_URL}) for it") == [("the S-1", SOURCE_URL)]


# --- lint: composing with the invented-URL gate ----------------------------


@pytest.mark.parametrize(
    "written",
    [
        SOURCE_URL,
        SOURCE_URL + "/",
        "https://www.openai.com/news/agents",
        "https://OpenAI.com/news/agents",
    ],
)
def test_a_legitimate_source_link_never_trips_the_invented_url_check(written):
    body = f"OpenAI made reliability visible in its [agent platform notes]({written})."
    codes, issues = _codes(_copy(body))

    assert "invented_url" not in codes, [item.as_dict() for item in issues]


def test_a_fabricated_link_still_hard_fails():
    body = "OpenAI made reliability visible in its [notes](https://fabricated.example/proof)."
    _, issues = _codes(_copy(body))

    fails = hard_fail_issues(issues)
    assert [item.code for item in fails] == ["invented_url"]


def test_the_writer_parser_accepts_a_draft_that_links_its_source():
    body = (
        f"OpenAI made reliability visible in its [agent platform notes]({SOURCE_URL}).\n\n"
        "That isn't a small change for buyers."
    )
    parsed = parse_writer_output(json.dumps(_copy(body)), allowed_urls={SOURCE_URL})

    assert parsed is not None
    assert SOURCE_URL in parsed["body_markdown"]


def test_normalize_url_folds_punctuation_and_trailing_slash():
    assert normalize_url(f"<{SOURCE_URL}/>,") == normalize_url(SOURCE_URL)
    assert normalize_url("https://other.example/x") != normalize_url(SOURCE_URL)


def test_link_urls_do_not_count_against_the_prose_checks():
    """A URL's dots split _sentences and its tokens inflate the word count."""
    plain = "Reliability moved to procurement, per the agent platform notes. " * 4
    linked = plain.replace(
        "the agent platform notes",
        f"[the agent platform notes]({SOURCE_URL})",
        1,
    )
    plain_codes, _ = _codes(_copy(plain))
    linked_codes, _ = _codes(_copy(linked))

    assert linked_codes - {"missing_source_link"} == plain_codes - {"missing_source_link"}


def test_good_fixture_models_a_linked_story():
    payload = json.loads((FIXTURE_ROOT / "good" / "strong_story.json").read_text())
    links = markdown_links(payload["copy"]["body_markdown"])

    assert links, "the good fixture is the writer's example, so it links its source"
    assert links[0][1] in payload["allowed_urls"]


# --- the evidence pack and the prompt --------------------------------------


def test_evidence_pack_labels_the_linkable_urls():
    pack = _graph_pack(
        [
            {"url": SOURCE_URL, "domain": "openai.com", "title": "Agent platform notes"},
            {"url": "https://github.com/openai/agents", "domain": "github.com", "title": "Repo"},
        ]
    )
    evidence = json.loads(evidence_block_for_pack(pack))

    assert evidence["linkable_source_urls"] == [SOURCE_URL, "https://github.com/openai/agents"]
    assert evidence["source_link_policy"]["required_inline_links"] == 2
    assert all(source["linkable"] for source in evidence["sources"])


def test_linkable_source_urls_dedupes_and_drops_empties():
    pack = _graph_pack([{"url": SOURCE_URL}, {"url": SOURCE_URL}, {"url": ""}, {}])

    assert linkable_source_urls(pack) == [SOURCE_URL]


def test_writer_prompt_asks_for_links_and_names_the_urls():
    pack = _graph_pack([{"url": SOURCE_URL, "domain": "openai.com", "title": "Notes"}])
    prompt = build_site_writer_prompt(pack, [], voice_text="Be sharp.", rules_text="rules")

    assert "Outbound links (required)" in prompt
    assert "[descriptive anchor](url)" in prompt
    assert SOURCE_URL in prompt
    assert "Put 1 inline markdown link" in prompt


def test_writer_prompt_asks_for_three_links_when_the_pack_has_more_sources():
    pack = _graph_pack(
        [{"url": f"https://example.com/{index}"} for index in range(5)]
    )
    prompt = build_site_writer_prompt(pack, [], voice_text="v", rules_text="rules")

    assert "Put 3 inline markdown links" in prompt


def test_writer_prompt_tells_a_sourceless_pack_not_to_invent_a_link():
    prompt = build_site_writer_prompt({"candidate_id": "x"}, [], voice_text="v", rules_text="r")

    assert "no source URLs" in prompt
    assert "Do not invent one" in prompt


# --- the writer skill ------------------------------------------------------


def test_writer_skill_requires_descriptive_inline_links():
    text = WRITER_SKILL.read_text()

    assert "## Link Out (required)" in text
    assert "[anchor](url)" in text
    assert "linkable_source_urls" in text
    assert 'bare word "Source"' in text
    assert "click here" in text


# --- the seam the reviewers found: rules, critic, and the run trace --------


def test_the_writer_rules_permit_the_pack_urls_the_prompt_demands():
    """The rules text is inlined verbatim into the writer prompt AND is the
    entire rubric the critic scores against. While it read "No new facts,
    numbers, quotes, or URLs", the prompt ordered the writer to emit up to
    three links and the critic scored every one of them as a violation, so a
    linked draft dropped below PASS_SCORE and burned a revision call to undo
    the links."""
    rules = (Path(__file__).parent.parent / "docs" / "specs" / "site-writer-rules.md").read_text()

    assert "No new facts, numbers, quotes, or\n  URLs" not in rules
    assert "linkable_source_urls" in rules
    assert "at least one\n  inline markdown link" in rules


def test_the_critic_skill_scores_for_links_rather_than_against_them():
    critic = (Path(__file__).parent.parent / "agents" / "site-story-critic.md").read_text()
    lowered = critic.lower()

    assert "linkable_source_urls" in critic
    assert "with no inline markdown link" in lowered
    assert "never tell the writer to remove a link" in lowered


def test_the_publish_gate_reports_a_linkless_story_without_blocking_it():
    """A story with no outbound link still publishes. What was missing was any
    record that it happened, which is how 63 of 63 went unnoticed."""
    from orchestrator.site_content_engine import evaluate_site_story_confidence

    story = {
        "kind": "site_story",
        "title": "OpenAI puts agent reliability on buyer scorecards",
        "dek": "Procurement teams will ask for recovery before they trust autonomy.",
        "take": "Runtime reliability is the control plane.",
        "why_now": "The July 2 source trail ties the note to buying criteria.",
        "body_markdown": "OpenAI made reliability visible to buyers, per OpenAI.",
        "source_refs": [{"url": SOURCE_URL, "domain": "openai.com", "title": "Agents"}],
        "claim_evidence": [{"claim": "Reliability is visible", "source_url": SOURCE_URL}],
        "graph_edges": [{"kind": "source"}],
        "provenance": {"redaction_status": "passed"},
    }

    gate = evaluate_site_story_confidence(story)

    assert gate["link_notes"] == ["missing_source_link"]
    assert gate["body_link_count"] == 0
    assert not [reason for reason in gate["reasons"] if reason.startswith("copy_lint:missing")]


def test_the_publish_gate_records_the_links_a_good_story_carries():
    from orchestrator.site_content_engine import evaluate_site_story_confidence

    story = {
        "kind": "site_story",
        "title": "OpenAI puts agent reliability on buyer scorecards",
        "dek": "Procurement teams will ask for recovery before they trust autonomy.",
        "take": "Runtime reliability is the control plane.",
        "why_now": "The July 2 source trail ties the note to buying criteria.",
        "body_markdown": f"OpenAI made reliability visible, per its [agent notes]({SOURCE_URL}).",
        "source_refs": [{"url": SOURCE_URL, "domain": "openai.com", "title": "Agents"}],
        "claim_evidence": [{"claim": "Reliability is visible", "source_url": SOURCE_URL}],
        "graph_edges": [{"kind": "source"}],
        "provenance": {"redaction_status": "passed"},
    }

    gate = evaluate_site_story_confidence(story)

    assert gate["link_notes"] == []
    assert gate["body_link_count"] == 1


def test_the_run_trace_carries_the_link_numbers():
    """After the next run you can answer "did the links land?" from the trace
    instead of hand-querying the database."""
    from orchestrator.runner import _site_content_trace_payload

    payload = _site_content_trace_payload(
        {"status": "completed", "outbound_link_count": 7, "stories_without_links": 2}
    )

    assert payload["outbound_link_count"] == 7
    assert payload["stories_without_links"] == 2


# --- lint hardening the reviewers asked for -------------------------------


def test_an_invented_fragment_on_a_real_source_url_still_fails():
    """normalize_url dropped the fragment from both sides, so the writer could
    invent any #anchor on a real URL and the only hard stop on fabricated URLs
    never saw it."""
    codes, _ = _codes(_copy(f"Per the [notes]({SOURCE_URL}#made-up-section), reliability ships."))

    assert "invented_url" in codes


def test_a_fragment_the_pack_itself_carries_is_still_allowed():
    codes, _ = _codes(
        _copy(f"Per the [notes]({SOURCE_URL}#reliability), reliability ships."),
        allowed_urls=(f"{SOURCE_URL}#reliability",),
    )

    assert "invented_url" not in codes


def test_a_pack_url_carrying_a_fragment_has_to_be_copied_with_it():
    codes, _ = _codes(
        _copy(f"Per the [notes]({SOURCE_URL}), reliability ships."),
        allowed_urls=(f"{SOURCE_URL}#reliability",),
    )

    assert "invented_url" in codes


@pytest.mark.parametrize("anchor", ["**here**", "_here_", '"here"', "`here`", "Source."])
def test_a_weak_anchor_dressed_in_emphasis_or_quotes_is_still_weak(anchor):
    codes, _ = _codes(_copy(f"Reliability ships, per [{anchor}]({SOURCE_URL})."))

    assert "generic_link_anchor" in codes


def test_every_weak_anchor_is_reported_not_only_the_first():
    urls = [SOURCE_URL, "https://anthropic.com/news/agents", "https://github.com/openai/agents"]
    body = " ".join(f"A claim, per [here]({url})." for url in urls)

    _, issues = _codes(_copy(body), allowed_urls=urls)

    assert len([item for item in issues if item.code == "generic_link_anchor"]) == 3


def test_a_five_source_story_with_one_link_is_short_of_the_ask():
    """required_inline_links sizes the ask in the prompt, so it also has to
    measure the answer. Otherwise the ceiling of three is decorative."""
    urls = [f"https://example.com/{index}" for index in range(5)]
    body = f"A claim, per the [first note]({urls[0]}). More prose follows here."

    codes, issues = _codes(_copy(body), allowed_urls=urls)

    assert "too_few_source_links" in codes
    issue = next(item for item in issues if item.code == "too_few_source_links")
    assert issue.severity == "revise"
    assert issue.excerpt == "1 of 3"


def test_a_story_that_links_the_full_ask_is_clean():
    urls = [f"https://example.com/{index}" for index in range(5)]
    body = " ".join(
        f"Claim {index} lands, per the [note {index}]({url})."
        for index, url in enumerate(urls[:3])
    )

    codes, _ = _codes(_copy(body), allowed_urls=urls)

    assert "too_few_source_links" not in codes
    assert "missing_source_link" not in codes
