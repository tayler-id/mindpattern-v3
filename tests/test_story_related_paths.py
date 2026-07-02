"""Reader-facing story related paths (orchestrator/story_related.py)."""

from orchestrator.story_related import (
    related_path_between_stories,
    related_paths_for_story,
)


def _story(slug, *, date="2026-07-01", entities=(), topics=(), urls=(), domains=(),
           findings=(), arcs=(), title=None, summary=""):
    return {
        "id": slug,
        "slug": slug,
        "title": title or slug.replace("-", " "),
        "summary": summary,
        "issue_date": date,
        "target_url": f"/s/{slug}",
        "entity_refs": [
            {"id": entity, "slug": entity, "name": entity.replace("-", " ").title()}
            for entity in entities
        ],
        "source_refs": [{"url": url, "domain": url.split("/")[2], "title": "Src"} for url in urls],
        "graph_connectors": {
            "issue_date": date,
            "entity_ids": list(entities),
            "topic_terms": list(topics),
            "source_urls": list(urls),
            "source_domains": list(domains),
            "finding_ids": list(findings),
            "arc_ids": list(arcs),
        },
    }


def test_unconnected_stories_produce_no_path():
    a = _story("a", entities=["vercel"])
    b = _story("b", entities=["anthropic"], summary="however this contradicts everything")
    assert related_path_between_stories(a, b) is None


def test_shared_entity_path_is_reader_facing():
    a = _story("a", entities=["vercel"])
    b = _story("b", entities=["vercel"])
    path = related_path_between_stories(a, b)
    assert path is not None
    assert path["relationship"] == "multi_connector"
    assert "Shared entity: Vercel" in path["connector_labels"]
    assert path["reason"].startswith("Both cover Vercel")
    assert "Graph match" not in path["reason"]
    assert path["target_url"] == "/s/b"
    edge = path["evidence_edges"][0]
    assert edge["target_url"] == "/e/vercel"


def test_single_shared_topic_is_not_enough():
    a = _story("a", topics=["agents", "safety"])
    b = _story("b", topics=["agents", "pricing"])
    assert related_path_between_stories(a, b) is None


def test_two_shared_topics_connect():
    a = _story("a", topics=["agents", "safety", "evals"])
    b = _story("b", topics=["agents", "safety"])
    path = related_path_between_stories(a, b)
    assert path is not None
    assert "Shared topic" in path["connector_labels"]


def test_temporal_continuation_and_precursor():
    a = _story("a", date="2026-07-01", entities=["vercel"])
    later = _story("later", date="2026-07-03", entities=["vercel"])
    earlier = _story("earlier", date="2026-06-20", entities=["vercel"])

    forward = related_path_between_stories(a, later)
    assert "What happened next" in forward["connector_labels"]
    assert "2026-07-03" in forward["reason"] or "2026-07-03" in " ".join(
        connector["detail"] for connector in forward["connectors"]
    )

    backward = related_path_between_stories(a, earlier)
    assert "Earlier coverage" in backward["connector_labels"]


def test_contrast_requires_shared_substrate():
    a = _story("a", entities=["vercel"])
    b = _story(
        "b",
        entities=["vercel"],
        summary="However, developers push back and the move contradicts earlier pricing promises.",
    )
    path = related_path_between_stories(a, b)
    assert "Tension" in path["connector_labels"]

    unrelated = _story("c", entities=["anthropic"], summary="however this contradicts x")
    assert related_path_between_stories(a, unrelated) is None


def test_downstream_implication_signal():
    a = _story("a", entities=["vercel"])
    b = _story("b", entities=["vercel"], summary="What it means for the agent stack now that pricing changed.")
    path = related_path_between_stories(a, b)
    assert "Downstream implication" in path["connector_labels"]


def test_semantic_neighbor_threshold():
    a = _story("a", entities=["vercel"])
    b = _story("b", entities=["anthropic"])
    assert related_path_between_stories(a, b, similarity=0.44) is None
    path = related_path_between_stories(a, b, similarity=0.61)
    assert path is not None
    assert "Semantically similar" in path["connector_labels"]

    boosted = related_path_between_stories(
        _story("x", entities=["vercel"]), _story("y", entities=["vercel"]), similarity=0.9
    )
    assert {"shared_entity", "semantic_neighbor"} <= {
        connector["kind"] for connector in boosted["connectors"]
    }


def test_ranking_and_limit():
    source = _story("src", entities=["vercel"], urls=["https://vercel.com/blog/x"])
    weak = _story("weak", entities=["vercel"])
    strong = _story(
        "strong",
        entities=["vercel"],
        urls=["https://vercel.com/blog/x"],
        findings=["101"],
    )
    strong_source = dict(source)
    strong_source["graph_connectors"] = dict(source["graph_connectors"], finding_ids=["101"])

    paths = related_paths_for_story(strong_source, [weak, strong], limit=1)
    assert len(paths) == 1
    assert paths[0]["slug"] == "strong"


def test_self_is_excluded():
    a = _story("a", entities=["vercel"])
    assert related_paths_for_story(a, [a]) == []


def test_no_raw_relationship_strings_in_labels():
    a = _story("a", entities=["vercel"], urls=["https://vercel.com/blog/x"], domains=["vercel.com"])
    b = _story("b", entities=["vercel"], urls=["https://vercel.com/blog/x"], domains=["vercel.com"])
    path = related_path_between_stories(a, b)
    for label in path["connector_labels"]:
        assert "_" not in label
