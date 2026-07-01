from orchestrator.site_content_engine import evaluate_site_story_confidence


def _story(**overrides):
    story = {
        "kind": "site_story",
        "status": "published",
        "confidence": "high",
        "title": "OpenAI agent runtime reliability becomes public infrastructure",
        "dek": "A source-backed public intelligence artifact.",
        "take": "Runtime reliability is moving into buyer-facing agent decisions.",
        "why_now": "The July 1 graph pack connects source evidence, entities, and related findings.",
        "body_markdown": "OpenAI made runtime reliability a buyer-visible benchmark.",
        "source_refs": [
            {
                "url": "https://openai.com/news/agents",
                "domain": "openai.com",
                "title": "OpenAI",
            }
        ],
        "entity_refs": [{"id": "openai", "slug": "openai", "name": "OpenAI"}],
        "primary_finding_ids": [101],
        "supporting_finding_ids": [102],
        "arc_ids": ["agent-runtime-control-plane"],
        "graph_edges": [
            {
                "kind": "entity",
                "relationship": "shared_entity",
                "id": "openai",
                "target_url": "/e/openai",
                "evidence": "finding:101",
            }
        ],
        "related_paths": [
            {
                "id": 102,
                "connector_labels": ["Shared entity"],
                "reason": "Related by shared entity.",
                "connectors": [
                    {
                        "kind": "shared_entity",
                        "evidence": [{"kind": "entity", "id": "openai"}],
                    }
                ],
            }
        ],
        "claim_evidence": [
            {
                "claim": "OpenAI made runtime reliability a buyer-visible benchmark.",
                "source_url": "https://openai.com/news/agents",
                "finding_id": 101,
            }
        ],
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.story_generator",
            "redaction_status": "passed",
            "ai_generated": True,
        },
        "json_ld_ready": True,
    }
    story.update(overrides)
    return story


def test_confidence_gate_accepts_source_backed_public_story():
    result = evaluate_site_story_confidence(_story())

    assert result["publishable"] is True
    assert result["confidence"] == "high"
    assert result["reasons"] == []


def test_confidence_gate_rejects_missing_evidence_and_generic_titles():
    result = evaluate_site_story_confidence(
        _story(
            title="Top 5 Stories Today",
            why_now="",
            source_refs=[],
            claim_evidence=[],
            graph_edges=[],
        )
    )

    assert result["publishable"] is False
    assert result["confidence"] == "degraded"
    assert {
        "generic_section_title",
        "missing_why_now",
        "missing_source_evidence",
        "missing_claim_evidence",
        "missing_graph_evidence",
    } <= set(result["reasons"])


def test_confidence_gate_rejects_raw_markdown_and_skeptic_kill_switch():
    result = evaluate_site_story_confidence(
        _story(
            title="**OpenAI agent runtime**",
            dek="[source](https://openai.com/news/agents)",
            skeptic={"kill_switch": True, "reason": "unsupported causal claim"},
        )
    )

    assert result["publishable"] is False
    assert "raw_markdown_in_public_fields" in result["reasons"]
    assert "skeptic_kill_switch" in result["reasons"]
